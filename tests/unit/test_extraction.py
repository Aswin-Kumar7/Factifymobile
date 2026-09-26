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

    @pytest.mark.parametrize(
        "unusable",
        [
            "htp://example.org/story",  # a typo this service can never follow
            "file:///etc/passwd",  # a local path dressed as a link
            "javascript:alert(1)",  # not a document at all
            "https://localhost/admin",  # a host with no public name
            "not a url at all",
            "https://",
            "http://[::1",  # an unclosed bracket: urlsplit raises on this
        ],
    )
    def test_a_link_that_can_never_be_followed_is_refused_at_intake(self, unusable: str) -> None:
        """Answering 200 with "the linked page could not be read" reports the caller's
        mistake as a gap in the evidence. The SSRF guard still re-checks at fetch time;
        this only refuses the obviously unusable before a case is opened."""
        with pytest.raises(IntakeRejected):
            normalise_url(unusable)

    def test_a_usable_link_with_an_unusual_shape_is_still_accepted(self) -> None:
        """The check must not become a second, stricter allowlist of its own."""
        assert normalise_url("http://thehindu.com/a/b?utm_source=x").primary.source_url == (
            "http://thehindu.com/a/b"
        )
        assert normalise_url("https://timesofindia.indiatimes.com/city/x/1.cms").input_type


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


def test_one_malformed_claim_does_not_discard_the_rest() -> None:
    """A Wikipedia page returned seven claims, one with an importance value in
    `claim_type`, and the whole page came back with nothing to check."""
    from app.extraction.llm import _valid_claims_only

    good = {
        "text": "ISRO launched EOS-05 aboard GSLV-F17.",
        "claim_type": "EVENT",
        "severity": "LOW",
        "importance": "HEADLINE",
    }
    bad = {**good, "claim_type": "BACKGROUND"}

    kept = _valid_claims_only({"claims": [good, bad, good]})

    assert len(kept["claims"]) == 2
    assert all(item["claim_type"] == "EVENT" for item in kept["claims"])


class TestVendorMarkdownIsReadAsText:
    """The search vendor's extract is markdown; quotes are checked against plain text.

    On The Hindu's report of the story a person had pasted, both of the model's quotes
    were discarded as "not in the passage": the sentence was there, with a link in it.
    """

    PAGE = (
        "[Videos](https://example.org/videos/)   [Podcast](https://example.org/podcast/)\n"
        "![The Logo](https://example.org/logo.png)\n"
        "\n"
        "# Union warns of a nationwide strike\n"
        "\n"
        "The union on Thursday demanded the resignation of "
        "[the Labour Minister (LM) A. Kumar](https://example.org/a.ece) for "
        "\u201cundermining\u201d workers, and **warned** of a strike.\n"
        "\n"
        "****[Live updates](https://example.org/live)\n"
        "See [the explainer](https://en.wikipedia.org/wiki/Strike_(action)) for more."
    )

    def test_a_linked_phrase_keeps_its_words_and_loses_its_target(self) -> None:
        text = web_module.plain_text(self.PAGE)

        assert (
            "demanded the resignation of the Labour Minister (LM) A. Kumar for "
            "\u201cundermining\u201d workers, and warned of a strike."
        ) in text
        assert "See the explainer for more." in text
        assert "https://" not in text

    def test_navigation_images_and_markers_are_not_text(self) -> None:
        text = web_module.plain_text(self.PAGE)

        assert "Videos" not in text
        assert "Live updates" not in text
        assert "Logo" not in text
        assert "#" not in text
        assert "*" not in text
        assert text.startswith("Union warns of a nationwide strike")

    def test_a_quote_from_the_page_now_verifies(self) -> None:
        from app.sources.reasoning import verify_quote

        quote = (
            "demanded the resignation of the Labour Minister (LM) A. Kumar for "
            "\u201cundermining\u201d workers"
        )
        assert verify_quote(quote, self.PAGE) is None
        assert verify_quote(quote, web_module.plain_text(self.PAGE)) is not None


class TestReadingASubmittedLink:
    """What a link yields: the article, or the vendor's read of it when we get a wall."""

    ARTICLE = (
        "UNITED NATIONS, Sept 26 (Reuters) - World leaders left the United Nations on "
        "Friday after a week of speeches, meetings and hallway diplomacy. "
    ) * 8

    @staticmethod
    def _request(page_html: str, vendor_text: str) -> tuple[object, list[str]]:
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from app.security.fetcher import FetchResult

        asked: list[str] = []

        class _Reader:
            async def fetch(self, url: str, *, provider: str = "web") -> object:
                return FetchResult(
                    url=url,
                    final_url=url,
                    status_code=200,
                    content_type="text/html",
                    body=page_html.encode(),
                    byte_count=len(page_html),
                    fetched_at=datetime.now(UTC),
                )

        class _Resolver:
            async def _vendor_extract(self, url: str) -> str:
                asked.append(url)
                return vendor_text

        state = SimpleNamespace(url_reader=_Reader(), web_search_resolver=_Resolver())
        return SimpleNamespace(app=SimpleNamespace(state=state)), asked

    @pytest.mark.anyio
    async def test_a_bot_wall_is_not_taken_for_the_article(self) -> None:
        """Reuters answered "Please enable JS and disable any ad blocker" - 43 characters."""
        from app.api.verify import _read_linked_article

        wall = (
            "<html><head><title>reuters.com</title></head><body>"
            "<p>Please enable JS and disable any ad blocker</p></body></html>"
        )
        request, asked = self._request(wall, vendor_text=self.ARTICLE)

        text = await _read_linked_article(request, "https://www.reuters.com/world/x")  # type: ignore[arg-type]

        assert asked == ["https://www.reuters.com/world/x"]
        assert text is not None
        assert "UNITED NATIONS, Sept 26 (Reuters)" in text.text
        assert "enable JS" not in text.text
        assert text.partial is None

    @pytest.mark.anyio
    async def test_an_article_we_can_read_is_not_sent_to_the_vendor(self) -> None:
        from app.api.verify import _read_linked_article

        page = f"<html><body><article><p>{self.ARTICLE}</p></article></body></html>"
        request, asked = self._request(page, vendor_text="should not be used")

        text = await _read_linked_article(request, "https://example.org/story")  # type: ignore[arg-type]

        assert asked == []
        assert text is not None and "hallway diplomacy" in text.text

    def test_a_link_with_nothing_checked_is_not_answered_unconfirmed(self) -> None:
        """Zero claims used to verify as "Unconfirmed" - as if sources had been sought."""
        from typing import Any

        from fastapi.testclient import TestClient

        from app.extraction.claims import ExtractedClaims
        from app.main import create_app

        class _Orchestrator:
            async def cached(self, *args: Any, **kwargs: Any) -> None:
                return None

            async def verify(self, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError("nothing to check must not be verified")

        class _NothingFound:
            async def extract(self, *args: Any, **kwargs: Any) -> ExtractedClaims:
                return ExtractedClaims()

        async def _page(request: Any, url: str) -> Any:
            return verify_module.LinkedPage("A page with nothing in it to check.")

        import app.api.verify as verify_module

        app = create_app()
        app.state.orchestrator = _Orchestrator()
        app.state.claim_pipeline = _NothingFound()
        original = verify_module._read_linked_article
        verify_module._read_linked_article = _page  # type: ignore[assignment]
        try:
            response = TestClient(app).post("/v1/verify", json={"url": "https://example.org/x"})
        finally:
            verify_module._read_linked_article = original  # type: ignore[assignment]

        assert response.status_code == 422
        assert "Nothing was checked" in response.json()["detail"]


class TestALinkInsideAMessage:
    """ "Must read! https://..." is a forward carrying an article, and the article is read."""

    @pytest.mark.parametrize(
        ("message", "link"),
        [
            (
                "Must read!! https://www.reuters.com/world/x-2026-09-26/. Share",
                "https://www.reuters.com/world/x-2026-09-26",
            ),
            ("see www.thehindu.com/news/a.ece", "https://www.thehindu.com/news/a.ece"),
            ("Two: https://a.org/1 and https://b.org/2", "https://a.org/1"),
        ],
    )
    def test_the_first_followable_link_is_found(self, message: str, link: str) -> None:
        from app.api.verify import _first_link

        assert _first_link(message) == link

    @pytest.mark.parametrize("message", ["no link here", "https://localhost/admin is bad"])
    def test_no_link_or_an_unfollowable_one_is_ignored(self, message: str) -> None:
        from app.api.verify import _first_link

        assert _first_link(message) is None


class TestAPageNobodyCanReadIsCheckedOnItsHeadline:
    """The headline and summary a publisher shows anyone, when the article is closed."""

    PAYWALLED = (
        "<html><head><title>Premium | Example Times</title>"
        '<meta property="og:title" content="State to raise minimum wage by 12% from April">'
        '<meta property="og:description" content="The state cabinet on Friday approved a '
        '12% rise in the minimum wage for unskilled workers, effective April 1.">'
        "</head><body><p>Subscribe to read.</p></body></html>"
    )

    def test_the_published_headline_and_summary_are_read(self) -> None:
        headline, summary = web_module.headline_and_summary(self.PAYWALLED)

        assert headline == "State to raise minimum wage by 12% from April"
        assert summary is not None and "effective April 1" in summary

    def test_a_bare_site_name_is_not_a_summary(self) -> None:
        """Reuters' wall page had a title, "reuters.com", and nothing else."""
        wall = "<html><head><title>reuters.com</title></head><body>Enable JS</body></html>"

        assert web_module.headline_and_summary(wall) == (None, None)

    @pytest.mark.anyio
    async def test_the_link_reader_falls_back_to_them_and_says_so(self) -> None:
        from app.api.verify import _read_linked_article

        request, asked = TestReadingASubmittedLink._request(self.PAYWALLED, vendor_text="")

        page = await _read_linked_article(request, "https://example.org/wage")  # type: ignore[arg-type]

        assert asked == ["https://example.org/wage"]
        assert page is not None
        assert "12% rise in the minimum wage" in page.text
        assert page.partial is not None and "headline and summary" in page.partial
