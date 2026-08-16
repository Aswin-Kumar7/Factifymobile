"""The knowledge plane (M24-M26).

A hot corpus, minutes fresh, from allowlisted public sources — so a verification
searches something we already have rather than paying for a live web search.
"""

from app.knowledge.clustering import (
    Assignment,
    Cluster,
    CorroborationCount,
    OriginClusterer,
)
from app.knowledge.ingest import IngestedItem, IngestionWorker, TickResult, parse_feed
from app.knowledge.minhash import Signature, jaccard, shingles, sign
from app.knowledge.registry import (
    FeedDefinition,
    FeedRegistry,
    authenticate_trigger,
    backoff_for,
    load_registry,
    window_start,
)

__all__ = [
    "Assignment",
    "Cluster",
    "CorroborationCount",
    "FeedDefinition",
    "FeedRegistry",
    "IngestedItem",
    "IngestionWorker",
    "OriginClusterer",
    "Signature",
    "TickResult",
    "authenticate_trigger",
    "backoff_for",
    "jaccard",
    "load_registry",
    "parse_feed",
    "shingles",
    "sign",
    "window_start",
]
