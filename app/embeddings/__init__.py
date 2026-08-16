"""Local embedding services (M22, M23). CPU, ONNX, no quota.

Both are local because ingestion embeds hundreds to thousands of items per day
against a model allowance in the low hundreds. A hosted embedding call would exhaust
the quota before any user request, and would fail quietly.
"""

from app.embeddings.image import (
    ImageEmbedder,
    ImageEmbeddingResult,
    UnavailableImageEmbedder,
    Verification,
    cosine,
)
from app.embeddings.text import (
    EmbeddingResult,
    TextEmbedder,
    UnavailableTextEmbedder,
)

__all__ = [
    "EmbeddingResult",
    "ImageEmbedder",
    "ImageEmbeddingResult",
    "TextEmbedder",
    "UnavailableImageEmbedder",
    "UnavailableTextEmbedder",
    "Verification",
    "cosine",
]
