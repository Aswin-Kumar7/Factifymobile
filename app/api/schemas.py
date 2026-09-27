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

from datetime import date, datetime
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
    Technique,
    Tier,
    Verdict,
)

# 1.1 adds verdict, confidence, summary, per-claim confidence and explanation, and
# per-source credibility. Additive: every 1.0 field is still present and unchanged.
# 1.2 adds `image_reading`: what was read from an uploaded picture. Additive too.
# 1.3 adds, per claim, `input_anchor` (where the claim sits in the submitted text) and
# `technique` (how a false or misleading claim misleads), and on the result an inline
# `receipt`, so the seal shows without a second call; and progress events for a check
# the app follows by `request_id`. Additive: a 1.2 client ignores all of it. See
# docs/contract-changelog.md.
CONTRACT_VERSION = "1.3"


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
    # When the page itself says it was published, and its headline, when known (1.3).
    # A source card showed `observed_at`, the day we read it, as if it were the date
    # of an article two years older.
    published_on: date | None = None
    title: str | None = None


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
    # Whether the web was searched for this claim - "searched", "not_searched",
    # "timed_out" or "unavailable" - and how many pages were read for it. None on
    # cases stored before this was recorded.
    search: str | None = None
    sources_looked_at: int | None = None
    # Where the claim sits in what was submitted, so the app underlines the words
    # themselves. Offsets are into the submitted text for text; for a link or a file,
    # into the text read from it. None when the claim was not located (1.3).
    input_anchor: InputAnchorResponse | None = None
    # How a false or misleading claim misleads, for the lesson the app shows beside it.
    # Only ever on a CONTRADICTED or MISLEADING_CONTEXT claim (1.3).
    technique: Technique | None = None

    @model_validator(mode="after")
    def _decisive_status_carries_citations(self) -> Self:
        if self.status.is_decisive and not self.evidence:
            raise ValueError(
                f"claim {self.id} reports {self.status} with no evidence; a decisive "
                "status without a citation is the one thing this API must never emit"
            )
        return self

    @model_validator(mode="after")
    def _technique_only_on_a_refuted_claim(self) -> Self:
        # A technique describes how something misleads. Named on a supported or
        # unconfirmed claim it would call a true or undecided claim a manipulation.
        if self.technique is not None and self.status not in (
            ClaimStatus.CONTRADICTED,
            ClaimStatus.MISLEADING_CONTEXT,
        ):
            raise ValueError(
                f"claim {self.id} is {self.status}; a technique is named only for a "
                "contradicted or misleading claim"
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


class ImageReadingResponse(BaseModel):
    """What was read from an uploaded picture, shown beside the verdict about it.

    The claims were extracted from `text`, so a person can see exactly what was
    checked - and catch a misread before trusting the verdict built on it.
    `description` is the model's account of what the image shows: context, never
    evidence, and never checked.
    """

    model_config = ConfigDict(frozen=True)

    text: str = ""
    description: str | None = None
    # NEWS_ARTICLE, SOCIAL_POST, CHAT_MESSAGE, TV_GRAPHIC, POSTER, DOCUMENT, PHOTO,
    # MEME or OTHER.
    kind: str | None = None
    # The outlet, channel or account the image carries, as written on it.
    publisher: str | None = None
    language: str | None = None


class CredentialsResponse(BaseModel):
    """What the file's content credentials say (C2PA), or that it has none."""

    model_config = ConfigDict(frozen=True)

    # valid | untrusted (intact, but signed by nobody on a trust list checked) |
    # invalid | none | unavailable (not read)
    status: str
    signer: str | None = None
    # The file says a trained model made or composited it - from its credentials, or
    # from its metadata when it has none. What the file says, not a finding of ours.
    declares_ai: bool = False
    digital_source: str | None = None
    generator: str | None = None


class EarlierCopyResponse(BaseModel):
    """The oldest dated appearance of the picture found online."""

    model_config = ConfigDict(frozen=True)

    url: str
    publisher: str | None = None
    published_at: datetime
    # How long before this check it was already online.
    days_before: int | None = None
    # A small copy served from our own address, never the third-party image itself.
    thumbnail_url: str | None = None


class HistoryResponse(BaseModel):
    """Where the picture has appeared before (reverse image search)."""

    model_config = ConfigDict(frozen=True)

    # found | none | not_checked
    status: str
    pages: int = 0
    dated: int = 0
    earliest: EarlierCopyResponse | None = None


class DetectorResponse(BaseModel):
    """An AI-image detector's estimates, 0-1. Advisory: never in a verdict."""

    model_config = ConfigDict(frozen=True)

    # checked | not_checked
    status: str
    generated: float | None = None
    # Only when there was a face to judge.
    face_swap: float | None = None


class EditingResponse(BaseModel):
    """The forensic view: descriptive signals, never scored, never in a verdict."""

    model_config = ConfigDict(frozen=True)

    # checked | not_checked
    status: str
    uneven_noise: bool = False
    spectral_peaks: bool = False


class MediaReportResponse(BaseModel):
    """The picture checks: what can be said about the upload itself (1.3).

    Beside the verdict, never inside it: the verdict is about what the picture's text
    claims and rests on cited sources. See app/media/report.py.
    """

    model_config = ConfigDict(frozen=True)

    kind: str  # image | video
    credentials: CredentialsResponse
    history: HistoryResponse
    detector: DetectorResponse
    editing: EditingResponse
    # For a video: how many still frames were checked.
    frames: int | None = None


class QuoteLocationResponse(BaseModel):
    """Where the quoted sentence sits in the paragraphs returned."""

    model_config = ConfigDict(frozen=True)

    text: str
    paragraph_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class SourceReaderResponse(BaseModel):
    """A cited passage in its article: the paragraph and its neighbours (1.3).

    Never the whole article - the publisher's page is where it is read. `complete` is
    false when the page could not be opened now, or no longer carries the passage;
    `paragraphs` is then the quote alone and `limitations` says why.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    domain: str
    publisher: str | None = None
    headline: str | None = None
    published_at: datetime | None = None
    read_minutes: int | None = None
    # The article's picture, served from our own address.
    image_url: str | None = None
    paragraphs: tuple[str, ...] = ()
    quote: QuoteLocationResponse
    match_basis: MatchBasisResponse | None = None
    credibility: str | None = None
    tier: Tier
    direction: Direction
    complete: bool = False
    limitations: tuple[str, ...] = ()


class ReceiptSummaryResponse(BaseModel):
    """The receipt behind a result, checked when the result was sent (1.3).

    Enough for the seal: the id, whether it verified against the evidence stored now,
    and when it was issued. `/v1/receipts/{id}` still gives the whole receipt.
    """

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    verified: bool
    issued_at: datetime


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

    # For an uploaded image: its text and what it shows. None for everything else.
    image_reading: ImageReadingResponse | None = None
    # For an uploaded picture or video: the checks of the upload itself (1.3).
    media_report: MediaReportResponse | None = None

    receipt_url: str | None = None
    # The receipt itself, checked as the result was sent. None when none was issued.
    receipt: ReceiptSummaryResponse | None = None
    # The `X-Request-ID` the app sent, when it sent one: the id it follows this
    # check's progress by, at `/v1/cases/{request_id}/events` (1.3).
    request_id: str | None = None
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
        published_on=getattr(item, "published_on", None),
        title=getattr(item, "title", None),
    )


def media_report_to_response(report: Any, *, thumbnails: str) -> MediaReportResponse:
    """Project a `MediaReport` (app/media/report.py) onto the wire.

    Statuses, not sentences: the app words them in the reader's language.
    """
    from app.domain.enums import SyntheticSignal
    from app.media.report import days_before

    credentials = report.credentials
    if credentials.present and credentials.valid:
        status = "valid"
    elif credentials.present and credentials.untrusted_signer:
        status = "untrusted"
    elif credentials.present:
        status = "invalid"
    elif (credentials.reason or "").startswith(("unavailable", "unreadable")):
        status = "unavailable"
    else:
        status = "none"

    history = report.history
    earliest = history.oldest
    if history.pages:
        history_status = "found"
    elif history.reason == "no matching pages found":
        history_status = "none"
    else:
        history_status = "not_checked"

    synthetic = report.synthetic
    editing = report.editing
    # Forensic advisory ids read "adv:<signal>:<artifact>".
    suspicious = {
        advisory.id.split(":")[1]
        for advisory in editing.advisories
        if advisory.signal is SyntheticSignal.ADVISORY_SUSPICION
    }
    return MediaReportResponse(
        kind=report.kind,
        credentials=CredentialsResponse(
            status=status,
            signer=credentials.signer,
            declares_ai=credentials.declares_ai,
            digital_source=credentials.digital_source,
            generator=credentials.generator,
        ),
        history=HistoryResponse(
            status=history_status,
            pages=len(history.pages),
            dated=len(history.instances),
            earliest=(
                EarlierCopyResponse(
                    url=earliest.url,
                    publisher=earliest.publisher,
                    published_at=earliest.published_at,
                    days_before=days_before(earliest),
                    thumbnail_url=(
                        f"{thumbnails}{report.earliest_thumbnail}"
                        if report.earliest_thumbnail
                        else None
                    ),
                )
                if earliest is not None
                else None
            ),
        ),
        detector=DetectorResponse(
            status="checked" if synthetic.checked else "not_checked",
            generated=synthetic.generated,
            face_swap=synthetic.face_swap,
        ),
        editing=EditingResponse(
            status="checked" if editing.rendered else "not_checked",
            uneven_noise="noise" in suspicious,
            spectral_peaks="spectrum" in suspicious,
        ),
        frames=report.frames,
    )


def claim_anchor_response(anchor: Any) -> InputAnchorResponse | None:
    """Where a claim sits in the submission, or None when it was never located.

    Takes a domain `ClaimAnchor` or a stored `claim_anchor` row. An anchor that only
    names a paragraph gives the app nothing to underline, so it is not sent.
    """

    def read(name: str) -> Any:
        return anchor.get(name) if isinstance(anchor, dict) else getattr(anchor, name, None)

    located = InputAnchorResponse(
        char_start=read("char_start"),
        char_end=read("char_end"),
        page_number=read("page_number"),
        frame_start_ms=read("frame_start_ms"),
    )
    if located == InputAnchorResponse():
        return None
    return located


def advisory_to_response(item: Any) -> AdvisoryResponse:
    return AdvisoryResponse(
        id=item.id,
        provider=item.provider,
        signal=item.signal,
        note=item.note,
        score=item.score,
        excluded_note=item.excluded_note,
    )
