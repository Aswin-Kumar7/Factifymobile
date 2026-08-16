"""M22 and M23 — the parts that need no model weights.

Weight-requiring tests live in tests/model/, marked and skipped when the weights are
absent, the same way database tests are.
"""

from __future__ import annotations

import pytest

from app.embeddings.image import (
    DEFAULT_THRESHOLD,
    UnavailableImageEmbedder,
    cosine,
)
from app.embeddings.image import (
    DIMENSIONS as IMAGE_DIMENSIONS,
)
from app.embeddings.text import (
    DIMENSIONS as TEXT_DIMENSIONS,
)
from app.embeddings.text import (
    SUPPORTED,
    TextEmbedder,
    UnavailableTextEmbedder,
)
from app.extraction.language import Language

pytestmark = pytest.mark.unit


class TestDimensionContract:
    """The migration fixed these. A mismatch is a schema disagreement, not a warning."""

    def test_text_dimensions_match_the_migration(self) -> None:
        assert TEXT_DIMENSIONS == 384

    def test_image_dimensions_match_the_migration(self) -> None:
        assert IMAGE_DIMENSIONS == 512

    def test_the_migration_declares_the_same_widths(self) -> None:
        from pathlib import Path

        sql = (Path(__file__).resolve().parents[2] / "migrations" / "0001_initial.sql").read_text(
            encoding="utf-8"
        )

        assert f"VECTOR({TEXT_DIMENSIONS})" in sql
        assert f"VECTOR({IMAGE_DIMENSIONS})" in sql


class TestHinglishIsRefusedNotGuessed:
    """The model produces noise for romanised Hindi, so it is not asked to.

    Measured: unrelated Hinglish scores 0.630 while related Hinglish scores 0.494.
    Feeding that into retrieval would produce confident, cited, wrong matches.
    """

    def test_hinglish_is_not_in_the_supported_set(self) -> None:
        assert Language.HINGLISH not in SUPPORTED

    def test_english_and_hindi_are_supported(self) -> None:
        assert Language.ENGLISH in SUPPORTED
        assert Language.HINDI in SUPPORTED

    def test_embedding_hinglish_is_refused_with_a_reason(self) -> None:
        embedder = TextEmbedder()

        result = embedder.embed(["Yeh khabar sach hai"], language=Language.HINGLISH)

        assert not result.succeeded
        assert result.vectors == ()
        assert "lexical" in str(result.reason)

    def test_the_refusal_happens_before_the_model_is_even_loaded(self) -> None:
        """A refusal must not depend on weights being present."""
        embedder = TextEmbedder(model_id="a-model-that-does-not-exist")

        result = embedder.embed(["Yeh sach hai"], language=Language.HINGLISH)

        assert "not represented" in str(result.reason)


class TestUnavailableReturnsNothing:
    """A zero vector would be stored silently and match everything equally."""

    def test_text_embedder_returns_no_vectors(self) -> None:
        result = UnavailableTextEmbedder().embed(["anything"])

        assert result.vectors == ()
        assert not result.succeeded
        assert "unavailable" in str(result.reason)

    def test_image_embedder_returns_no_vectors(self) -> None:
        result = UnavailableImageEmbedder().embed(["/some/path.jpg"])

        assert result.vectors == ()
        assert not result.succeeded

    def test_verification_refuses_rather_than_passing(self) -> None:
        """Defaulting to verified would let hash distance alone decide a match."""
        verification = UnavailableImageEmbedder().verify((1.0,) * 512, (1.0,) * 512)

        assert not verification.verified

    def test_a_missing_model_degrades_rather_than_raising(self) -> None:
        embedder = TextEmbedder(model_id="not/a/real/model")

        result = embedder.embed(["text"], language=Language.ENGLISH)

        assert not result.succeeded
        assert not embedder.available


class TestCosine:
    def test_identical_vectors_are_one(self) -> None:
        assert cosine((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == pytest.approx(1.0)

    def test_orthogonal_vectors_are_zero(self) -> None:
        assert cosine((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)

    def test_opposite_vectors_are_minus_one(self) -> None:
        assert cosine((1.0, 0.0), (-1.0, 0.0)) == pytest.approx(-1.0)

    def test_magnitude_does_not_affect_similarity(self) -> None:
        assert cosine((1.0, 1.0), (5.0, 5.0)) == pytest.approx(1.0)

    def test_a_zero_vector_is_similar_to_nothing(self) -> None:
        """Rather than raising: a zero vector is a bug upstream, not a crash here."""
        assert cosine((0.0, 0.0), (1.0, 1.0)) == 0.0

    def test_a_dimension_mismatch_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="dimension mismatch"):
            cosine((1.0, 2.0), (1.0, 2.0, 3.0))


class TestVerificationSemantics:
    def _embedder(self) -> UnavailableImageEmbedder:
        return UnavailableImageEmbedder()

    def test_the_default_threshold_sits_above_measured_same_kind_similarity(self) -> None:
        """Two different images of the same kind measured 0.956.

        The threshold sits above that on purpose: a false match is a cited wrong
        answer, a miss is an honest abstention.
        """
        assert DEFAULT_THRESHOLD > 0.956

    def test_a_near_miss_is_identifiable_for_calibration(self) -> None:
        from app.embeddings.image import Verification

        verification = Verification(verified=False, similarity=0.94, threshold=0.96)

        assert verification.is_near_miss
        assert verification.margin == pytest.approx(-0.02)

    def test_a_clear_rejection_is_not_a_near_miss(self) -> None:
        from app.embeddings.image import Verification

        verification = Verification(verified=False, similarity=0.61, threshold=0.96)

        assert not verification.is_near_miss

    def test_there_is_no_search_method_on_the_embedder(self) -> None:
        """Structural: this verifies candidates, it never proposes them.

        A nearest-neighbour method here would make embedding similarity primary
        retrieval, which is precisely what the 0.956 result forbids.
        """
        from app.embeddings.image import ImageEmbedder

        forbidden = {"search", "nearest", "query", "find", "retrieve", "most_similar"}

        assert not (forbidden & set(dir(ImageEmbedder)))
