"""Evidence and advisory (M05).

These are two different types, and that is the point. The verdict engine's signature
accepts `Evidence` only, so passing an advisory signal is a type error rather than a
policy violation someone has to notice in review. Nothing here is convenience: it is
invariant 1 made structural.

Three rules are enforced at construction, so an invalid object cannot exist:

  - an `Evidence` without a citation, snapshot, excerpt and anchor is not
    constructible (invariant 4);
  - `match_quality` is *derived* from the recorded `match_basis`, so it is
    reproducible by a reviewer and cannot be authored by a model (invariant 5);
  - methods that can never be decisive are marked as such, so the engine cannot be
    handed a search snippet dressed up as a citation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    Credibility,
    Direction,
    EvidenceKind,
    MatchQuality,
    Method,
    SyntheticSignal,
    Tier,
)

# The validators table from codexplan.md §3. A method absent from this set produces
# candidates, never conclusions: an embedding distance on its own, a search-result
# snippet nobody fetched, a domain-age signal about the publisher rather than the
# claim.
_DECISIVE_METHODS = frozenset(
    {
        Method.EXACT_HASH,
        Method.NEAR_DUPLICATE_VERIFIED,
        Method.CLAIM_REVIEW,
        Method.OFFICIAL_SOURCE,
        Method.MATCHED_PAGE_DATE,
        Method.ARCHIVE_CAPTURE,
        Method.C2PA_VALIDATION,
        Method.ORIGIN_CLUSTER_COUNT,
        # The page was fetched, read and quoted verbatim — exactly what SEARCH_SNIPPET
        # is excluded for lacking. The quote is verified against the fetched text
        # before the relation is kept, so a finding that reaches here is anchored.
        Method.PASSAGE_ENTAILMENT,
    }
)


# How a passage that establishes only a narrower version of a claim is recorded:
# the start of its match metric. Context, never support - "Tamil Nadu pays Rs 5,000
# to 1.3 crore women" does not establish "the government pays every woman Rs 5,000 a
# month" - and what the rule engine calls misleading when credible sources agree.
NARROWER_SCOPE = "passage_narrower"


# How relevant the reader must rate a passage, 0-1, before it can decide anything.
# It was 0.0, so every passage cleared it: one the reader itself rated 0.1 relevant
# was a MODERATE match and could carry a verdict. At 0.5, below half-relevant is WEAK
# (context at most), 0.5-0.7 MODERATE, and 0.7 up STRONG (see derive_match_quality).
READING_RELEVANCE_THRESHOLD = 0.5


# The match metric of a fact-check's rating read from the page the person shared: the
# page's own ClaimReview markup names the claim it rates, so the claim is that claim
# and there is nothing further to read (`app/sources/factcheck.py`).
SHARED_REVIEW = "shared_claim_review"


def is_shared_review(metric: str) -> bool:
    """Whether a match metric records the shared fact-check's own rating."""
    return metric == SHARED_REVIEW


def is_narrower_scope(metric: str) -> bool:
    """Whether a match metric records a narrower version of the claim."""
    return metric.startswith(NARROWER_SCOPE)


def can_be_decisive(method: Method) -> bool:
    """Whether evidence from this method may drive a decisive status.

    Embedding similarity alone is candidate generation. A search snippet must be
    fetched and anchored before it is evidence. Domain age is a source-risk signal
    and never a statement about a claim.
    """
    return method in _DECISIVE_METHODS


class MatchBasis(BaseModel):
    """The recorded metric behind a match, and the threshold it was judged against.

    Storing both is what lets a reviewer recompute `match_quality` rather than trust
    it, and what turns threshold calibration into a testable artifact instead of a
    number buried in a prompt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    value: float
    threshold: float

    @property
    def margin(self) -> float:
        """How far past the threshold the observation sits."""
        return self.value - self.threshold

    @property
    def clears_threshold(self) -> bool:
        return self.value >= self.threshold


def derive_match_quality(basis: MatchBasis) -> MatchQuality:
    """Compute match quality from the recorded metric. Deterministic and total.

    A comfortable margin past the threshold is STRONG, a bare pass is MODERATE, and
    anything short of the threshold is WEAK. The bands are arithmetic on numbers that
    were written down, so two people reading the same evidence object reach the same
    answer.
    """
    if not basis.clears_threshold:
        return MatchQuality.WEAK
    span = max(1.0 - basis.threshold, 1e-9)
    if basis.margin >= 0.4 * span:
        return MatchQuality.STRONG
    return MatchQuality.MODERATE


class SourceAnchor(BaseModel):
    """Where in the cited source the excerpt was found."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paragraph_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Self:
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError("char_end precedes char_start")
        return self


class InputAnchor(BaseModel):
    """Where in the user's input the finding applies — a frame, a page, a span."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    paragraph_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    frame_start_ms: int | None = None
    frame_end_ms: int | None = None


class Evidence(BaseModel):
    """One citable finding. The only type the verdict engine accepts.

    Every field that could carry an unaccountable judgement is either absent or
    derived. There is deliberately no `confidence` field: a free-text confidence has
    no defined author, and if a model can write it then model confidence has entered
    the evidence contract through a side door.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    claim_id: str
    tier: Tier
    kind: EvidenceKind
    direction: Direction
    method: Method

    finding: str = Field(min_length=1)
    citation_url: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    source_excerpt: str = Field(min_length=1)
    source_anchor: SourceAnchor

    match_basis: MatchBasis
    match_quality: MatchQuality

    publisher: str | None = None
    # The headline of the page the excerpt came from, when the fetch found one.
    # Carried so the source check reads a quoted sentence the way a person
    # does - under its headline - rather than stripped of it.
    title: str | None = None
    # When that page was published, when known. Shown to the source check beside the
    # headline, so a page about an earlier event of the same kind can be told apart.
    published_on: date | None = None
    input_anchor: InputAnchor | None = None
    provider: str | None = None
    provider_version: str | None = None
    observed_at: datetime | None = None
    # Set once the source has been checked against the claim; see
    # `app/sources/verification.py`. None means nobody has weighed it yet.
    credibility: Credibility | None = None

    @model_validator(mode="after")
    def _match_quality_is_derived_not_asserted(self) -> Self:
        """Reject any quality that does not follow from the recorded basis.

        This is what makes invariant 5 real. A caller may supply the value, but only
        the value the metric implies — so the field stays reproducible and no
        component can quietly upgrade its own evidence.
        """
        derived = derive_match_quality(self.match_basis)
        if self.match_quality is not derived:
            raise ValueError(
                f"match_quality {self.match_quality} does not follow from match_basis "
                f"(metric={self.match_basis.metric}, value={self.match_basis.value}, "
                f"threshold={self.match_basis.threshold} implies {derived})"
            )
        return self

    @classmethod
    def build(cls, *, match_basis: MatchBasis, **fields: Any) -> Evidence:
        """Construct with the quality derived, which is the normal path.

        Callers record what they measured; they do not get to say how good it was.
        """
        return cls(
            match_basis=match_basis, match_quality=derive_match_quality(match_basis), **fields
        )

    @property
    def is_decisive_capable(self) -> bool:
        """Whether this item may drive a decisive status.

        Requires both a method that can conclude and a quality that clears its
        threshold — a weak match from a decisive method is still only a candidate.
        """
        return can_be_decisive(self.method) and self.match_quality is not MatchQuality.WEAK


class Advisory(BaseModel):
    """A Tier E signal. Structurally not evidence, and never an input to a verdict.

    This class shares no base with `Evidence` on purpose: there is no supertype that
    a function could accept, so `decide(evidence=[...])` cannot be handed one of
    these by mistake, and no refactor can make it possible without deleting this
    comment first.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    provider: str
    signal: SyntheticSignal
    note: str = Field(min_length=1)
    score: float | None = None
    provider_version: str | None = None
    artifact_ref: str | None = None
    observed_at: datetime | None = None

    @property
    def excluded_note(self) -> str:
        """The label rendered beside this signal wherever it appears."""
        return "Forensic signal — not used in this verdict."
