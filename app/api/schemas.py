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
# 1.8 adds `input_read`: what was read from the input, part by part, and what could
# not be - with the answer held back (`verdict_withheld`) when what was missed could
# decide it. Also `media_reports` for a post's other pictures, `skipped[].kind`, and
# the request's `accept_partial`. Additive: every 1.7 field is unchanged.
CONTRACT_VERSION = "1.8"


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
    # Accepted and not used: the app sends its interface language. The words under a
    # verdict are written in the language of the claim they explain (app/verdict/
    # explain.py), from the stored evidence, and served again from the cache to
    # everyone who checks the same thing; the app writes its own words around them.
    language: str | None = None
    # "background": answered at once with a case id (202) and checked while the app
    # follows its progress - every claim, with the time that takes. What the app uses
    # (1.4). "deep" is the name it had before, kept so an older app still works.
    # "fast": answered in this one request, inside the time a request can hold.
    mode: str = Field(default="fast", pattern="^(fast|deep|background)$")
    consent_to_process_media: bool = False
    # "Check again": skip the stored verdict and check from scratch.
    recheck: bool = False
    # "Check what was read" (1.8): check a post or a page that could be read only in
    # part, instead of holding the answer back. The answer then says it was checked
    # from part of the input, and is never TRUE.
    accept_partial: bool = False

    @model_validator(mode="after")
    def _exactly_one_input(self) -> Self:
        if bool(self.url) == bool(self.text):
            raise ValueError("supply exactly one of 'url' or 'text'")
        return self


class CorrectionTextRequest(BaseModel):
    """Which language the message to the chat is written in (1.3)."""

    model_config = ConfigDict(extra="forbid")

    # English, Hindi, or one of the ten newer languages (app/extraction/language.py).
    language: str = Field(default="en", pattern="^(en|hi|bn|mr|te|ta|gu|ur|kn|or|ml|pa)$")


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


class EarlierMediaResponse(BaseModel):
    """The earlier copy a media match points at, for the side-by-side (1.3, 4.5).

    `thumbnail_url` is on our own address, and only on a fresh result whose picture
    checks fetched that page: the upload itself is never kept, so a case read back
    later carries the date, publisher and match but no image.
    """

    model_config = ConfigDict(frozen=True)

    thumbnail_url: str | None = None
    published_at: date | None = None
    publisher: str | None = None
    # 0-1: how closely the two pictures match (1.0 for the identical file).
    similarity: float | None = None


def earlier_media_of(
    kind: str, similarity: float, published_on: date | None, publisher: str | None
) -> EarlierMediaResponse | None:
    """The side-by-side for a media match; nothing for any other kind of evidence."""
    if str(kind) != "media_match":
        return None
    return EarlierMediaResponse(
        published_at=published_on, publisher=publisher, similarity=round(similarity, 4)
    )


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
    # A media match's earlier copy, for the side-by-side on the answer (1.3).
    earlier_media: EarlierMediaResponse | None = None


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
    # A claim not made in English, as one self-contained English sentence (1.4): what
    # its words mean in full - "NASA launched Chandrayaan-3" for "নাসা এটি উৎক্ষেপণ
    # করেছিল" (NASA launched it). What its sources were found and read against.
    in_full: str | None = None
    # The language the claim was made in (1.3 addition, 2026-09-28): en, hi, or one of
    # bn mr te ta gu ur kn or ml pa. Lets the app offer the note to the chat in it.
    language: str | None = None
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
    # What kind of gap it is (1.8): "reading" (part of the input could not be read;
    # `input_read.gaps` says what), "deadline" (the check ran out of time), "provider"
    # (an outside service did not answer) or "other". Lets a client say the time ran
    # out only when it did.
    kind: str = "other"


class ReadPartResponse(BaseModel):
    """One thing read from the input, as it was read (1.8).

    `checked` says whether the part is in the text claims were found in. Since
    2026-10-02 that includes Factify's description of what a picture or video shows
    (`picture_description`, `video_description`, labelled "(described by Factify)"),
    where the claim a picture makes is often found; a part left out of that text - a
    wordless photograph's description, any part of an answer that was withheld - is
    `checked: false`.
    """

    model_config = ConfigDict(frozen=True)

    # message | post_text | quoted_post | title | description | article |
    # linked_article | picture_text | picture_description | transcript |
    # on_screen_text | video_description | document_text
    kind: str
    # "Post by … on X, 2 Oct 2026", "Text in picture 1 of 2", "Said in the video".
    label: str | None = None
    text: str
    checked: bool
    # How it was read: x.syndication, instagram.embed, gemini.youtube, whisper,
    # frames.ocr, ocr.local, ocr.hosted, fetched, vendor_extract, pdf.text, pasted…
    route: str
    # False when this part was itself read only in part; `gaps` says why.
    complete: bool = True
    note: str | None = None
    # The picture this part was read from, on our own address
    # (/v1/media/thumbnails/<key>). Kept for an hour; a client hides it on a 404.
    media_url: str | None = None
    # Where this part's text sits in the text claims were found in: the same offsets
    # as `claims[].input_anchor`. None for a part that is not in it.
    char_start: int | None = None
    char_end: int | None = None
    # For speech: how many seconds of the video were heard, of how many.
    seconds_read: int | None = None
    seconds_total: int | None = None
    language: str | None = None


class ReadGapResponse(BaseModel):
    """Something that could not be read (1.8).

    `code` is what a client words in its own language: headline_only,
    text_truncated, post_unavailable, login_required, not_supported, picture_unread,
    video_unread, speech_unread, cut_off, pages_unread, too_large, needs_background,
    reader_unavailable, first_picture_only, article_truncated, description_unread,
    linked_page_unread or page_unread. `detail` is one English sentence, for a code it
    does not know.
    """

    model_config = ConfigDict(frozen=True)

    part: str
    code: str
    detail: str
    # Whether what was missed could decide the answer. A blocking gap keeps the
    # verdict from TRUE (`checked_partially`), or holds it back when nothing that
    # could be checked was read (`verdict_withheld`).
    blocking: bool


class InputReadResponse(BaseModel):
    """What Factify read from the input, and what it could not (1.8).

    The answer is only ever about what was read. This says what that was, so a
    person can see the part of a post that was checked - and the part that was not -
    before trusting a verdict built on it.
    """

    model_config = ConfigDict(frozen=True)

    # text | link | social_post | image | pdf | video
    kind: str
    # x | instagram | youtube | facebook, for a social post.
    platform: str | None = None
    url: str | None = None
    author: str | None = None
    handle: str | None = None
    published_at: datetime | None = None
    parts: tuple[ReadPartResponse, ...] = ()
    gaps: tuple[ReadGapResponse, ...] = ()
    # Limits that are not about reading: "YouTube does not let Factify download the
    # video, so its AI, face-swap and voice checks did not run."
    limits: tuple[str, ...] = ()
    # Everything was read: no gap of any kind.
    complete: bool = True
    # Not checked: nothing that could be checked was read, so no verdict was given.
    # `verdict` is UNCONFIRMED, with no claims, and `summary` says why.
    verdict_withheld: bool = False
    # Checked from what could be read: something that could decide the answer was
    # not read (a blocking gap), and the rest was checked all the same - as the
    # person asked ("Check what was read"), or as the server does by default
    # (`reading.WITHHOLD_WHEN_BLOCKED`). The verdict is never TRUE then.
    checked_partially: bool = False

    @model_validator(mode="after")
    def _complete_says_whether_anything_was_missed(self) -> Self:
        # A reading that calls itself complete while naming a gap, or incomplete
        # without naming one, would show a person a panel that contradicts itself.
        if self.complete == bool(self.gaps):
            raise ValueError(
                "input_read.complete must be true exactly when no gap was recorded "
                f"(complete={self.complete}, gaps={len(self.gaps)})"
            )
        return self

    @model_validator(mode="after")
    def _withheld_or_partly_checked_not_both(self) -> Self:
        if self.verdict_withheld and self.checked_partially:
            raise ValueError("an answer cannot be both withheld and checked from part of it")
        if self.checked_partially and not any(item.blocking for item in self.gaps):
            raise ValueError("checked_partially is set only when a blocking gap was checked past")
        return self


class MediaProvenanceResponse(BaseModel):
    """What content credentials said, including that there were none."""

    model_config = ConfigDict(frozen=True)

    present: bool
    valid: bool = False
    signer: str | None = None
    summary: str


class SourceProfileResponse(BaseModel):
    """The website a submitted link comes from (`app/sources/source_profile.py`).

    Itemised observations, never a score, and never a finding about the claims.
    """

    model_config = ConfigDict(frozen=True)

    domain: str
    trusted: bool
    trust: str | None = None
    fact_checker: bool = False
    level: SourceRisk = SourceRisk.UNKNOWN
    findings: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    domain_age_days: int | None = None


class RecurrenceResponse(BaseModel):
    """How often this has been verified before, and under what captions (M39)."""

    model_config = ConfigDict(frozen=True)

    times_seen: int = 0
    first_verified_at: datetime | None = None
    distinct_captions: int = 0
    languages: tuple[str, ...] = ()
    summary: str


class SpeechResponse(BaseModel):
    """What is said in an uploaded video, read on our own server (1.5)."""

    model_config = ConfigDict(frozen=True)

    text: str
    # The language it was heard in, as Whisper names it ("hi", "ta", "en").
    language: str | None = None
    # Only the start of a long video was read.
    cut_off: bool = False


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
    # Added in 1.5: why it was not checked - off (not set up on this server) or
    # failed (it was asked and did not answer). Absent when it was checked.
    why: str | None = None


class DetectorResponse(BaseModel):
    """An AI-image detector's estimates, 0-1. Advisory: never in a verdict."""

    model_config = ConfigDict(frozen=True)

    # checked | not_checked
    status: str
    # Added in 1.5: why it was not checked - text_card (mostly flat colour: a text
    # card or a screenshot, whose words are checked instead), too_small, unreadable,
    # off (no detector on this server) or failed. Absent when it was checked.
    why: str | None = None
    generated: float | None = None
    # Only when there was a face to judge.
    face_swap: float | None = None
    # Added in 1.3 (2026-09-28), all optional: our own detectors.
    # A second AI-picture model; both must agree before "likely_ai".
    second_opinion: float | None = None
    # likely_ai | unclear | no_sign - never "real".
    agreement: str | None = None
    # How many faces the face model judged; absent when it did not run.
    faces: int | None = None
    # A video's sound: likelihood the voice was made by a speech generator.
    voice: float | None = None
    # Added in 1.5: whether that is past the voice model's own line - the app does
    # not hold the model's threshold, so it is told. None when there was no voice.
    machine_voice: bool | None = None
    # Added in 1.5: whether a face in a video is past the face model's line for
    # video. None when no face was judged.
    face_swapped: bool | None = None
    # These detectors ran on our own server. Other checks (the hosted text reader,
    # reverse image search) may still send the picture to their providers.
    on_server: bool = False


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


class CorrectionTextResponse(BaseModel):
    """A short, polite message to send back with a correction, and its links (1.3).

    From templates, never a model: it says what the answer says, names the source
    and quotes it. The app lets the person edit it before sending.
    """

    model_config = ConfigDict(frozen=True)

    message: str
    links: tuple[str, ...] = ()


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
    # For a submitted link: what is known about its website.
    source_profile: SourceProfileResponse | None = None
    media_provenance: MediaProvenanceResponse | None = None
    recurrence: RecurrenceResponse | None = None

    skipped: tuple[SkippedCheckResponse, ...] = ()
    completeness_note: str | None = None

    # For an uploaded image: its text and what it shows. None for everything else.
    image_reading: ImageReadingResponse | None = None
    # For an uploaded picture or video: the checks of the upload itself (1.3). For a
    # post with pictures, the checks of its first picture.
    media_report: MediaReportResponse | None = None
    # For a post with more than one picture: the checks of pictures 2 to n, in order
    # (1.8). `media_report` stays picture 1, so an older client still shows it.
    media_reports: tuple[MediaReportResponse, ...] = ()
    # For an uploaded video: what is said in it, which is checked as a message is (1.5).
    speech: SpeechResponse | None = None
    # What was read from the input, part by part, and what could not be (1.8). None
    # on cases stored before it was recorded.
    input_read: InputReadResponse | None = None

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
    """202 for a check run in the background: a video, or any check asked for that way."""

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
        earlier_media=earlier_media_of(
            item.kind,
            item.match_basis.value,
            getattr(item, "published_on", None),
            item.publisher,
        ),
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
            why=_history_why(history.reason) if history_status == "not_checked" else None,
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
            why=None if synthetic.checked else _detector_why(synthetic.reason),
            generated=synthetic.generated,
            face_swap=synthetic.face_swap,
            second_opinion=synthetic.second_opinion,
            agreement=synthetic.outcome,
            faces=synthetic.faces,
            voice=synthetic.voice,
            machine_voice=(
                synthetic.voice >= synthetic.voice_at if synthetic.voice is not None else None
            ),
            face_swapped=(
                synthetic.face_swap >= synthetic.face_swap_at
                if synthetic.face_swap is not None
                else None
            ),
            on_server=synthetic.on_server,
        ),
        editing=EditingResponse(
            status="checked" if editing.rendered else "not_checked",
            uneven_noise="noise" in suspicious,
            spectral_peaks="spectrum" in suspicious,
        ),
        frames=report.frames,
    )


def _detector_why(reason: str | None) -> str:
    """Why the AI-picture detector did not judge a picture, as a code the app words.

    The app said only "Not checked", so a text card the detector skips on purpose
    read the same as a detector that broke (2026-09-29).
    """
    text = (reason or "").casefold()
    if "flat colour" in text:
        return "text_card"
    if "too small" in text:
        return "too_small"
    if "could not be read" in text:
        return "unreadable"
    if text.startswith("unavailable"):
        return "off"
    return "failed"


def _history_why(reason: str | None) -> str:
    """Why reverse image search did not run: not set up here, or it failed.

    A provider refusing us outright - Google Vision answers 403 until billing is on
    for its project - is "not set up", not a passing failure.
    """
    text = (reason or "").casefold()
    if text.startswith("unavailable") or "403" in text or "401" in text:
        return "off"
    return "failed"


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
