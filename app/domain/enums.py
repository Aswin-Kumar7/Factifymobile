"""The value set the system can produce (M05).

Every enumeration here is a contract: it appears in the API response, in the schema's
CHECK constraints, and in the verdict rules. Adding a value is a change to all three.

Sourced from codexplan.md §2 (trust dimensions), §3 (evidence contract) and §5A
(claim types, relation labels).
"""

from __future__ import annotations

from enum import StrEnum


class ClaimStatus(StrEnum):
    """What the cited evidence says about one specific assertion.

    The boundary between the two decisive values is defined in §9 and implemented in
    the verdict engine: `CONTRADICTED` when the asserted proposition itself is false,
    `MISLEADING_CONTEXT` when the proposition is true but its framing is not.
    """

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    MISLEADING_CONTEXT = "MISLEADING_CONTEXT"
    UNVERIFIED = "UNVERIFIED"

    @property
    def is_decisive(self) -> bool:
        """A decisive status may never ship with an empty evidence list."""
        return self in _DECISIVE_STATUSES


_DECISIVE_STATUSES = frozenset(
    {ClaimStatus.SUPPORTED, ClaimStatus.CONTRADICTED, ClaimStatus.MISLEADING_CONTEXT}
)


class MediaProvenance(StrEnum):
    """What is known about a media object's origin — not whether a claim is true."""

    PROVENANCE_FOUND = "PROVENANCE_FOUND"
    RECYCLED_OR_MISATTRIBUTED = "RECYCLED_OR_MISATTRIBUTED"
    UNKNOWN = "UNKNOWN"


class SyntheticSignal(StrEnum):
    """Positive provenance, or a non-decisive forensic signal.

    `ADVISORY_SUSPICION` is the only value a detector can produce, and it reaches the
    user through the advisory panel, never through a verdict.
    """

    CONFIRMED_BY_PROVENANCE = "CONFIRMED_BY_PROVENANCE"
    ADVISORY_SUSPICION = "ADVISORY_SUSPICION"
    NO_SIGNAL = "NO_SIGNAL"


class SourceRisk(StrEnum):
    """Risk indicators about a publisher — never proof that a claim is false."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class Action(StrEnum):
    """The user-facing decision, rolled up from every claim in the case."""

    SAFE_TO_SHARE = "SAFE_TO_SHARE"
    SHARE_WITH_CONTEXT = "SHARE_WITH_CONTEXT"
    SHARE_WITH_CORRECTION = "SHARE_WITH_CORRECTION"
    DO_NOT_SHARE = "DO_NOT_SHARE"
    WAIT_AND_RECHECK = "WAIT_AND_RECHECK"
    SEND_TO_REVIEW = "SEND_TO_REVIEW"


class ClaimType(StrEnum):
    """Atomic claim types (§5A). `OPINION` is labelled and never fact-checked."""

    EVENT = "EVENT"
    STATISTIC = "STATISTIC"
    ATTRIBUTION = "ATTRIBUTION"
    QUOTE = "QUOTE"
    IDENTITY = "IDENTITY"
    MEDIA = "MEDIA"
    PREDICTION = "PREDICTION"
    OPINION = "OPINION"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Importance(StrEnum):
    HEADLINE = "HEADLINE"
    MAIN_THESIS = "MAIN_THESIS"
    SUPPORTING_DETAIL = "SUPPORTING_DETAIL"
    BACKGROUND = "BACKGROUND"


class CoverageExpectation(StrEnum):
    """How widely a claim would be reported if true.

    Captured at extraction because corroboration cannot interpret silence without it:
    a national claim absent from the corpus is meaningful, a local one is not.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOCAL = "LOCAL"


class Tier(StrEnum):
    """Evidence tiers A-D only.

    Tier E is deliberately absent. It is not a tier of evidence — it is a different
    type entirely (`Advisory`), so there is no value here that could carry it into
    the verdict engine.
    """

    A = "A"  # validated content credential — provenance only
    B = "B"  # dated source, archive capture, strong media match
    C = "C"  # published ClaimReview
    D = "D"  # corroboration clusters, attribution, source-risk signals


class EvidenceKind(StrEnum):
    FACT_CHECK = "fact_check"
    DATED_SOURCE = "dated_source"
    MEDIA_MATCH = "media_match"
    PROVENANCE = "provenance"
    SOURCE_RISK = "source_risk"
    CORROBORATION = "corroboration"
    ATTRIBUTION = "attribution"
    QUOTE = "quote"


class Direction(StrEnum):
    """What an evidence item does to the claim it is attached to."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUALIZES = "contextualizes"
    RISK_SIGNAL = "risk_signal"


class MatchQuality(StrEnum):
    """Derived from a recorded metric and threshold — never written by a model."""

    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


class Relation(StrEnum):
    """The label every retrieved item carries (§5A step 8).

    `INSUFFICIENT` is a correct outcome, not a failure: it is what a source that
    cannot be located, fetched, anchored and cited produces.
    """

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXTUALIZES = "CONTEXTUALIZES"
    NOT_RELEVANT = "NOT_RELEVANT"
    INSUFFICIENT = "INSUFFICIENT"


class Method(StrEnum):
    """How an evidence item was produced.

    The method determines whether the item can ever be decisive — see
    `app.domain.evidence.can_be_decisive`, which implements the validators table
    in §3.
    """

    EXACT_HASH = "exact_hash"
    NEAR_DUPLICATE_VERIFIED = "near_duplicate_verified"
    EMBEDDING_SIMILARITY = "embedding_similarity"
    CLAIM_REVIEW = "claim_review"
    OFFICIAL_SOURCE = "official_source"
    MATCHED_PAGE_DATE = "matched_page_date"
    ARCHIVE_CAPTURE = "archive_capture"
    SEARCH_SNIPPET = "search_snippet"
    DOMAIN_AGE = "domain_age"
    C2PA_VALIDATION = "c2pa_validation"
    ORIGIN_CLUSTER_COUNT = "origin_cluster_count"
