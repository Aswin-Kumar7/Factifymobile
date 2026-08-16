"""Evidence retrieval (M27-M32).

Every module here answers a different question, and each is careful about what it
refuses to conclude. The source-risk track in particular runs in parallel with the
claim track and never touches it.
"""

from app.sources.attribution import AttributionResolver, QuoteResolver, find_cited_sources
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceResolver,
    SourceSnapshot,
    insufficient,
    keyword_overlap,
    locate_excerpt,
)
from app.sources.corroboration import (
    CorroborationResolver,
    CorroborationResult,
    silence_is_meaningful,
    within_developing_window,
)
from app.sources.factcheck import FactCheckRecord, FactCheckResolver, parse_rating_from_title
from app.sources.risk import RiskSignal, SourceProfile, SourceRiskProfiler
from app.sources.temporal import DatedInstance, TemporalFinding, TemporalResolver

__all__ = [
    "AttributionResolver",
    "CorroborationResolver",
    "CorroborationResult",
    "DatedInstance",
    "FactCheckRecord",
    "FactCheckResolver",
    "QuoteResolver",
    "RiskSignal",
    "SourceCandidate",
    "SourceProfile",
    "SourceRelation",
    "SourceResolver",
    "SourceRiskProfiler",
    "SourceSnapshot",
    "TemporalFinding",
    "TemporalResolver",
    "find_cited_sources",
    "insufficient",
    "keyword_overlap",
    "locate_excerpt",
    "parse_rating_from_title",
    "silence_is_meaningful",
    "within_developing_window",
]
