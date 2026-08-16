"""M15, M16, M17, M21 — intake, web, PDF and phrasing."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from app.domain.enums import Action, ClaimStatus, MediaProvenance, SourceRisk
from app.extraction import pdf as pdf_module
from app.extraction import phrasing
from app.extraction import web as web_module
from app.extraction.language import Language
from app.intake.normalizer import (
    InputType,
    IntakeRejected,
    normalise_text,
    normalise_upload,
    normalise_url,
)

pytestmark = pytest.mark.unit


ARTICLE_HTML = """
<html><head>
<title>Government announces relief scheme</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"NewsArticle",
 "headline":"Government announces relief scheme",
 "datePublished":"2019-03-14T09:00:00Z",
 "author":{"@type":"Person","name":"A Reporter"},
 "publisher":{"@type":"Organization","name":"Example Times"},
 "image":"https://example.org/photo.jpg"}
</script></head>
<body><article>
<p>The government announced a relief scheme for farmers on Thursday, according to a
statement issued by the department in New Delhi that afternoon.</p>
<p>Officials said applications would open next month and that the scheme would cover
every district in the state without exception this year.</p>
<blockquote>We will ensure every eligible farmer receives support, the minister said.</blockquote>
<p>See also <a href="https://reuters.example/report">the original report</a>.</p>
</article></body></html>
"""


class TestIntakeText:
    def test_text_is_hashed_and_language_detected(self) -> None:
        intake = normalise_text("Yeh khabar sach hai, sab log forward karo")

        assert intake.input_type is InputType.TEXT
        assert intake.cache_identity.startswith("sha256:")
        assert intake.language.language is Language.HINGLISH

    def test_the_same_text_with_different_whitespace_is_one_cache_entry(self) -> None:
        first = normalise_text("a claim about a scheme")
        second = normalise_text("a  claim   about a scheme\n")

        assert first.cache_identity == second.cache_identity

    def test_empty_text_is_rejected(self) -> None:
        with pytest.raises(IntakeRejected):
            normalise_text("   ")


class TestIntakeUrl:
    def test_tracking_parameters_do_not_fork_the_cache_key(self) -> None:
        """Every person sharing an article would otherwise be a separate miss."""
        plain = normalise_url("https://example.org/story")
        shared = normalise_url("https://example.org/story?utm_source=whatsapp&fbclid=xyz")

        assert plain.cache_identity == shared.cache_identity

    def test_meaningful_query_parameters_are_kept(self) -> None:
        first = normalise_url("https://example.org/article?id=1")
        second = normalise_url("https://example.org/article?id=2")

        assert first.cache_identity != second.cache_identity

    def test_case_and_default_port_are_normalised(self) -> None:
        assert (
            normalise_url("HTTPS://Example.ORG:443/story/").cache_identity
            == normalise_url("https://example.org/story").cache_identity
        )

    def test_normalisation_does_not_fetch(self) -> None:
        """No network at intake. The cache is probed on the canonical form first."""
        intake = normalise_url("https://example.org/story")

        assert intake.primary.source_url == "https://example.org/story"
        assert intake.primary.data is None


class TestIntakeUpload:
    def _png(self) -> bytes:
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), "green").save(buffer, format="PNG")
        return buffer.getvalue()

    def test_an_image_is_identified_by_its_bytes(self) -> None:
        intake = normalise_upload(self._png(), max_bytes=1_000_000)

        assert intake.input_type is InputType.IMAGE
        assert intake.primary.mime_type == "image/png"
        assert intake.primary.width == 10

    def test_a_declared_type_that_lies_is_recorded_not_honoured(self) -> None:
        intake = normalise_upload(self._png(), max_bytes=1_000_000, declared_type="application/pdf")

        assert intake.input_type is InputType.IMAGE
        assert any("declared" in note for note in intake.notes)

    def test_an_unsupported_file_is_rejected_with_a_reason(self) -> None:
        with pytest.raises(IntakeRejected) as raised:
            normalise_upload(b"<?php echo 1; ?>", max_bytes=1000)

        assert raised.value.kind == "unsupported"

    def test_identity_is_computed_over_sanitised_bytes(self) -> None:
        """So the same photo shared with and without GPS is one cache entry."""
        intake = normalise_upload(self._png(), max_bytes=1_000_000)

        assert intake.cache_identity.startswith("sha256:")
        assert intake.primary.data is not None


class TestWebExtraction:
    def test_structured_metadata_is_preferred(self) -> None:
        article = web_module.extract(ARTICLE_HTML, url="https://example.org/story")

        assert article.has_structured_metadata
        assert article.title == "Government announces relief scheme"
        assert article.author == "A Reporter"
        assert article.publisher == "Example Times"
        assert article.published_at is not None
        assert article.published_at.year == 2019

    def test_paragraphs_carry_the_offsets_a_claim_will_anchor_to(self) -> None:
        article = web_module.extract(ARTICLE_HTML, url="https://example.org/story")

        assert article.paragraphs
        first = article.paragraphs[0]
        assert first.char_end > first.char_start
        assert article.body[first.char_start : first.char_end].strip() == first.text

    def test_outbound_links_are_kept_for_the_attribution_check(self) -> None:
        """A content extractor drops these as boilerplate; the killer check needs them."""
        article = web_module.extract(ARTICLE_HTML, url="https://example.org/story")

        assert "https://reuters.example/report" in article.outbound_links

    def test_quotes_are_kept_for_the_quote_check(self) -> None:
        article = web_module.extract(ARTICLE_HTML, url="https://example.org/story")

        assert any("every eligible farmer" in quote for quote in article.quotes)

    def test_missing_structured_metadata_is_recorded_as_a_signal(self) -> None:
        """Real CMSes emit JSON-LD; sites built to look like publishers often do not."""
        article = web_module.extract("<html><body><p>x</p></body></html>")

        assert not article.has_structured_metadata
        assert "no structured article metadata" in article.limitations

    def test_a_page_that_cannot_be_parsed_reports_its_limits(self) -> None:
        article = web_module.extract("<html><body><div id='root'></div></body></html>")

        assert not article.is_usable
        assert article.limitations

    def test_the_excerpt_is_short_not_the_whole_body(self) -> None:
        """Storing the full body would be republishing someone else's work."""
        article = web_module.extract(ARTICLE_HTML)

        assert len(article.excerpt) <= 500


class TestPdfExtraction:
    def _pdf(self, pages: int = 2) -> bytes:
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=200, height=200)
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def test_pages_are_counted_and_anchored(self) -> None:
        result = pdf_module.extract(self._pdf(3))

        assert result.page_count == 3
        assert [page.number for page in result.pages] == [1, 2, 3]

    def test_a_page_limit_is_reported_not_silently_applied(self) -> None:
        result = pdf_module.extract(self._pdf(5), max_pages=2)

        assert len(result.pages) == 2
        assert any("read 2 of 5" in limit for limit in result.limitations)

    def test_a_scanned_pdf_is_routed_to_ocr(self) -> None:
        """A forged circular is usually a photograph of a printout."""
        result = pdf_module.extract(self._pdf(1))

        assert result.needs_ocr

    def test_a_non_pdf_is_rejected(self) -> None:
        with pytest.raises(pdf_module.PdfRejected):
            pdf_module.extract(b"not a pdf at all")

    def test_an_empty_file_is_rejected(self) -> None:
        with pytest.raises(pdf_module.PdfRejected):
            pdf_module.extract(b"")


class TestPhrasing:
    """The kill-switch drill lives here: no model call on the response path."""

    def test_english_verdict_renders(self) -> None:
        rendered = phrasing.render(
            status=ClaimStatus.MISLEADING_CONTEXT,
            action=Action.SHARE_WITH_CONTEXT,
            provenance=MediaProvenance.RECYCLED_OR_MISATTRIBUTED,
            source_risk=SourceRisk.MEDIUM,
            reasons=("Same image found in a dated 2019 source",),
            language=Language.ENGLISH,
        )

        assert rendered.status_line == "Real content, misleading context"
        assert rendered.action_line == "Share only with context."
        assert rendered.reasons

    def test_hindi_verdict_renders_in_devanagari(self) -> None:
        rendered = phrasing.render(
            status=ClaimStatus.CONTRADICTED,
            action=Action.DO_NOT_SHARE,
            language=Language.HINDI,
        )

        assert "खंडित" in rendered.status_line
        assert "साझा न करें" in rendered.action_line

    def test_hinglish_readers_get_english_not_devanagari(self) -> None:
        """Someone typing Hindi in Latin script reads English more easily than
        Devanagari they did not choose."""
        rendered = phrasing.render(
            status=ClaimStatus.SUPPORTED,
            action=Action.SAFE_TO_SHARE,
            language=Language.HINGLISH,
        )

        assert rendered.action_line == "Safe to share."

    def test_every_status_and_action_has_wording_in_both_languages(self) -> None:
        for status in ClaimStatus:
            for action in Action:
                for language in (Language.ENGLISH, Language.HINDI):
                    rendered = phrasing.render(status=status, action=action, language=language)
                    assert rendered.status_line
                    assert rendered.action_line

    def test_capacity_notes_are_surfaced_verbatim(self) -> None:
        """A result that omits what it could not check is not an honest result."""
        rendered = phrasing.render(
            status=ClaimStatus.UNVERIFIED,
            action=Action.SEND_TO_REVIEW,
            capacity_notes=("vision: capacity limited",),
        )

        assert any("vision: capacity limited" in note for note in rendered.not_checked)

    def test_corroboration_reports_origins_alongside_documents(self) -> None:
        rendered = phrasing.render(
            status=ClaimStatus.SUPPORTED,
            action=Action.SAFE_TO_SHARE,
            document_count=19,
            origin_count=3,
        )

        assert rendered.corroboration_line == "19 articles, 3 independent origins"

    def test_the_advisory_heading_states_the_exclusion(self) -> None:
        rendered = phrasing.render(status=ClaimStatus.UNVERIFIED, action=Action.SEND_TO_REVIEW)

        assert "not used in this verdict" in rendered.advisory_heading
