"""Public API contract (M41).

The shape both clients consume. Frozen early and deliberately: the Android client is
built in parallel against this, so a change here after Day 1 is a versioned contract
change, not an edit.

Two structural properties are worth stating because they are enforced by the types
rather than by review:

  - **`advisories` is a top-level field, never an item inside `evidence`.** They are
    different models with no shared base, so there is no assignment that would
    typecheck. An advisory cannot arrive in the evidence list by accident.
  - **A decisive status carries citations.** `ClaimResponse` validates it, so a
    response object asserting `CONTRADICTED` with an empty evidence list cannot be
    constructed at all.

Everything the interface needs to be honest travels in the payload: what was checked,
what was skipped and why, when the evidence was retrieved, and the receipt link.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    Action,
    ClaimStatus,
    ClaimType,
    Direction,
    EvidenceKind,
    Importance,
    Method,
    Severity,
    SourceRisk,
    SyntheticSignal,
    Tier,
    Verdict,
)

# 1.1 adds verdict, confidence, summary, per-claim confidence and explanation, and
# per-source credibility. Additive: every 1.0 field is still present and unchanged.
CONTRACT_VERSION = "1.1"


# ------------------------------------------------------------------------ requests


class VerifyRequest(BaseModel):
    """A text or URL submission.

    Exactly one of `url` or `text`. Accepting both would leave the service choosing
    which one the user meant, and the wrong guess produces a confident answer about
    content nobody submitted.
    """

    model_config = ConfigDict(extra="forbid")

    url: str | None = None
    text: str | None = Field(default=None, max_length=50_000)
    language: str | None = None
    mode: str = Field(default="fast", pattern="^(fast|deep)$")
    consent_to_process_media: bool = False
    # "Check again": skip the stored verdict and check from scratch.
    recheck: bool = False

    @model_validator(mode="after")
    def _exactly_one_input(self) -> Self:
        if bool(self.url) == bool(self.text):
            raise ValueError("supply exactly one of 'url' or 'text'")
        return self


class ReviewLabelRequest(BaseModel):
    """A reviewer's judgement, recorded beside the machine's (M43)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        pattern="^(SUPPORTED|CONTRADICTED|MISLEADING_CONTEXT|UNVERIFIED|OUT_OF_SCOPE)$"
    )
    reviewer: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=4_000)


# ----------------------------------------------------------------------- responses


class SourceAnchorResponse(BaseModel):
    """Where in the cited source the excerpt sits, so a reader can find it."""

    model_config = ConfigDict(frozen=True)

    char_start: int | None = None
    char_end: int | None = None
    paragraph_index: int | None = None
    page_number: int | None = None


class InputAnchorResponse(BaseModel):
    """Where in the submission the claim was made."""

    model_config = ConfigDict(frozen=True)

    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None
    frame_start_ms: int | None = None


class MatchBasisResponse(BaseModel):
    """The metric behind a match and the threshold it was judged against.

    Exposed rather than hidden: it is what lets a reader recompute `match_quality`
    instead of trusting it, and what makes a disputed finding checkable.
    """

    model_config = ConfigDict(frozen=True)

    metric: str
    value: float
    threshold: float


class EvidenceResponse(BaseModel):
    """One citable finding. Everything here points at something fetched."""

    model_config = ConfigDict(frozen=True)

    id: str
    tier: Tier
    kind: EvidenceKind
    direction: Direction
    method: Method
    finding: str
    citation_url: str
    snapshot_id: str
    source_excerpt: str
    source_anchor: SourceAnchorResponse
    match_basis: MatchBasisResponse
    match_quality: str
    publisher: str | None = None
    input_anchor: InputAnchorResponse | None = None
    observed_at: datetime | None = None
    # HIGH, MEDIUM or LOW, from the curated publisher list. Absent on a source that
    # predates the relevance check.
    credibility: str | None = None


class AdvisoryResponse(BaseModel):
    """A Tier E signal. Structurally not evidence and never inside the evidence list.

    `excluded_note` travels with every item so no client has to remember to render
    the caveat — the disclaimer is part of the data, not part of the design system.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    provider: str
    signal: SyntheticSignal
    note: str
    score: float | None = None
    excluded_note: str = "Forensic signal — not used in this verdict."


class ComponentResponse(BaseModel):
    """One contributor to the strength score, with its own explanation."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    explanation: str
    # The citations this component was computed from, so a reader can tap a strength
    # row through to the sources behind it (PLAN 1.7.7). Empty for components that
    # rest on no specific citation (a conflict penalty, an absent-evidence term).
    citations: tuple[str, ...] = ()


class StrengthResponse(BaseModel):
    """The explainable score. Not a probability, and not a model confidence."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    band: str
    components: tuple[ComponentResponse, ...] = ()
    advisory_excluded: tuple[str, ...] = ()
    version: str


class ClaimResponse(BaseModel):
    """One claim's outcome.

    The validator below is the contract half of the ledger-completeness invariant:
    a decisive status without evidence cannot be serialised, so the API cannot emit
    what the engine already refuses to produce.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    claim_type: ClaimType
    status: ClaimStatus
    severity: Severity
    importance: Importance
    reason: str
    rule_id: str
    rule_version: str
    strength: StrengthResponse
    evidence: tuple[EvidenceResponse, ...] = ()
    # 50-97 when the claim was decided, None when it was not.
    confidence: int | None = None
    # One or two plain sentences on what the sources show, in the claim's language.
    explanation: str | None = None

    @model_validator(mode="after")
    def _decisive_status_carries_citations(self) -> Self:
        if self.status.is_decisive and not self.evidence:
            raise ValueError(
                f"claim {self.id} reports {self.status} with no evidence; a decisive "
                "status without a citation is the one thing this API must never emit"
            )
        return self


class SkippedCheckResponse(BaseModel):
    """Something that could not be checked, named so the answer can be read correctly."""

    model_config = ConfigDict(frozen=True)

    check: str
    reason: str


class MediaProvenanceResponse(BaseModel):
    """What content credentials said, including that there were none."""

    model_config = ConfigDict(frozen=True)

    present: bool
    valid: bool = False
    signer: str | None = None
    summary: str


class RecurrenceResponse(BaseModel):
    """How often this has been verified before, and under what captions (M39)."""

    model_config = ConfigDict(frozen=True)

    times_seen: int = 0
    first_verified_at: datetime | None = None
    distinct_captions: int = 0
    languages: tuple[str, ...] = ()
    summary: str


class VerifyResponse(BaseModel):
    """The full result.

    `retrieved_at` is required. A verdict shown without saying when its evidence was
    gathered is a claim about the present made from evidence about the past.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str
    contract_version: str = CONTRACT_VERSION
    # What a person is told: TRUE, FALSE, MISLEADING or UNCONFIRMED, with how sure the
    # sources make us and one plain sentence on why. Always derived from `action`, so
    # the two cannot disagree; `action` stays for clients that already read it.
    verdict: Verdict = Verdict.UNCONFIRMED
    confidence: int | None = None
    summary: str | None = None
    action: Action
    action_reason: str
    rule_version: str
    claims: tuple[ClaimResponse, ...] = ()

    # Separate from every evidence list, at the top level, by construction.
    advisories: tuple[AdvisoryResponse, ...] = ()

    source_risk: SourceRisk = SourceRisk.UNKNOWN
    media_provenance: MediaProvenanceResponse | None = None
    recurrence: RecurrenceResponse | None = None

    skipped: tuple[SkippedCheckResponse, ...] = ()
    completeness_note: str | None = None

    receipt_url: str | None = None
    retrieved_at: datetime
    from_cache: bool = False
    elapsed_ms: int = 0

    @property
    def is_complete(self) -> bool:
        return not self.skipped


class AcceptedResponse(BaseModel):
    """202 for video, which cannot finish inside the synchronous budget."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    contract_version: str = CONTRACT_VERSION
    status: str = "processing"
    poll_url: str
    estimated_seconds: int = 30


class ReceiptResponse(BaseModel):
    """A tamper-evident receipt and the outcome of checking it."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    case_id: str
    evidence_digest: str
    signature: str
    issued_at: datetime
    rule_version: str
    action: str
    evidence_count: int
    receipt_version: str
    verified: bool
    verification_reason: str
    disclaimer: str


class ReviewItemResponse(BaseModel):
    """A queued case (M43). Both records travel together, always."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    case_id: str
    reason: str
    context: str
    machine_status: str | None = None
    human_label: str | None = None
    reviewer: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class ErrorResponse(BaseModel):
    """A failure the client can act on.

    `retryable` distinguishes "this input is wrong" from "try again shortly", which
    is the difference between a client showing a correction and a client showing a
    spinner.
    """

    model_config = ConfigDict(frozen=True)

    error: str
    detail: str
    retryable: bool = False
    request_id: str | None = None


def evidence_to_response(item: Any) -> EvidenceResponse:
    """Project a domain Evidence onto the wire model.

    Typed loosely on purpose so this module imports no domain model it does not
    serialise — the contract stays readable as a contract.
    """
    return EvidenceResponse(
        id=item.id,
        tier=item.tier,
        kind=item.kind,
        direction=item.direction,
        method=item.method,
        finding=item.finding,
        citation_url=item.citation_url,
        snapshot_id=item.snapshot_id,
        source_excerpt=item.source_excerpt,
        source_anchor=SourceAnchorResponse(
            char_start=item.source_anchor.char_start,
            char_end=item.source_anchor.char_end,
            paragraph_index=item.source_anchor.paragraph_index,
            page_number=item.source_anchor.page_number,
        ),
        match_basis=MatchBasisResponse(
            metric=item.match_basis.metric,
            value=item.match_basis.value,
            threshold=item.match_basis.threshold,
        ),
        match_quality=item.match_quality.value,
        publisher=item.publisher,
        observed_at=item.observed_at,
        credibility=(item.credibility.value if getattr(item, "credibility", None) else None),
    )


def advisory_to_response(item: Any) -> AdvisoryResponse:
    return AdvisoryResponse(
        id=item.id,
        provider=item.provider,
        signal=item.signal,
        note=item.note,
        score=item.score,
        excluded_note=item.excluded_note,
    )
