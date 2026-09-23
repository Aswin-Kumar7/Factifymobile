"""M22 and M23 gates, against real model weights.

    FACTIFY_MODEL_TESTS=1 uv run pytest -m model

Skipped by default: the weights are a few hundred megabytes and CI has no business
downloading them on every commit. They are exercised here, on the machine that
calibrates the threshold, which is the only place the numbers mean anything.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.embeddings.image import ImageEmbedder, cosine
from app.embeddings.text import TextEmbedder
from app.extraction.language import Language

requires_weights = pytest.mark.skipif(
    os.environ.get("FACTIFY_MODEL_TESTS") != "1",
    reason="set FACTIFY_MODEL_TESTS=1 to download model weights and run these",
)

pytestmark = [pytest.mark.model, requires_weights]

CACHE = Path(".cache/model-tests")


@pytest.fixture(scope="module")
def text_embedder() -> TextEmbedder:
    return TextEmbedder()


@pytest.fixture(scope="module")
def image_embedder() -> ImageEmbedder:
    return ImageEmbedder()


def _scene(seed: int, background: str) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", (400, 300), background)
    draw = ImageDraw.Draw(image)
    for _ in range(14):
        x, y = int(rng.integers(0, 340)), int(rng.integers(0, 240))
        draw.rectangle(
            [x, y, x + int(rng.integers(20, 60)), y + int(rng.integers(20, 60))],
            fill=tuple(int(c) for c in rng.integers(0, 255, 3)),
        )
        draw.ellipse([x, y, x + 40, y + 40], outline="black", width=3)
    return image


def _document() -> Image.Image:
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    for row in range(14):
        draw.rectangle([30, 20 + row * 19, 360 - (row % 4) * 40, 28 + row * 19], fill="black")
    return image


def _save(image: Image.Image, name: str, *, quality: int = 40) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.jpg"
    image.convert("RGB").save(path, "JPEG", quality=quality)
    return str(path)


class TestTextEmbedding:
    def test_the_model_produces_the_dimension_the_schema_expects(
        self, text_embedder: TextEmbedder
    ) -> None:
        result = text_embedder.embed_one("A claim about a scheme", language=Language.ENGLISH)

        assert result.succeeded
        assert result.single is not None
        assert len(result.single) == 384

    def test_the_same_claim_matches_across_scripts(self, text_embedder: TextEmbedder) -> None:
        """The point of a multilingual model: a Hindi claim finds an English fact-check."""
        english = text_embedder.embed_one(
            "The government announced a relief scheme for farmers.", language=Language.ENGLISH
        )
        hindi = text_embedder.embed_one(
            "सरकार ने किसानों के लिए राहत योजना की घोषणा की।", language=Language.HINDI
        )

        assert english.single is not None
        assert hindi.single is not None
        assert cosine(english.single, hindi.single) > 0.85

    def test_unrelated_claims_do_not_match(self, text_embedder: TextEmbedder) -> None:
        first = text_embedder.embed_one(
            "The government announced a relief scheme for farmers.", language=Language.ENGLISH
        )
        second = text_embedder.embed_one(
            "A volcano erupted in Indonesia in 2019.", language=Language.ENGLISH
        )

        assert first.single is not None
        assert second.single is not None
        assert cosine(first.single, second.single) < 0.4

    def test_a_batch_costs_no_external_call(self, text_embedder: TextEmbedder) -> None:
        """The M22 gate: ingestion embeds a full batch with zero provider calls."""
        from app.observability.metrics import metrics

        metrics.reset()
        corpus = [f"Corpus item number {index} about a public scheme." for index in range(50)]

        result = text_embedder.embed(corpus, language=Language.ENGLISH)

        assert result.succeeded
        assert len(result.vectors) == 50
        assert metrics.snapshot() == {}, "embedding must not touch any provider"


class TestImageVerification:
    """The M23 gate, and the measurement that produced the threshold."""

    def test_the_model_produces_the_dimension_the_schema_expects(
        self, image_embedder: ImageEmbedder
    ) -> None:
        result = image_embedder.embed([_save(_scene(1, "steelblue"), "dim")])

        assert result.succeeded
        assert result.single is not None
        assert len(result.single) == 512

    def test_a_recycled_variant_verifies_against_the_original(
        self, image_embedder: ImageEmbedder
    ) -> None:
        """Cropped, resized and recompressed — what sharing does to an image."""
        original = _scene(1, "steelblue")
        recycled = original.crop((20, 15, 380, 285)).resize((300, 225))

        result = image_embedder.embed([_save(original, "orig"), _save(recycled, "recycled")])

        assert result.succeeded
        verification = image_embedder.verify(result.vectors[0], result.vectors[1])
        assert verification.verified
        assert verification.similarity > 0.96

    def test_genuinely_different_content_does_not_verify(
        self, image_embedder: ImageEmbedder
    ) -> None:
        result = image_embedder.embed(
            [_save(_scene(1, "steelblue"), "photo"), _save(_document(), "document")]
        )

        verification = image_embedder.verify(result.vectors[0], result.vectors[1])

        assert not verification.verified
        assert verification.similarity < 0.9

    def test_different_content_of_the_same_kind_is_the_dangerous_case(
        self, image_embedder: ImageEmbedder
    ) -> None:
        """Two different images of the same sort of scene score ~0.956.

        This is why embedding similarity is never decisive on its own, and why the
        threshold sits above this number rather than between it and a true match. If
        this assertion ever starts failing low, the threshold can come down; if it
        starts failing high, the whole technique needs revisiting.
        """
        result = image_embedder.embed(
            [_save(_scene(1, "steelblue"), "a"), _save(_scene(99, "steelblue"), "b")]
        )

        similarity = cosine(result.vectors[0], result.vectors[1])

        assert similarity > 0.9, "same-kind similarity is high; that is the finding"
        assert not image_embedder.verify(result.vectors[0], result.vectors[1]).verified
