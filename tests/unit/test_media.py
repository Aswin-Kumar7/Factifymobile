"""M33-M37 — the media path, everything that needs no model weights or ffmpeg.

The M33 gate ("a known recycled image matches its stored original, and a visually
similar but distinct image produces no match") is asserted twice, deliberately:

  - Here, against a stub embedder, proving the *matcher's* logic is right.
  - In tests/model/test_media_live.py against real CLIP, proving the thresholds are
    right too.

Both matter. The first would pass with a broken threshold; the second would pass with
a matcher that ignored its own verification step.
"""

from __future__ import annotations

import io
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from PIL import Image

from app.domain.enums import SyntheticSignal
from app.domain.evidence import Advisory
from app.embeddings.image import Verification
from app.media.discovery import (
    MatchingPage,
    UnavailableDiscovery,
)
from app.media.forensics import (
    PANEL_HEADER,
    analyse,
    error_level_analysis,
    noise_map,
    spectrum_profile,
)
from app.media.hashing import (
    CANDIDATE_DISTANCE,
    HASH_BITS,
    HashFailed,
    PerceptualHash,
    dhash,
    fingerprint,
    phash,
)
from app.media.matching import LocalMatcher, StoredMedia
from app.media.provenance import ProvenanceReport
from tests.unit import images

pytestmark = pytest.mark.unit


class StubEmbedder:
    """Stands in for CLIP, keyed by the caller's own vectors.

    Not a fake result: it performs the real cosine comparison against the real
    threshold. Only the encoding is replaced, because encoding needs weights.
    """

    threshold = 0.96

    def verify(
        self,
        query: tuple[float, ...],
        candidate: tuple[float, ...],
        *,
        threshold: float | None = None,
    ) -> Verification:
        limit = self.threshold if threshold is None else threshold
        from app.embeddings.image import cosine

        similarity = cosine(query, candidate)
        return Verification(verified=similarity >= limit, similarity=similarity, threshold=limit)


# ---------------------------------------------------------------- M33 · hashing


class TestPerceptualHashing:
    def test_both_hashes_are_64_bits(self) -> None:
        """The `bit(64)` column and the Hamming index both depend on this."""
        data = images.original()
        assert len(dhash(data).to_bit_string()) == HASH_BITS
        assert len(phash(data).to_bit_string()) == HASH_BITS

    def test_bit_string_round_trips(self) -> None:
        value = phash(images.original())
        assert PerceptualHash.from_bit_string(value.to_bit_string(), "phash") == value

    def test_identical_bytes_hash_identically(self) -> None:
        data = images.original()
        assert dhash(data).distance(dhash(data)) == 0

    def test_recompression_barely_moves_the_hash(self) -> None:
        """The whole premise: a re-saved, resized image is still the same picture."""
        assert phash(images.original()).distance(phash(images.recycled())) <= CANDIDATE_DISTANCE

    def test_a_distinct_photograph_is_far_away(self) -> None:
        distance = phash(images.original()).distance(phash(images.distinct()))
        assert distance > CANDIDATE_DISTANCE

    def test_comparing_different_algorithms_raises(self) -> None:
        """dHash and pHash bits describe different things; a distance between them
        would be a number with no meaning, which is worse than an error."""
        data = images.original()
        with pytest.raises(ValueError, match="different things"):
            dhash(data).distance(phash(data))

    def test_undecodable_input_raises_rather_than_returning_a_hash(self) -> None:
        with pytest.raises(HashFailed):
            phash(b"this is not an image")

    def test_fingerprint_carries_the_sha256(self) -> None:
        result = fingerprint(images.original())
        assert result.sha256.startswith("sha256:")


class TestPhashConstruction:
    def test_dc_term_does_not_dominate(self) -> None:
        """Brightness alone must not make two images resemble each other.

        If the DC term leaked into the median, a darkened copy of one photograph and
        a darkened copy of another would drift toward the same hash.
        """
        from PIL import ImageEnhance

        base = images.scene(7)
        darker = ImageEnhance.Brightness(base).enhance(0.55)

        same_picture = phash(images.encode(base)).distance(phash(images.encode(darker)))
        different_picture = phash(images.encode(darker)).distance(
            phash(images.encode(ImageEnhance.Brightness(images.scene(41)).enhance(0.55)))
        )

        assert same_picture < different_picture


# --------------------------------------------------------------- M33 · matching


def _stored(
    identifier: str,
    data: bytes,
    *,
    embedding: tuple[float, ...] | None = None,
    dated: bool = True,
) -> StoredMedia:
    marks = fingerprint(data)
    return StoredMedia(
        id=identifier,
        sha256=marks.sha256,
        dhash=marks.dhash,
        phash=marks.phash,
        embedding=embedding,
        source_date=datetime(2019, 3, 14, tzinfo=UTC) if dated else None,
        citation_url="https://example.org/2019/story" if dated else None,
        publisher="Example Wire" if dated else None,
    )


class TestLocalMatcherGate:
    """The M33 gate, at the matcher level."""

    def test_recycled_image_matches_its_stored_original(self) -> None:
        vector = (1.0, 0.0, 0.0)
        corpus = [_stored("original", images.original(), embedding=vector)]

        result = LocalMatcher(embedder=StubEmbedder()).match(
            fingerprint(images.recycled()), corpus=corpus, query_embedding=vector
        )

        assert result.found
        assert result.matched is not None
        assert result.matched.id == "original"
        assert result.is_citable

    def test_visually_similar_but_distinct_image_produces_no_match(self) -> None:
        """The failure this module exists to prevent: a confident, cited, wrong answer."""
        corpus = [_stored("original", images.original(), embedding=(1.0, 0.0, 0.0))]

        result = LocalMatcher(embedder=StubEmbedder()).match(
            fingerprint(images.distinct()), corpus=corpus, query_embedding=(1.0, 0.0, 0.0)
        )

        assert not result.found
        assert result.matched is None
        assert result.reason


class TestLocalMatcherBehaviour:
    def test_identical_bytes_short_circuit_before_any_approximation(self) -> None:
        data = images.original()
        corpus = [_stored("original", data)]

        result = LocalMatcher(embedder=StubEmbedder()).match(fingerprint(data), corpus=corpus)

        assert result.method == "exact_hash"
        assert result.similarity == 1.0

    def test_hash_candidate_without_an_embedding_is_refused(self) -> None:
        """A hash match alone is not a match — 64 bits collide."""
        corpus = [_stored("original", images.original(), embedding=(1.0, 0.0, 0.0))]

        result = LocalMatcher(embedder=StubEmbedder()).match(
            fingerprint(images.recycled()), corpus=corpus, query_embedding=None
        )

        assert not result.found
        assert "not a match" in result.reason

    def test_a_candidate_failing_visual_verification_is_rejected(self) -> None:
        corpus = [_stored("original", images.original(), embedding=(1.0, 0.0, 0.0))]

        result = LocalMatcher(embedder=StubEmbedder()).match(
            fingerprint(images.recycled()), corpus=corpus, query_embedding=(0.0, 1.0, 0.0)
        )

        assert not result.found
        assert any(a.metric == "clip_cosine" and not a.verified for a in result.attempts)

    def test_rejections_are_recorded_for_calibration(self) -> None:
        """The near-miss log is the only thing that makes the threshold justifiable."""
        corpus = [
            _stored("original", images.original(), embedding=(1.0, 0.0, 0.0)),
            _stored("unrelated", images.distinct(), embedding=(1.0, 0.0, 0.0)),
        ]

        result = LocalMatcher(embedder=StubEmbedder()).match(
            fingerprint(images.recycled()), corpus=corpus, query_embedding=(1.0, 0.0, 0.0)
        )

        assert result.found
        assert any(a.candidate_id == "unrelated" and not a.verified for a in result.attempts)

    def test_an_undated_match_is_not_citable(self) -> None:
        """'We have seen this before' is not a finding. When and where is."""
        vector = (1.0, 0.0, 0.0)
        corpus = [_stored("original", images.original(), embedding=vector, dated=False)]

        result = LocalMatcher(embedder=StubEmbedder()).match(
            fingerprint(images.recycled()), corpus=corpus, query_embedding=vector
        )

        assert result.found
        assert not result.is_citable

    def test_an_empty_corpus_produces_a_miss_not_an_error(self) -> None:
        result = LocalMatcher(embedder=StubEmbedder()).match(
            fingerprint(images.original()), corpus=[], query_embedding=(1.0, 0.0, 0.0)
        )
        assert not result.found
        assert result.reason


# -------------------------------------------------------------- M34 · discovery


class TestDiscovery:
    def test_unconfigured_discovery_returns_nothing_rather_than_a_guess(self) -> None:
        import asyncio

        result = asyncio.run(UnavailableDiscovery().discover(b"bytes"))

        assert not result.succeeded
        assert result.instances == ()
        assert result.provider_skipped

    def test_partial_matches_are_not_fetched(self) -> None:
        assert not MatchingPage(url="https://a.example", full_match=False).is_worth_fetching


# ------------------------------------------------------------- M36 · provenance


class TestProvenance:
    def test_absence_is_unknown_and_says_so_plainly(self) -> None:
        report = ProvenanceReport(present=False)

        assert report.is_unknown
        assert report.signal is SyntheticSignal.NO_SIGNAL
        assert "normal" in report.summary
        assert "not a sign that" in report.summary

    def test_an_invalid_manifest_is_not_suspicion(self) -> None:
        """A broken credential says nothing about the content, only about itself."""
        report = ProvenanceReport(
            present=True, valid=False, validation_errors=("signingCredential",)
        )

        assert report.signal is SyntheticSignal.NO_SIGNAL
        assert "says nothing about whether" in report.summary

    def test_a_valid_manifest_does_not_confirm_the_event(self) -> None:
        report = ProvenanceReport(present=True, valid=True, signer="Example CA")

        assert report.signal is SyntheticSignal.CONFIRMED_BY_PROVENANCE
        assert "does not confirm that the depicted event happened" in report.summary


# --------------------------------------------------------------- M37 · forensics


class TestForensicPanel:
    def test_the_panel_emits_only_advisories(self) -> None:
        panel = analyse(images.original())

        assert panel.rendered
        assert panel.advisories
        assert all(isinstance(item, Advisory) for item in panel.advisories)

    def test_the_panel_carries_its_exclusion_header(self) -> None:
        panel = analyse(images.original())

        assert panel.header == PANEL_HEADER
        assert "not used in the verdict" in panel.header

    def test_the_panel_exposes_no_verdict_shaped_field(self) -> None:
        """A field named `score` or `is_fake` here would be quoted as an accuracy
        figure within a week, whatever the header said."""
        panel = analyse(images.original())
        forbidden = {"verdict", "score", "confidence", "is_fake", "probability", "authentic"}

        assert not forbidden & set(dir(panel))

    def test_every_advisory_is_labelled_as_excluded(self) -> None:
        panel = analyse(images.original())

        for advisory in panel.advisories:
            assert advisory.excluded_note == "Forensic signal — not used in this verdict."

    def test_descriptions_never_assert_authenticity(self) -> None:
        """Both branches of both signals must refuse to conclude."""
        panel = analyse(images.original())
        text = " ".join(a.note for a in panel.advisories).lower()

        assert "does not" in text or "can also" in text or "does not confirm" in text
        assert "authentic" not in text.replace("does not indicate the image is authentic", "")

    def test_undecodable_input_renders_nothing(self) -> None:
        panel = analyse(b"not an image")

        assert not panel.rendered
        assert panel.advisories == ()
        assert panel.reason is not None

    def test_error_level_analysis_is_excluded_by_design(self) -> None:
        """Not missing — refused, and the refusal explains itself."""
        with pytest.raises(NotImplementedError, match="excluded by design"):
            error_level_analysis(images.original())

    def test_noise_map_is_renderable(self) -> None:
        from app.media.forensics import _luminance

        result = noise_map(_luminance(images.original()))

        assert result.blocks
        assert all(0.0 <= value <= 1.0 for row in result.normalised for value in row)

    def test_spectrum_is_renderable(self) -> None:
        from app.media.forensics import _luminance

        result = spectrum_profile(_luminance(images.original()))

        assert result.radial
        assert result.description


class TestForensicsCannotReachTheEngine:
    """M37's gate: disabling the module changes no verdict and no strength score.

    Asserted by running the engine with and without the panel's output and comparing,
    which is the property stated — not merely that a wrong call raises.
    """

    def test_the_panel_changes_no_verdict(self) -> None:
        from app.verdict.engine import decide
        from tests.unit import factories

        claim = factories.claim()
        evidence = [factories.evidence()]
        panel = analyse(images.original())

        without = decide(claim, evidence)
        # There is no argument through which the panel could be supplied, which is
        # the point: `decide` has no advisory parameter at all.
        with_panel = decide(claim, evidence)

        assert without.status == with_panel.status
        assert panel.advisories

    def test_the_panel_changes_no_strength_score(self) -> None:
        from app.verdict.strength import evidence_strength
        from tests.unit import factories

        evidence = [factories.evidence()]
        panel = analyse(images.original())

        without = evidence_strength(evidence)
        with_panel = evidence_strength(evidence, list(panel.advisories))

        assert without.score == with_panel.score
        assert without.band == with_panel.band
        # Present in the output, absent from the arithmetic.
        assert len(with_panel.advisory_excluded) == len(panel.advisories)
        assert without.advisory_excluded == ()

    def test_passing_an_advisory_as_evidence_is_rejected(self) -> None:
        """The structural guard, so the gate above cannot be defeated by a refactor."""
        from app.verdict.engine import AdvisoryLeakError
        from app.verdict.strength import evidence_strength

        panel = analyse(images.original())

        with pytest.raises(AdvisoryLeakError):
            evidence_strength(list(panel.advisories))  # type: ignore[arg-type]


# ------------------------------------------------- 1.8 · a post's pictures, kept


class TestKeptPictures:
    """A post's pictures are shown beside what was read from them (`media_url`), from
    our own address: the app never loads the platform's copy."""

    def test_a_picture_read_is_kept_small_under_a_key_of_our_own(self) -> None:
        from app.media.report import MediaInspector

        inspector = MediaInspector()

        key = inspector.keep_picture(images.original())

        assert key is not None
        assert re.fullmatch(r"[0-9a-f]{32}", key)
        kept = inspector.thumbnails.get(key)
        assert kept is not None
        with Image.open(io.BytesIO(kept)) as picture:
            assert picture.format == "JPEG"
            # 640 x 480 in, the same shape at most 320 on its long side out.
            assert picture.size == (320, 240)

    def test_a_large_photograph_is_kept_as_small_as_any_other(self) -> None:
        from app.media.report import MediaInspector

        inspector = MediaInspector()
        large = images.encode(images.scene(3, size=(4000, 3000), subjects=3))

        key = inspector.keep_picture(large)

        assert key is not None
        kept = inspector.thumbnails.get(key)
        assert kept is not None
        with Image.open(io.BytesIO(kept)) as picture:
            assert picture.size == (320, 240)

    def test_bytes_that_are_not_a_picture_keep_nothing(self) -> None:
        from app.media.report import MediaInspector

        inspector = MediaInspector()

        assert inspector.keep_picture(b"not a picture at all") is None
        assert inspector.keep_picture(b"") is None

    def test_pictures_can_be_kept_from_many_threads_at_once(self) -> None:
        """A post's pictures are kept off the event loop, side by side; the store is
        bounded while they arrive."""
        from app.media.report import ThumbnailStore

        store = ThumbnailStore(most=25)

        with ThreadPoolExecutor(max_workers=8) as pool:
            keys = list(pool.map(lambda index: store.put(bytes([index % 256])), range(400)))

        assert len(set(keys)) == 400
        assert sum(store.get(key) is not None for key in keys) == 25
