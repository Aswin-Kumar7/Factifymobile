"""Image embedding service (M23).

Verifies perceptual-hash candidates against crop, resize, recolour and re-encoding.
Local CLIP-class ONNX on CPU, loaded once per container, 512 dimensions fixed at the
migration.

## What this measures, and why it is never decisive alone

CLIP embeds **semantic** similarity, not identity. Measured on this model:

    an image vs. itself, cropped, resized and JPEG-recompressed at q40   0.975
    an image vs. genuinely different content                       0.78 - 0.84
    an image vs. different content of the *same kind*                    0.956

That last number is the one that matters. Two different photographs of the same sort
of scene — two crowds, two floods, two ministers at two podiums — score almost as
high as a true match. A system that treated a high cosine as identity would produce a
confident, cited, wrong answer, which is the worst failure available to this product.

Hence two structural rules, not guidelines:

  1. **This is verification, never retrieval.** Candidates come from perceptual-hash
     search over content we have actually seen. Embedding similarity confirms or
     rejects a candidate; it never proposes one.
  2. **A pass here is not evidence.** A decisive media match additionally requires a
     dated source and contextual confirmation. This module answers "could these be
     the same image", not "these are the same image".

The default threshold is deliberately conservative and the module reports the margin
so calibration is done against real matches and logged near-misses rather than
assumed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from math import sqrt

from app.observability.logging import event

logger = logging.getLogger("factify.embeddings.image")

# Fixed at the migration. `content_object.embedding` and
# `media_fingerprint.embedding` are vector(512).
DIMENSIONS = 512

DEFAULT_MODEL = "Qdrant/clip-ViT-B-32-vision"

# Set above the measured same-kind-different-content score (0.956) rather than
# between it and a true match, because the cost of a false match is a cited wrong
# answer while the cost of a miss is an honest abstention. Calibrate on real pairs
# before trusting it; the margin is reported on every comparison so that is possible.
DEFAULT_THRESHOLD = 0.96


@dataclass(frozen=True, slots=True)
class ImageEmbeddingResult:
    vectors: tuple[tuple[float, ...], ...] = ()
    model_id: str | None = None
    reason: str | None = None
    elapsed_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.reason is None

    @property
    def single(self) -> tuple[float, ...] | None:
        return self.vectors[0] if self.vectors else None


@dataclass(frozen=True, slots=True)
class Verification:
    """The outcome of comparing a candidate against a query image.

    `verified` is deliberately not called `matched`: it means the candidate survived
    verification, not that identity was established.
    """

    verified: bool
    similarity: float
    threshold: float
    reason: str | None = None


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Cosine similarity. Pure, so the comparison logic is testable without weights."""
    if len(left) != len(right):
        raise ValueError(f"dimension mismatch: {len(left)} vs {len(right)}")

    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return dot / (left_norm * right_norm)


class ImageEmbedder:
    """Encodes images for candidate verification. One model instance per process."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL,
        cache_dir: str | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._model_id = model_id
        self._cache_dir = cache_dir
        self._threshold = threshold
        self._model: object | None = None
        self._load_failure: str | None = None

    @property
    def threshold(self) -> float:
        return self._threshold

    def _ensure_loaded(self) -> object | None:
        if self._model is not None or self._load_failure is not None:
            return self._model

        try:
            from fastembed import ImageEmbedding

            started = time.perf_counter()
            self._model = ImageEmbedding(self._model_id, cache_dir=self._cache_dir)
            event(
                logger,
                "image embedding model loaded",
                module="embeddings.image",
                outcome="ok",
                model_id=self._model_id,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            self._load_failure = f"{type(exc).__name__}: {exc}"
            event(
                logger,
                "image embedding model unavailable",
                module="embeddings.image",
                outcome="error",
                model_id=self._model_id,
                failure_reason=self._load_failure,
                level=logging.ERROR,
            )

        return self._model

    @property
    def available(self) -> bool:
        return self._ensure_loaded() is not None

    def embed(self, paths: list[str]) -> ImageEmbeddingResult:
        """Encode images from disk paths."""
        if not paths:
            return ImageEmbeddingResult()

        model = self._ensure_loaded()
        if model is None:
            return ImageEmbeddingResult(reason=f"model unavailable: {self._load_failure}")

        started = time.perf_counter()
        try:
            vectors = tuple(
                tuple(float(value) for value in vector)
                for vector in model.embed(paths)  # type: ignore[attr-defined]
            )
        except Exception as exc:
            return ImageEmbeddingResult(reason=f"encoding failed: {type(exc).__name__}: {exc}")

        for vector in vectors:
            if len(vector) != DIMENSIONS:
                return ImageEmbeddingResult(
                    reason=(
                        f"model produced {len(vector)} dimensions, schema expects "
                        f"{DIMENSIONS}; the model and the migration disagree"
                    )
                )

        return ImageEmbeddingResult(
            vectors=vectors,
            model_id=self._model_id,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def verify(
        self,
        query: tuple[float, ...],
        candidate: tuple[float, ...],
        *,
        threshold: float | None = None,
    ) -> Verification:
        """Check whether a hash-search candidate survives visual comparison.

        Called with a candidate that perceptual-hash search already proposed. It is
        not a search function and there is deliberately no method here that takes a
        corpus and returns nearest neighbours — that would make this primary
        retrieval, which the module docstring explains it must never be.
        """
        limit = self._threshold if threshold is None else threshold

        try:
            similarity = cosine(query, candidate)
        except ValueError as exc:
            return Verification(verified=False, similarity=0.0, threshold=limit, reason=str(exc))

        verified = similarity >= limit

        if not verified:
            event(
                logger,
                "candidate rejected",
                module="embeddings.image",
                outcome="rejected",
                similarity=round(similarity, 4),
                threshold=limit,
                near_miss=similarity - limit > -0.05,
            )

        return Verification(verified=verified, similarity=similarity, threshold=limit)


class UnavailableImageEmbedder:
    """Used when no model is configured.

    `verify` refuses rather than passing. A candidate that cannot be verified is not
    a match — defaulting to true here would let hash distance alone decide, which is
    exactly the collision this module exists to catch.
    """

    available = False
    threshold = DEFAULT_THRESHOLD

    def embed(self, paths: list[str]) -> ImageEmbeddingResult:
        del paths
        return ImageEmbeddingResult(reason="unavailable: no image embedding model configured")

    def verify(
        self,
        query: tuple[float, ...],
        candidate: tuple[float, ...],
        *,
        threshold: float | None = None,
    ) -> Verification:
        del query, candidate
        return Verification(
            verified=False,
            similarity=0.0,
            threshold=self.threshold if threshold is None else threshold,
            reason="unavailable: no image embedding model configured",
        )
