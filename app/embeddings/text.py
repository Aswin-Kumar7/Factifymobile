"""Text embedding service (M22).

Local ONNX on CPU, loaded once per container. This is not a preference — it is forced
arithmetic. Ingestion embeds hundreds to thousands of corpus items per day against a
model allowance in the low hundreds that is already committed to claim extraction. A
hosted embedding call would exhaust the daily quota on ingestion alone, before a
single user request, and it would fail *quietly*: correct at test volume, starved in
production.

Dimensionality is 384 and fixed at the migration. Changing it is a schema change.

## A measured limitation, stated plainly

The multilingual model handles Devanagari Hindi and English well and **cannot
represent romanised Hindi at all**. Measured on this model:

    Hindi <-> the same sentence in Hinglish     0.044
    Hinglish <-> Hinglish, same topic           0.494
    Hinglish <-> Hinglish, unrelated topic      0.630

The last two are the problem: unrelated Hinglish scores *higher* than related
Hinglish. The output is not weak signal, it is noise — and noise fed into retrieval
produces confident, cited, wrong matches, which is the failure this system exists to
avoid.

So Hinglish is refused rather than embedded badly. Retrieval falls back to lexical
matching, which does work on romanised text. Transliterating Hinglish to Devanagari
before embedding would unlock cross-script matching properly (Hindi<->English is
0.927) and is the right fix; it needs a real transliterator, not a scheme mapping,
and is recorded as roadmap rather than faked here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.extraction.language import Language
from app.observability.logging import event

logger = logging.getLogger("factify.embeddings.text")

# Fixed at the migration. `claim.embedding` and `corpus_item.embedding` are vector(384).
DIMENSIONS = 384

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Languages this model represents faithfully. Hinglish is deliberately absent; see
# the module docstring for the numbers.
SUPPORTED = frozenset({Language.ENGLISH, Language.HINDI})


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Vectors, or the reason there are none."""

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


class TextEmbedder:
    """Encodes claims and corpus items. One model instance per process."""

    def __init__(self, *, model_id: str = DEFAULT_MODEL, cache_dir: str | None = None) -> None:
        self._model_id = model_id
        self._cache_dir = cache_dir
        self._model: object | None = None
        self._load_failure: str | None = None

    def _ensure_loaded(self) -> object | None:
        """Load on first use, once, and remember a failure rather than retrying it.

        Retrying a missing model on every request would turn one misconfiguration
        into a per-request stall.
        """
        if self._model is not None or self._load_failure is not None:
            return self._model

        try:
            from fastembed import TextEmbedding

            started = time.perf_counter()
            self._model = TextEmbedding(self._model_id, cache_dir=self._cache_dir)
            event(
                logger,
                "text embedding model loaded",
                module="embeddings.text",
                outcome="ok",
                model_id=self._model_id,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            self._load_failure = f"{type(exc).__name__}: {exc}"
            event(
                logger,
                "text embedding model unavailable",
                module="embeddings.text",
                outcome="error",
                model_id=self._model_id,
                failure_reason=self._load_failure,
                level=logging.ERROR,
            )

        return self._model

    @property
    def available(self) -> bool:
        return self._ensure_loaded() is not None

    def supports(self, language: Language | str | None) -> bool:
        """Whether this model represents the language faithfully enough to use.

        A language it cannot represent is refused, not embedded badly.
        """
        if language is None:
            return True
        try:
            return Language(language) in SUPPORTED
        except ValueError:
            return False

    def embed(self, texts: list[str], *, language: Language | str | None = None) -> EmbeddingResult:
        """Encode a batch. Used for ingestion; a single item is a batch of one.

        Batching matters: encoding a feed of 200 items one at a time pays the
        per-call overhead 200 times for no benefit.
        """
        if not texts:
            return EmbeddingResult()

        if not self.supports(language):
            return EmbeddingResult(
                reason=(
                    f"language {language} is not represented by this model; "
                    "retrieval falls back to lexical matching"
                )
            )

        model = self._ensure_loaded()
        if model is None:
            return EmbeddingResult(reason=f"model unavailable: {self._load_failure}")

        started = time.perf_counter()
        try:
            vectors = tuple(
                tuple(float(value) for value in vector)
                for vector in model.embed(texts)  # type: ignore[attr-defined]
            )
        except Exception as exc:
            return EmbeddingResult(reason=f"encoding failed: {type(exc).__name__}: {exc}")

        for vector in vectors:
            if len(vector) != DIMENSIONS:
                # A dimension mismatch would be silently written into a vector(384)
                # column and fail at insert, far from the cause.
                return EmbeddingResult(
                    reason=(
                        f"model produced {len(vector)} dimensions, schema expects "
                        f"{DIMENSIONS}; the model and the migration disagree"
                    )
                )

        return EmbeddingResult(
            vectors=vectors,
            model_id=self._model_id,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def embed_one(self, text: str, *, language: Language | str | None = None) -> EmbeddingResult:
        """Request-path encoding of a single claim."""
        return self.embed([text], language=language)


class UnavailableTextEmbedder:
    """Used when no model is configured. Returns nothing rather than zeros.

    A zero vector would be silently stored and would match everything equally — the
    worst kind of failure, because retrieval would keep working and keep being wrong.
    """

    available = False

    def supports(self, language: Language | str | None) -> bool:
        del language
        return False

    def embed(self, texts: list[str], *, language: Language | str | None = None) -> EmbeddingResult:
        del texts, language
        return EmbeddingResult(reason="unavailable: no text embedding model configured")

    def embed_one(self, text: str, *, language: Language | str | None = None) -> EmbeddingResult:
        return self.embed([text], language=language)
