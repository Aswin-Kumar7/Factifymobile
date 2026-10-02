"""Verification endpoints (M41).

Maps the contract in `schemas` onto the orchestrator. Deliberately thin: routing,
projection and status codes. Every rule about what may be returned lives either in
the orchestrator or in the response models, so there is no policy here that could
drift away from the policy elsewhere.

The internal ingestion trigger lives here too because it shares the app, but it is
authenticated with a shared secret and is never publicly routable — an unconfigured
deployment denies every trigger rather than accepting anonymous ones.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pypdf.errors import PdfReadError

from app.api.accounts import charge, check_cost, release_credit, require_credit, signed_in
from app.api.admin import _staff
from app.api.schemas import (
    AcceptedResponse,
    AdvisoryResponse,
    ClaimResponse,
    ComponentResponse,
    CorrectionTextRequest,
    CorrectionTextResponse,
    DetectorResponse,
    EvidenceResponse,
    ImageReadingResponse,
    InputReadResponse,
    MediaReportResponse,
    QuoteLocationResponse,
    ReadGapResponse,
    ReadPartResponse,
    ReceiptResponse,
    ReceiptSummaryResponse,
    ReviewItemResponse,
    ReviewLabelRequest,
    SkippedCheckResponse,
    SourceProfileResponse,
    SourceReaderResponse,
    SpeechResponse,
    StrengthResponse,
    VerifyRequest,
    VerifyResponse,
    advisory_to_response,
    claim_anchor_response,
    evidence_to_response,
    media_report_to_response,
)
from app.cache.keys import text_hash
from app.domain.claim import Claim, ClaimAnchor
from app.domain.enums import ClaimType, Importance, Severity, SourceRisk
from app.extraction.claimreview import ClaimReview, read_claim_reviews
from app.extraction.claims import ExtractedClaims
from app.extraction.language import detect
from app.extraction.local_ocr import LocalFirstOcr
from app.extraction.model_wire import PDF_MIME
from app.extraction.ocr import READER_VERSION, OcrOutcome, looks_designed
from app.extraction.pdf import PdfRejected, first_pages
from app.extraction.pdf import extract as extract_pdf
from app.extraction.reading import (
    NOTHING_TO_CHECK_IN_PART_SUMMARY,
    NOTHING_TO_CHECK_SUMMARY,
    WITHHELD_SUMMARY,
    Composed,
    Gap,
    GapCode,
    PartKind,
    Reading,
    ReadingPolicy,
    ReadPart,
    gap,
    linked_article_label,
    picture_text_label,
    served_policy,
    withheld_without_claims,
)
from app.extraction.web import extract as extract_article
from app.extraction.web import headline_and_summary
from app.intake.normalizer import (
    InputType,
    IntakeRejected,
    NormalisedIntake,
    normalise_text,
    normalise_upload,
    normalise_url,
)
from app.intake.social_urls import Platform, PostRef, is_video_route, recognise
from app.knowledge.registry import authenticate_trigger
from app.media.composed import (
    PICTURE_DESCRIBED,
    SAID_IN_VIDEO,
    TEXT_IN_VIDEO,
    VIDEO_DESCRIBED,
    compose,
    described,
)
from app.media.frame_text import FramesText, local_reader, read_frames_text
from app.media.sheet import contact_sheet, pick_for_sheet
from app.media.speech import SpeechOutcome, read_speech
from app.media.video import (
    DEFAULT_MAX_SECONDS,
    READ_SECONDS,
    ExtractedVideo,
    FramesRead,
    Keyframe,
    KeyframeExtractor,
    clock,
)
from app.observability.logging import event
from app.observability.middleware import REQUEST_ID_HEADER
from app.orchestration.background import BackgroundChecks, set_phase
from app.orchestration.correction import correction_message
from app.orchestration.pipeline import (
    BACKGROUND_CEILING_SECONDS,
    BACKGROUND_MIN_READING_SECONDS,
    BACKGROUND_SECONDS,
    SkippedCheck,
    VerificationResult,
    claim_progress,
)
from app.orchestration.progress import CheckProgress, current_progress, valid_key
from app.orchestration.review import HumanLabel
from app.orchestration.summary import case_summary
from app.security.fetcher import FetchResult, SecureFetcher
from app.security.patience import PATIENT, current_patience
from app.sources.base import check_seconds, current_reference_date
from app.sources.credibility import SourceCredibility
from app.sources.factcheck import (
    SHARED_CLAIM_ID,
    FactCheckRecord,
    SharedReview,
    current_shared_review,
)
from app.sources.outlets import outlet_name
from app.sources.reader import SourceViews, read_source
from app.sources.source_profile import SourceReport, profile_link, rdap_fetcher
from app.sources.verification import page_key
from app.verdict.technique import technique_for

logger = logging.getLogger("factify.api.verify")

router = APIRouter(prefix="/v1", tags=["verification"])
internal = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def get_orchestrator(request: Request) -> object:
    """Resolve the orchestrator from app state.

    Raises 503 rather than 500 when it is absent: a service booted without a
    database is unavailable, not broken, and the distinction matters to a client
    deciding whether to retry.
    """
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="verification is not available; the service is not fully configured",
        )
    return orchestrator


async def extract_claims_for(request: Request, intake: NormalisedIntake) -> ExtractedClaims:
    """Pull checkable claims out of the submission.

    Upstream of the orchestrator because it has its own cache and its own provider
    budget — one model call per document, and a cache hit costs none.

    An unconfigured extractor returns no claims *and a reason*, which the caller
    attaches to the response. That distinction is the point: "we could not read this"
    and "we read it and found nothing to check" are different answers, and collapsing
    them would let a configuration gap render as a clean bill of health.
    """
    extracted, _ = await read_and_extract(request, intake)
    return extracted


async def read_and_extract(
    request: Request, intake: NormalisedIntake
) -> tuple[ExtractedClaims, Reading]:
    """Read a pasted message or a submitted link, and pull its checkable claims out.

    Beside the claims, what was read and what could not be (contract 1.8): the
    message, the page's headline and article, the page a message links to, each a
    part, and a gap for each thing missed - a page read only by its headline, an
    article longer than is read, a linked page that could not be opened.

    The parts carry no labels, so the text claims are found in is exactly the text
    this read before 1.8: the message, then the linked page, a blank line apart.
    """
    reading = Reading(
        kind="link" if intake.input_type is InputType.URL else "text",
        url=intake.primary.source_url if intake.input_type is InputType.URL else None,
    )
    pipeline = getattr(request.app.state, "claim_pipeline", None)
    if pipeline is None:
        return ExtractedClaims(reason="claim extraction is not configured"), reading

    text = intake.primary.text or ""
    language = intake.language.language.value

    # A forward that carries a link: "Must read! https://..." The message was checked
    # and the article it points at was never opened, so the substance of most shared
    # news went unread. The article is read and checked alongside the message, which
    # keeps whatever the message itself claims.
    reviewed: tuple[str, ...] = ()
    reviews: tuple[ClaimReview, ...] = ()
    # The linked page's address, and where its text starts in what is extracted.
    page_url: str | None = None
    page_start = 0
    if intake.input_type is InputType.TEXT:
        reading = reading.plus(parts=(ReadPart(kind=PartKind.MESSAGE, text=text, route="pasted"),))
        link = _first_link(text)
        if link is not None:
            page = await _read_linked_article(request, link)
            if page is None:
                reading = reading.plus(
                    gaps=(
                        gap(
                            "linked_page",
                            GapCode.LINKED_PAGE_UNREAD,
                            "The page the message links to could not be read; the message "
                            "was checked on its own words.",
                        ),
                    )
                )
            else:
                page_start = len(text) + 2
                text = f"{text}\n\n{page.text}"
                reviewed = page.reviewed
                reviews = page.reviews
                page_url = link
                reading = reading.plus(
                    parts=(
                        ReadPart(
                            kind=PartKind.LINKED_ARTICLE,
                            text=page.text,
                            route=page.route,
                            complete=page.partial is None and not page.truncated,
                            note=f"read from {link}",
                        ),
                    ),
                    gaps=_page_gaps(page, part="linked_article", linked=True),
                )

    if not text.strip() and intake.input_type is InputType.URL:
        # A submitted link carries no text of its own — normalisation is local and
        # deliberately does not fetch. Read the page here, the same way a retrieved
        # source is read (M16), so "check this link" checks the article instead of
        # abstaining on an empty body. This was the gap that made every URL a no-op.
        page = await _read_linked_article(request, intake.primary.source_url or "")
        if page is None:
            return ExtractedClaims(reason="the linked page could not be read"), reading.plus(
                gaps=(
                    gap(
                        "page",
                        GapCode.PAGE_UNREAD,
                        "Factify could not read this page: not its article, and not even "
                        "its headline. Paste the text of the page instead.",
                    ),
                )
            )
        text = page.text
        reviewed = page.reviewed
        reviews = page.reviews
        page_url = intake.primary.source_url
        reading = reading.plus(parts=_page_parts(page), gaps=_page_gaps(page, part="article"))
        # What "on Monday" in its claims means (`current_reference_date`).
        current_reference_date.set(page.published)
        # The article's own language, detected on its body — not the URL's, which
        # was detected on an empty string and is always the default.
        language = detect(text).language.value

    if not text.strip():
        return ExtractedClaims(reason="no readable text in this submission"), reading

    set_phase("finding_claims")
    # Keyed by the text read, not by the address: a page read anew - its article this
    # time, where last time only its headline - is found new claims in. For a message
    # alone this is the message's own identity, as before.
    content_hash = text_hash(text)
    extracted: ExtractedClaims = await pipeline.extract(
        text,
        content_hash=content_hash,
        input_kind=intake.input_type.value,
        language=language,
    )
    shared = _shared_fact_check(reviews, page_url)
    restated: tuple[Claim, ...] = ()
    if shared is not None and reviewed and extracted.claims:
        # Set aside only when the fact-check's own rating answers the claim it
        # examines (`_answered_by_the_fact_check`). On a page it cannot answer by - a
        # desk not on the fact-checker list, a roundup rating several claims, a rating
        # it cannot read - the debunked claim, which extraction makes the HEADLINE, is
        # what is searched and checked: set aside, only the findings were left, and one
        # supported finding answered TRUE for a debunk (2026-10-03 review, finding 6).
        before = extracted.claims
        extracted = _without_the_reviewed_claim(extracted, reviewed)
        restated = tuple(claim for claim in before if claim not in extracted.claims)

    if shared is not None:
        extracted = _answered_by_the_fact_check(
            extracted,
            shared,
            restated=restated,
            source=text,
            page_start=page_start,
            content_hash=content_hash,
            input_kind=intake.input_type.value,
        )
        current_shared_review.set(shared)
    return extracted, reading


def _page_parts(page: LinkedPage) -> tuple[ReadPart, ...]:
    """A submitted page's parts: its headline, then its article - or its summary, when
    the headline and summary were all that could be read.

    Bare, with no labels: the two compose to `page.text`, the text claims have always
    been found in. A page built from its text alone is one article part.
    """
    if page.title is None and not page.body:
        return (ReadPart(kind=PartKind.ARTICLE, text=page.text, route=page.route),)
    parts: list[ReadPart] = []
    if page.title and page.title.strip():
        parts.append(ReadPart(kind=PartKind.TITLE, text=page.title, route=page.route))
    if page.body.strip():
        parts.append(
            ReadPart(
                kind=PartKind.DESCRIPTION if page.partial else PartKind.ARTICLE,
                text=page.body,
                route=page.route,
                complete=page.partial is None and not page.truncated,
            )
        )
    return tuple(parts)


def _page_gaps(page: LinkedPage, *, part: str, linked: bool = False) -> tuple[Gap, ...]:
    """What a page's reading missed: its article, read only by its headline and
    summary, or its tail, past `_MAX_ARTICLE_CHARS`."""
    whose = "The page the message links to" if linked else "The page"
    if page.partial:
        if linked:
            return (
                gap(
                    part,
                    GapCode.LINKED_PAGE_UNREAD,
                    f"{whose} gave only its headline and summary, not the article.",
                ),
            )
        return (
            gap(
                part,
                GapCode.HEADLINE_ONLY,
                "Only the page's headline and summary could be read, not the full article.",
            ),
        )
    if page.truncated:
        return (
            gap(
                part,
                GapCode.ARTICLE_TRUNCATED,
                f"{whose} is long: its first {_MAX_ARTICLE_CHARS:,} characters of "
                f"{page.total_chars:,} were read and checked.",
            ),
        )
    return ()


# The website of the link read for this request, set where the page is read
# (`_read_linked_article`) and put on the answer by `_checked`.
_LINK_PROFILE: ContextVar[SourceReport | None] = ContextVar("_LINK_PROFILE", default=None)
_RDAP: SecureFetcher | None = None


def _rdap() -> SecureFetcher:
    global _RDAP
    if _RDAP is None:
        _RDAP = rdap_fetcher()
    return _RDAP


def _profile_response(report: SourceReport | None) -> SourceProfileResponse | None:
    if report is None:
        return None
    return SourceProfileResponse(
        domain=report.domain,
        trusted=report.trusted,
        trust=report.trust,
        fact_checker=report.fact_checker,
        level=report.level,
        findings=report.findings,
        warnings=report.warnings,
        domain_age_days=report.domain_age_days,
    )


async def _profile_url(request: Request, url: str) -> SourceReport | None:
    """A link's website, for an answer served from the cache (no page was read)."""
    reader = getattr(request.app.state, "url_reader", None)
    html = ""
    if reader is not None:
        fetched = await reader.fetch(url, provider="url_intake")
        if isinstance(fetched, FetchResult):
            html = fetched.text
    try:
        return await profile_link(url, html=html, credibility=_credibility(), rdap=_rdap())
    except Exception:
        logger.exception("the link's website could not be profiled")
        return None


def _credibility() -> SourceCredibility:
    """The source list, read once."""
    global _CREDIBILITY
    if _CREDIBILITY is None:
        _CREDIBILITY = SourceCredibility.load()
    return _CREDIBILITY


_CREDIBILITY: SourceCredibility | None = None


def _shared_fact_check(
    reviews: tuple[ClaimReview, ...], page_url: str | None
) -> SharedReview | None:
    """The rating a shared fact-check gives, when the page is one we can answer by.

    A page of a listed fact-checker whose markup rates one claim, in a word we read
    (`FactCheckRecord.verdict`). Not a roundup rating several claims - which of them
    the person meant cannot be told - and not a news site's markup, whose "rating" no
    fact-checker put their name to.
    """
    if not reviews or not page_url or not _credibility().is_fact_checker(page_url):
        return None
    rated: dict[str, FactCheckRecord] = {}
    for review in reviews:
        record = FactCheckRecord(
            claim_text=review.claim_reviewed,
            normalized_text=review.claim_reviewed.casefold(),
            # The page the person shared, as its own page: the markup's own URL field
            # is sometimes another address for it.
            url=page_url,
            rating=review.rating,
            # The outlet by its name: BOOM's markup names the writer as its author.
            publisher=outlet_name(urlsplit(page_url).hostname or "") or review.publisher,
            published_at=review.published_at,
            retrieved_at=datetime.now(UTC),
        )
        if record.verdict is not None:
            rated.setdefault(record.normalized_text, record)
    if len(rated) != 1:
        return None
    return SharedReview(
        record=next(iter(rated.values())),
        certified=_credibility().is_certified_fact_checker(page_url),
    )


# Which of a shared fact-check's findings is its main one: the first by rank.
_RANK = {
    Importance.HEADLINE: 0,
    Importance.MAIN_THESIS: 1,
    Importance.SUPPORTING_DETAIL: 2,
    Importance.BACKGROUND: 3,
}


def _answered_by_the_fact_check(
    extracted: ExtractedClaims,
    shared: SharedReview,
    *,
    restated: tuple[Claim, ...],
    source: str,
    page_start: int,
    content_hash: str,
    input_kind: str,
) -> ExtractedClaims:
    """A shared fact-check's claims: the claim it examines, and its main finding.

    The claim it examines is answered by its rating, cross-checked against what other
    fact-checkers rated (`current_shared_review`). Of what it finds, only the main
    finding is checked, as a detail: a certified fact-checker's reading of a video
    against the original footage is more than our search of the open web can match,
    and each finding checked on its own came back Unconfirmed and outvoted the rating
    (2026-09-28). A message forwarded with the link keeps its own claims.
    """
    record = shared.record
    like = restated[0] if restated else None
    # Its type from a restatement that says what happened, never from one that only
    # describes the fake: "a letter attributed to Nehru says ..." set aside as a QUOTE
    # made the examined claim a "misattributed quote" (fake-7, 2026-10-03).
    typed = next(
        (c for c in restated if c.claim_type in (ClaimType.EVENT, ClaimType.STATISTIC)), None
    )
    at = source.casefold().find(record.claim_text.casefold())
    anchor = ClaimAnchor(
        input_kind=input_kind,
        content_hash=content_hash,
        # Named in the page's ClaimReview markup, and in its text too when it is there.
        section="claim_review",
        char_start=at if at >= 0 else None,
        char_end=at + len(record.claim_text) if at >= 0 else None,
        paragraph_index=None if at >= 0 else 0,
    )
    examined = Claim(
        id=SHARED_CLAIM_ID,
        text=record.claim_text,
        normalized_text=" ".join(record.claim_text.casefold().split()),
        claim_type=typed.claim_type if typed is not None else ClaimType.EVENT,
        severity=(
            Severity.CRITICAL
            if like is not None and like.severity is Severity.CRITICAL
            else Severity.HIGH
        ),
        importance=Importance.HEADLINE,
        entities=like.entities if like is not None else (),
        language=detect(record.claim_text).language.value,
        anchor=anchor,
    )

    on_page = [c for c in extracted.claims if (c.anchor.char_start or 0) >= page_start]
    from_message = [c for c in extracted.claims if c not in on_page]
    main = min(on_page, key=lambda c: _RANK[c.importance], default=None)
    kept: list[Claim] = [examined]
    if main is not None:
        kept.append(
            main.model_copy(
                update={
                    "importance": Importance.SUPPORTING_DETAIL,
                    "severity": (
                        Severity.HIGH if main.severity is Severity.CRITICAL else main.severity
                    ),
                }
            )
        )
    kept.extend(from_message)
    event(
        logger,
        "shared fact-check answered by its rating",
        module="api.verify",
        outcome="ok",
        certified=shared.certified,
        findings_not_checked=max(0, len(on_page) - 1),
    )
    return replace(
        extracted,
        claims=tuple(kept),
        discarded=(
            *extracted.discarded,
            *(c.text[:120] for c in on_page if c is not main),
        ),
    )


def _in_full(claim: Claim) -> str | None:
    """The self-contained English of a claim made in another language, when it says
    more than a word-for-word reading would show; None for an English claim."""
    english = claim.english_text.strip()
    if not english or (claim.language or "en") == "en" or english == claim.text.strip():
        return None
    return english


# Words a claim must share with the claim a fact-check examines to be that claim
# restated - a viral post's caption, quoted - rather than one of its findings.
_RESTATES = 0.6
# Latin, digits and the Indian scripts, less the danda; "\w" splits a Hindi word at
# its vowel signs.
_WORD = re.compile(r"[a-z0-9ऀ-ॣ०-ൿ؀-ۿݐ-ݿ]{3,}")


def _without_the_reviewed_claim(
    extracted: ExtractedClaims, reviewed: tuple[str, ...]
) -> ExtractedClaims:
    """A shared fact-check's claims, less the claim it examines.

    A fact-check quotes the post it debunks, and the post is not something it asserts.
    Vishvas News' check of "Sitharaman went to meet her father" gave the claim "X user
    Promila shared a video captioned that the Finance Minister met her father", which
    Alt News' check of the caption then contradicted - and a fact-check that holds up
    came back "partly true" (2026-09-28). The page names the claim it examines in its
    own ClaimReview markup; a claim that restates it is set aside, and what the page
    finds is what is checked.
    """
    reviewed_words = [set(_WORD.findall(text.casefold())) for text in reviewed]

    def restates(claim: Claim) -> bool:
        said = set(_WORD.findall(f"{claim.text} {claim.english_text}".casefold()))
        return any(
            words and len(words & said) / len(words) >= _RESTATES for words in reviewed_words
        )

    kept = tuple(claim for claim in extracted.claims if not restates(claim))
    if len(kept) == len(extracted.claims) or not kept:
        return extracted
    event(
        logger,
        "claim a shared fact-check examines set aside",
        module="api.verify",
        outcome="ok",
        set_aside=len(extracted.claims) - len(kept),
    )
    return replace(
        extracted,
        claims=kept,
        discarded=(*extracted.discarded, "the claim the shared fact-check examines"),
    )


# A link inside a message: with a scheme, or starting "www." as people type them.
_LINK_IN_TEXT = re.compile(r"(?:https?://|www\.)[^\s<>\"'()]+", re.IGNORECASE)


def _first_link(text: str) -> str | None:
    """The first followable link in a message, or None.

    Trailing punctuation is the sentence's, not the link's. A link that normalisation
    would refuse — localhost, a bare scheme — is ignored rather than read.
    """
    match = _LINK_IN_TEXT.search(text)
    if match is None:
        return None
    link = match.group(0).rstrip(".,;:!?'\"")
    if link.lower().startswith("www."):
        link = f"https://{link}"
    try:
        return normalise_url(link).primary.source_url
    except IntakeRejected:
        return None


# Longest article body sent to extraction. A news story fits well within this; a
# very long reference page is truncated to its opening, where the headline claims
# sit, and the answer says so (`GapCode.ARTICLE_TRUNCATED`). It was 6,000, which cut
# a long-form report or a YouTube video's captions mid-story (2026-10-02).
_MAX_ARTICLE_CHARS = 12000

# Below this, what our own fetch got is a bot wall, a consent page or a paywall stub,
# not the article — the same line the search path draws (`websearch._MIN_ARTICLE_CHARS`).
# Reuters answered a link with "Please enable JS and disable any ad blocker", 43
# characters, and that was accepted as the article: nothing was extracted, the vendor
# reader that returns the full 6,000-character story was never asked, and the app
# showed "Unconfirmed" for a report an hour old.
_MIN_LINK_ARTICLE_CHARS = 600


@dataclass(frozen=True, slots=True)
class LinkedPage:
    """What a submitted link yielded: its text, and what was missing from it."""

    text: str
    # Why this is less than the article, when it is: said in the response.
    partial: str | None = None
    # When the page is a fact-check: the claims it examines, from its own ClaimReview
    # markup. What it debunks is not what it asserts (`_without_the_reviewed_claim`).
    reviewed: tuple[str, ...] = ()
    # The day the page says it was published, when it says.
    published: date | None = None
    # Those reviews in full: the claim, the rating, who gave it (`_shared_fact_check`).
    reviews: tuple[ClaimReview, ...] = ()
    # The headline and the body `text` was made of, as read (contract 1.8).
    title: str | None = None
    body: str = ""
    # How it was read: fetched, vendor_extract, headline_summary or search_listing.
    route: str = "fetched"
    # How long the body was before it was cut to `_MAX_ARTICLE_CHARS`.
    total_chars: int = 0

    @property
    def truncated(self) -> bool:
        """Only the opening of a longer article was read."""
        return self.total_chars > _MAX_ARTICLE_CHARS


async def _read_linked_article(request: Request, url: str) -> LinkedPage | None:
    """Fetch a submitted link and return its readable article text, or None.

    Only HTML is read here: a PDF or image shared as a link is a file, and the file
    endpoint handles those. A page with no extractable body — a login wall, a
    JavaScript shell, a social-media permalink — returns None, and the caller says so
    plainly rather than presenting an empty read as "nothing to check".
    """
    reader = getattr(request.app.state, "url_reader", None)
    if reader is None or not url:
        return None

    body: str | None = None
    title: str | None = None
    published: date | None = None
    route = "fetched"
    html: str | None = None
    partial: str | None = None

    result = await reader.fetch(url, provider="url_intake")
    if isinstance(result, FetchResult):
        content_type = (result.content_type or "").lower()
        if content_type and "html" not in content_type and "xml" not in content_type:
            _log_link_read(url, route="not html", title=None, body="", total=0)
            return None

        html = result.text
        article = extract_article(html, url=url)
        if article.is_usable and len((article.body or "").strip()) >= _MIN_LINK_ARTICLE_CHARS:
            body, title = article.body, article.title
        if article.published_at is not None:
            published = article.published_at.date()

    if body is None:
        # Second rung, the same ladder a retrieved source climbs.
        #
        # One fetch was the whole of it before, so a link the publisher would not
        # serve us became "not enough evidence to decide" — a sentence about the
        # evidence, for a page nobody had read. Measured on an Olympics.com live
        # report of a result carried worldwide: the fetch raised, zero bytes came
        # back, zero claims were extracted, and the answer named the evidence rather
        # than the blocked door. The search path already pays a vendor to read pages
        # that refuse us; a link the user typed deserves the same attempt.
        body = await _vendor_read(request, url)
        route = "vendor extract"

    if not body:
        # Third rung: what the publisher shows anyone about the page — the headline
        # and summary in its head, for search engines and link previews — and failing
        # that, what the search index holds for this exact address. Never the article
        # behind a paywall; the headline and summary are usually its main claim, and
        # checking that beats telling the person nothing could be read.
        title, body = headline_and_summary(html) if html else (None, None)
        route = "page headline and summary"
        if not body:
            listed = await _search_listing(request, url)
            if listed is not None:
                title, body = listed
                route = "search listing"
        if not body:
            _log_link_read(url, route="unreadable", title=None, body="", total=0)
            return None
        partial = "only the page's headline and summary could be read, not the full article"

    # Title and body together: the headline carries the primary claim, the body the
    # rest, so even a one-paragraph story yields something to check. The body is
    # capped: extraction takes at most a handful of claims and the consequential ones
    # sit near the top, while a long page (a Wikipedia article runs to tens of
    # thousands of characters) would push one extraction call past the model's
    # per-minute token budget and come back 429.
    total = len(body or "")
    body = (body or "")[:_MAX_ARTICLE_CHARS]
    _log_link_read(url, route=route, title=title, body=body, total=total)
    parts = [part for part in (title, body) if part and part.strip()]
    reviews = tuple(
        review
        for review in read_claim_reviews(html or "", page_url=url)
        if review.claim_reviewed.strip()
    )
    if not reviews and _credibility().is_fact_checker(url):
        reviews = await _indexed_reviews(request, url)
    reviewed = tuple(review.claim_reviewed for review in reviews)
    try:
        _LINK_PROFILE.set(
            await profile_link(
                url, html=html or "", text=body or "", credibility=_credibility(), rdap=_rdap()
            )
        )
    except Exception:  # what is known about the site is a help, never a dependency
        logger.exception("the link's website could not be profiled")
    if not parts:
        return None
    return LinkedPage(
        "\n\n".join(parts),
        partial,
        reviewed,
        published,
        reviews,
        title=title if title and title.strip() else None,
        body=body if body.strip() else "",
        route=_ROUTES.get(route, route),
        total_chars=total,
    )


# How a page was read, in the words the contract uses for `parts[].route`.
_ROUTES = {
    "fetched": "fetched",
    "vendor extract": "vendor_extract",
    "page headline and summary": "headline_summary",
    "search listing": "search_listing",
}


async def _indexed_reviews(request: Request, url: str) -> tuple[ClaimReview, ...]:
    """A fact-check page's ratings as its publisher filed them with the fact-check
    index, for a page whose own markup we could not read."""
    resolver = getattr(request.app.state, "factcheck_resolver", None)
    lookup = getattr(resolver, "published_ratings", None)
    if lookup is None:
        return ()
    try:
        records = await lookup(url)
    except Exception:
        logger.exception("the fact-check index could not be asked about a shared page")
        return ()
    return tuple(
        ClaimReview(
            claim_reviewed=record.claim_text,
            rating=record.rating,
            publisher=record.publisher,
            published_at=record.published_at,
            url=record.url,
        )
        for record in records
    )


async def _search_listing(request: Request, url: str) -> tuple[str | None, str] | None:
    """The search index's title and summary for this exact page, or None."""
    resolver = getattr(request.app.state, "web_search_resolver", None)
    listing = getattr(resolver, "listing", None)
    if listing is None:
        return None
    try:
        return await listing(url)  # type: ignore[no-any-return]
    except Exception:
        return None


def _log_link_read(url: str, *, route: str, title: str | None, body: str, total: int) -> None:
    """What a submitted link actually yielded, so "did it read the article?" has an
    answer in the log: which rung read it, how much, and how the text begins."""
    event(
        logger,
        "linked page read",
        module="api.verify",
        outcome="ok" if body else "degraded",
        url=url,
        route=route,
        title=(title or "")[:160],
        chars=total,
        truncated=total > _MAX_ARTICLE_CHARS,
        opening=" ".join(body.split())[:240],
    )


async def _vendor_read(request: Request, url: str) -> str | None:
    """Ask the configured search provider for the text of a page we could not fetch.

    The licensed route, and the only one on this ladder: presenting ourselves as a
    browser to get past a publisher's block is not something this service does.
    """
    resolver = getattr(request.app.state, "web_search_resolver", None)
    extract_one = getattr(resolver, "_vendor_extract", None)
    if extract_one is None:
        return None
    try:
        return await extract_one(url) or None
    except Exception:
        return None


async def cached_full_response(
    request: Request, result: VerificationResult
) -> VerifyResponse | None:
    """The complete stored result behind a cache hit, or `None` to fall back.

    The cache payload stores the action, not the claims or the evidence, so a hit
    rendered from the payload alone is a verdict card with nothing behind it — on
    exactly the repeated content the cache exists to serve. The claims and evidence
    do exist: the ledger recorded them under the original case. Reading them back
    through `CaseReader` keeps one source of truth, and means the `case_id` in a
    cached response resolves — `/v1/cases/{id}/evidence` works on it, where the
    fresh hit's throwaway id pointed at nothing.

    `None` when the hit is not ledger-backed (older cache rows, or the original
    ledger write failed): the caller serves the thin result, which is everything
    those rows actually hold (`_thin`).
    """
    if not result.from_cache or result.source_case_id is None:
        return None

    reader = getattr(request.app.state, "case_reader", None)
    if reader is None:
        return None

    try:
        stored = await reader.get(result.source_case_id)
    except Exception:
        logger.exception("cached case could not be read; serving the thin result")
        return None

    if not isinstance(stored, VerifyResponse) or not stored.claims:
        return None

    # `retrieved_at` stays the original computation time — a cached result served
    # later is a claim about the present made from evidence about the past, and the
    # timestamp is how the interface stays honest about that. The reason comes from
    # the cache payload, which kept the original rollup wording.
    return stored.model_copy(
        update={
            "from_cache": True,
            "action": result.action,
            "verdict": result.case_decision.verdict,
            "action_reason": result.case_decision.reason,
            "elapsed_ms": result.elapsed_ms,
        }
    )


_VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".3gp", ".avi")


def _thin(result: VerificationResult) -> VerifyResponse:
    """A cache hit's thin result, under the case it was recorded as.

    The thin result used to carry the id minted for this request, a case that was
    never written: Report, the correction to send back and the source reader all
    answered 404 on it. The original case is in the ledger even when its claims could
    not be read back, so the thin result is served under that. Only a row older than
    the field has no case to name (none is reachable since the rule version moved on);
    it keeps the minted id, as before.
    """
    response = to_response(result)
    if result.source_case_id is None:
        return response
    return response.model_copy(update={"case_id": str(result.source_case_id)})


async def _from_cache(request: Request, result: VerificationResult) -> VerifyResponse | None:
    """What a cache hit is served as - in full, else thin - or None for a fresh result."""
    if not result.from_cache:
        return None
    return await cached_full_response(request, result) or _thin(result)


def _is_video(file: UploadFile) -> bool:
    """A video costs more (speech read, frames checked): known from the upload."""
    kind = (file.content_type or "").lower()
    return kind.startswith("video/") or (file.filename or "").lower().endswith(_VIDEO_SUFFIXES)


def _followed_by(request: Request) -> str | None:
    """The id the app follows this check by: the `X-Request-ID` it sent, if any.

    The same id the server logs the request under, so the stream and the logs of one
    check line up. Only a UUID is listened on; an id the server made up for itself
    is not, because nobody is following it.
    """
    sent = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
    return sent if valid_key(sent) else None


def _echo(response: VerifyResponse, key: str | None) -> VerifyResponse:
    return response if key is None else response.model_copy(update={"request_id": key})


# What a refused check is called on the progress stream; the HTTP answer says the rest.
_ERROR_CODES = {
    401: "signed_out",
    402: "no_credit",
    413: "too_large",
    422: "invalid_input",
    429: "rate_limited",
    503: "unavailable",
}


@asynccontextmanager
async def _watched(request: Request, key: str | None) -> AsyncIterator[CheckProgress | None]:
    """Publish what the check does while it runs, when the app is following it.

    Every stream ends: with `done` from the caller, or here with `error` when the check
    is refused or fails, so the Checking screen is never left waiting on silence.
    """
    bus = getattr(request.app.state, "progress_bus", None)
    if key is None or bus is None:
        yield None
        return
    watching = CheckProgress(bus, key, names=outlet_name)
    token = current_progress.set(watching)
    try:
        await watching.step("read")
        yield watching
    except HTTPException as refused:
        await watching.error(_ERROR_CODES.get(refused.status_code, "failed"))
        raise
    except asyncio.CancelledError:
        await watching.error("cancelled")
        raise
    except Exception:
        await watching.error("failed")
        raise
    finally:
        current_progress.reset(token)


async def with_receipt(request: Request, response: VerifyResponse) -> VerifyResponse:
    """The result with its receipt inline, checked now (contract 1.3).

    The app showed the seal only after a second call for the receipt; carrying it here
    saves that call. A receipt that cannot be read leaves the result as it is: the
    receipt attests to the answer, and failing to attach it is no reason to hold the
    answer back.
    """
    receipts = getattr(request.app.state, "receipt_reader", None)
    if receipts is None or response.receipt is not None:
        return response
    try:
        payload = await receipts.for_case(UUID(response.case_id))
    except Exception:
        logger.exception("receipt could not be read; the result is sent without it")
        return response
    if payload is None:
        return response
    return response.model_copy(
        update={
            "receipt": ReceiptSummaryResponse(
                receipt_id=payload["receipt_id"],
                verified=payload["verified"],
                issued_at=payload["issued_at"],
            ),
            "receipt_url": response.receipt_url or f"/v1/receipts/{payload['receipt_id']}",
        }
    )


def to_response(result: VerificationResult, *, receipt_url: str | None = None) -> VerifyResponse:
    """Project a pipeline result onto the wire contract.

    The projection is total: every claim, every citation, every skipped check. A
    field dropped here is a fact the interface cannot show, and the ones most likely
    to be dropped are precisely the uncomfortable ones.
    """
    claims = tuple(
        ClaimResponse(
            id=outcome.claim.id,
            text=outcome.claim.text,
            in_full=_in_full(outcome.claim),
            language=outcome.claim.language,
            claim_type=outcome.claim.claim_type,
            status=outcome.decision.status,
            severity=outcome.claim.severity,
            importance=outcome.claim.importance,
            reason=outcome.decision.reason,
            rule_id=outcome.decision.rule_id,
            rule_version=outcome.decision.rule_version,
            strength=StrengthResponse(
                score=outcome.strength.score,
                band=outcome.strength.band,
                components=tuple(
                    ComponentResponse(
                        name=component.name,
                        value=component.value,
                        explanation=component.detail,
                        citations=component.citations,
                    )
                    for component in outcome.strength.components
                ),
                advisory_excluded=tuple(
                    signal.provider for signal in outcome.strength.advisory_excluded
                ),
                version=outcome.strength.version,
            ),
            evidence=tuple(evidence_to_response(item) for item in outcome.evidence),
            confidence=outcome.decision.confidence,
            explanation=outcome.explanation,
            search=outcome.search,
            sources_looked_at=outcome.looked_at,
            input_anchor=claim_anchor_response(outcome.claim.anchor),
            technique=technique_for(
                outcome.decision.status,
                outcome.claim.claim_type,
                ((item.kind, item.direction) for item in outcome.evidence),
            ),
        )
        for outcome in result.claims
    )

    return VerifyResponse(
        case_id=str(result.case_id),
        verdict=result.case_decision.verdict,
        confidence=result.case_decision.confidence,
        summary=case_summary(
            result.case_decision.verdict,
            [(o.decision.status, o.claim.importance, o.explanation) for o in result.claims],
        ),
        action=result.action,
        action_reason=result.case_decision.reason,
        rule_version=result.rule_version,
        claims=claims,
        advisories=tuple(advisory_to_response(item) for item in result.advisories),
        skipped=tuple(
            SkippedCheckResponse(check=item.check, reason=item.reason, kind=item.kind)
            for item in result.skipped
        ),
        completeness_note=result.completeness_note(),
        # Offered only when one was actually issued and stored, so the link a
        # client follows can never 404.
        receipt_url=receipt_url
        or (f"/v1/receipts/{result.receipt_id}" if result.receipt_id else None),
        retrieved_at=datetime.now(UTC),
        from_cache=result.from_cache,
        elapsed_ms=result.elapsed_ms,
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify a URL or a block of text",
)
async def verify(payload: VerifyRequest, request: Request) -> VerifyResponse | JSONResponse:
    """Verify a URL or a block of text.

    With an API key, an `Idempotency-Key` header makes a retried request return the
    first answer, charged once (kept 24 hours).
    """
    idem = await _idempotency(request, payload.model_dump_json())
    if isinstance(idem, JSONResponse):
        return idem
    response = await _verify(payload, request)
    if idem is not None:
        await _remember_idempotent(request, idem, response)
    return response


async def _idempotency(
    request: Request, fingerprint_of: str
) -> tuple[str, str, str] | JSONResponse | None:
    header = request.headers.get("idempotency-key", "").strip()[:200]
    orgs = getattr(request.app.state, "orgs", None)
    if not header or orgs is None:
        return None
    await signed_in(request)
    payer = getattr(request.state, "payer", None)
    if payer is None or payer.key_id is None:
        return None
    scope = f"key:{payer.key_id}"
    fingerprint = hashlib.sha256(fingerprint_of.encode()).hexdigest()
    found = await orgs.replay(scope, header, fingerprint)
    if found is not None:
        return JSONResponse(found[1], status_code=found[0], headers={"Idempotent-Replayed": "true"})
    return scope, header, fingerprint


async def _remember_idempotent(
    request: Request, idem: tuple[str, str, str], response: VerifyResponse | JSONResponse
) -> None:
    if isinstance(response, JSONResponse):
        status_code, body = response.status_code, json.loads(bytes(response.body))
    else:
        status_code, body = 200, response.model_dump(mode="json")
    try:
        await request.app.state.orgs.remember(*idem, status_code, body)
    except Exception:
        logger.exception("could not store an idempotent response")


async def _verify(payload: VerifyRequest, request: Request) -> VerifyResponse | JSONResponse:
    """Run one synchronous verification.

    Targets 3-8 seconds. Video does not come through here — it cannot finish inside
    that budget, so it returns 202 from `/verify/file` instead of holding a request
    open and timing out somewhere less legible.

    The orchestrator is resolved in the body rather than through `Depends` on
    purpose: an `HTTPException` raised inside a dependency short-circuits before
    request-body validation runs, so a malformed request would come back 503
    "service unavailable" instead of 422. A client cannot tell those apart, and one
    of them is its own fault.
    """
    # The time budget runs from here, not from after extraction. Reading a long page
    # and extracting its claims takes ten to twenty seconds, and starting the clock
    # after that let a four-claim link run to 68 seconds against an app that waits 75.
    arrived = time.perf_counter()
    background = payload.mode in ("background", "deep")
    key = _followed_by(request)

    # A check in the background is followed by its case id, from the 202.
    async with _watched(request, None if background else key) as watching:
        # Who is asking, and whether they may: decided here, from the credit ledger.
        user = await signed_in(request)
        cost = check_cost(request)
        await require_credit(request, user, cost)

        if background:
            case_id = uuid4()
            return _in_background(
                request,
                case_id,
                lambda: _checked(payload, request, time.perf_counter(), case_id=case_id),
                user=user,
                cost=cost,
                # A post with a video is downloaded, heard and read before it is checked.
                estimated_seconds=120 if _is_video_post(payload.url) else 90,
            )

        try:
            response = await with_receipt(request, await _checked(payload, request, arrived))
        except BaseException:
            await release_credit(request)
            raise
        await _settle(request, user, cost, response)
        if watching is not None:
            await watching.done(response.case_id)
    return _echo(response, key)


def _is_video_post(url: str | None) -> bool:
    """Whether a submitted link's address says it is a video post (a reel, YouTube)."""
    ref = recognise(url) if url else None
    return ref is not None and is_video_route(ref)


def billable(response: VerifyResponse) -> bool:
    """Whether a finished check is charged.

    Not an answer held back because too little of the input could be read
    (`verdict_withheld`), nor a link or a post with no claim in it to check: neither
    was checked against anything, and the person is told to send it another way.
    """
    read = response.input_read
    if read is None:
        return True
    if read.verdict_withheld:
        return False
    return not (read.kind in ("link", "social_post") and not response.claims)


async def _settle(request: Request, user: Any, cost: int, response: VerifyResponse) -> None:
    """Charge a finished check, or give back what was held for it when it is not
    billable; then keep what was read with the case. Neither may fail the check."""
    if billable(response):
        await charge(request, user, cost, response=response)
    else:
        await release_credit(request)
    await _keep_reading(request, response)


async def _keep_reading(request: Request, response: VerifyResponse) -> None:
    """Keep what was read with the case (`case_readings`), so the answer read back
    later shows it too. Not for an answer served from the cache: its case was kept
    when it was first checked. A failure is logged and never fails the check."""
    store = getattr(request.app.state, "case_readings", None)
    if store is None or response.from_cache:
        return
    try:
        await store.put(UUID(response.case_id), response)
    except Exception:
        logger.exception("what was read could not be kept with the case")


def _in_background(
    request: Request,
    case_id: UUID,
    check: Callable[[], Awaitable[VerifyResponse]],
    *,
    user: Any,
    cost: int,
    estimated_seconds: int = 90,
) -> JSONResponse:
    """Run a check in the background and answer with its case id at once (202).

    Every claim is searched and read, with up to `BACKGROUND_SECONDS` to do it and
    patience with a busy provider, while the app shows "3 of 7 claims checked" from
    `/v1/cases/{id}` and each source from the event stream. Charged only when it
    finishes with an answer: one that fails, or that the person who started it stops
    (`DELETE /v1/cases/{id}`), costs nothing and gives back what was held for it.
    """
    runs: BackgroundChecks = request.app.state.background_checks

    async def work(progress: Any) -> VerifyResponse:
        budget = check_seconds.set(BACKGROUND_SECONDS)
        patience = current_patience.set(PATIENT)
        counting = claim_progress.set(progress)
        try:
            async with _watched(request, str(case_id)) as watching:
                try:
                    response = await with_receipt(request, await check())
                except BaseException:
                    await release_credit(request)
                    raise
                # The answer is in: from here it is charged, and can no longer be stopped.
                run = runs.get(str(case_id))
                if run is not None:
                    run.settling = True
                await _settle(request, user, cost, response)
                if watching is not None:
                    await watching.done(str(case_id))
        finally:
            claim_progress.reset(counting)
            current_patience.reset(patience)
            check_seconds.reset(budget)
        return response

    runs.start(
        str(case_id),
        work,
        owner=getattr(user, "id", None),
        on_cancel=lambda: release_credit(request),
    )
    accepted = AcceptedResponse(
        case_id=str(case_id),
        poll_url=f"/v1/cases/{case_id}",
        # An article of seven claims measures two to three minutes; a forward, one.
        estimated_seconds=estimated_seconds,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content=accepted.model_dump(mode="json")
    )


async def _checked(
    payload: VerifyRequest, request: Request, arrived: float, *, case_id: UUID | None = None
) -> VerifyResponse:
    """The check itself; `verify` above decides who may run it and records the cost."""
    get_orchestrator(request)

    try:
        intake = (
            normalise_url(payload.url, consent=payload.consent_to_process_media)
            if payload.url
            else normalise_text(payload.text or "", consent=payload.consent_to_process_media)
        )
        # A post's address pasted as a message, with a word or two of the share sheet's
        # around it, is the post: read as text it was one more page nobody could read.
        shared = _only_a_post(payload.text or "") if not payload.url else None
        if shared is not None:
            intake = normalise_url(shared, consent=payload.consent_to_process_media)
    except IntakeRejected as rejected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(rejected)
        ) from rejected

    case_id = case_id or uuid4()
    ref = _post_of(request, intake)
    if ref is not None:
        # A post on X, Instagram or YouTube: read whole - its words, its pictures, its
        # video - through the platform's own embed addresses (`app/api/post_checks.py`).
        from app.api.post_checks import checked_post

        return await checked_post(request, payload, intake, ref, case_id=case_id, arrived=arrived)
    return await checked_input(request, payload, intake, case_id=case_id, arrived=arrived)


def _post_of(request: Request, intake: NormalisedIntake) -> PostRef | None:
    """The social post a submitted link is, when this server reads that platform's
    posts; None for any other input, which is read as it always was."""
    if intake.input_type is not InputType.URL or intake.extraction_route != "url.social":
        return None
    ref = recognise(intake.primary.source_url or "")
    reader = getattr(request.app.state, "social_reader", None)
    if ref is None or reader is None or ref.platform is Platform.FACEBOOK:
        return None
    return ref if reader.handles(ref) else None


# How many words of its own a message may have and still be only a post's address:
# "Check this out", "via @app" - the share sheet's, not a claim.
_SHARE_WORDS = 3


def _only_a_post(text: str) -> str | None:
    """A social post's address, when a message is that and little more; else None."""
    link = _first_link(text)
    if link is None or recognise(link) is None:
        return None
    rest = _LINK_IN_TEXT.sub(" ", text)
    if len(_WORD.findall(rest.casefold())) > _SHARE_WORDS:
        return None
    return link


async def checked_input(
    request: Request,
    payload: VerifyRequest,
    intake: NormalisedIntake,
    *,
    case_id: UUID,
    arrived: float,
    unread: tuple[Gap, ...] = (),
) -> VerifyResponse:
    """A pasted message or a link to a page: read, its claims found, and checked.

    `unread` is what an earlier attempt to read the input missed, said beside what
    this reading misses: a social post whose platform would not show it, read here as
    a web page instead (`post_checks.checked_post`).
    """
    orchestrator = get_orchestrator(request)
    _LINK_PROFILE.set(None)

    # A repeat is answered before anything is spent on it. Extraction is a metered
    # model call — and for a link, a page fetch as well — and it used to run first,
    # so every repeat of a viral message paid for a fresh extraction only to be
    # served the stored verdict afterwards. "Check again" asks for exactly that
    # stored verdict to be replaced, so it skips the probe.
    hit = (
        None if payload.recheck else await orchestrator.cached(intake, case_id=case_id)  # type: ignore[attr-defined]
    )
    if hit is not None:
        event(
            logger,
            "verify request served",
            module="api.verify",
            outcome="ok",
            action=hit.action.value,
            claims=0,
            from_cache=True,
            elapsed_ms=hit.elapsed_ms,
        )
        served = await cached_full_response(request, hit) or _thin(hit)
        if intake.input_type is InputType.URL and intake.primary.source_url:
            report = await _profile_url(request, intake.primary.source_url)
            if report is not None:
                served = served.model_copy(
                    update={
                        "source_profile": _profile_response(report),
                        "source_risk": report.level,
                    }
                )
        return recalled(request, intake.cache_identity, served)

    extracted, reading = await read_and_extract(request, intake)
    if unread:
        reading = reading.plus(gaps=unread)
    profile = _LINK_PROFILE.get()
    shown: dict[str, Any] = (
        {"source_profile": _profile_response(profile), "source_risk": profile.level}
        if profile is not None
        else {}
    )
    composed = reading.document()
    chosen = served_policy(reading, accept_partial=payload.accept_partial)

    # A link with no claims to check is not a verdict about the link.
    #
    # It used to pass through when extraction ran cleanly and found nothing, and a
    # verification of zero claims came back "Unconfirmed" - on a Reuters bot wall and
    # on a page whose every claim failed its anchor. Unconfirmed means sources were
    # looked for; here none were. Then it was refused (422) with "try pasting the
    # text of the page", which is no advice for a video and told the person nothing
    # of what had been read. Now the answer says: a page whose missing part could hold
    # the claim is held back, saying what was missed; a page read in full, or missing
    # only what could not decide it, with nothing in it to check says exactly that
    # (`answer_without_claims`). Neither is charged.
    if not extracted.claims and intake.input_type is InputType.URL:
        response = await answer_without_claims(
            request, intake, reading, case_id=case_id, reason=extracted.reason
        )
        return response.model_copy(update=shown)

    # The pages the person submitted, which can never be evidence for themselves.
    own_pages: set[str] = set()
    if intake.primary.source_url:
        own_pages.add(page_key(intake.primary.source_url))
    embedded = (
        _first_link(intake.primary.text or "") if intake.input_type is InputType.TEXT else None
    )
    if embedded is not None:
        own_pages.add(page_key(embedded))

    set_phase("checking")
    result = await orchestrator.verify(  # type: ignore[attr-defined]
        intake,
        case_id=case_id,
        claims=list(extracted.claims),
        started_at=arrived,
        fresh=payload.recheck,
        own_pages=frozenset(own_pages),
        # A site with strong warnings can hold the answer back from "True", never
        # make a claim false (`roll_up`).
        source_risk=profile.level if profile is not None else SourceRisk.UNKNOWN,
        # What could not be read, where it could decide the answer or may be read
        # next time, keeps the run out of the cache; a gap that could decide it keeps
        # the answer from TRUE.
        noted=gaps_as_skips(noted_gaps(reading)),
        partial_input=chosen is ReadingPolicy.CHECK_PARTIALLY,
    )

    cached = await _from_cache(request, result)
    if cached is not None:
        return recalled(request, intake.cache_identity, cached.model_copy(update=shown))

    # Extraction failing is a gap in the answer, not a failure of the request. It is
    # attached so the response can say the text could not be read into claims rather
    # than presenting "nothing to check" as "nothing wrong".
    if extracted.reason:
        result.skipped.append(SkippedCheck(check="claim_extraction", reason=extracted.reason))

    event(
        logger,
        "verify request served",
        module="api.verify",
        outcome="ok",
        action=result.action.value,
        claims=len(extracted.claims),
        from_cache=result.from_cache,
        elapsed_ms=result.elapsed_ms,
        read_parts=len(reading.parts),
        read_gaps=[item.code.value for item in reading.gaps],
    )
    response = with_reading(
        to_response(result),
        reading,
        composed,
        partially=chosen is ReadingPolicy.CHECK_PARTIALLY,
    )
    remember_reading(request, intake.cache_identity, response)
    return response.model_copy(update=shown)


# A gap that may not be there next time, in what the answer rests on - a page that gave
# only its headline today, a YouTube video's captions the vendor did not return - keeps
# the answer out of the cache even when it could not decide it. A gap that will be
# there every time (a long article's tail, an album's fifth picture, a YouTube video
# nobody may download) does not; nor does a page a message or a post merely links to,
# whose own words are the answer and whose dead links would otherwise be re-checked on
# every forward. A post its platform would not show today, read as a web page instead,
# is read whole the next time the platform shows it.
_MAY_READ_NEXT_TIME = frozenset(
    {
        GapCode.HEADLINE_ONLY,
        GapCode.DESCRIPTION_UNREAD,
        GapCode.PAGE_UNREAD,
        GapCode.POST_UNAVAILABLE,
        GapCode.READER_UNAVAILABLE,
    }
)


def noted_gaps(reading: Reading) -> tuple[Gap, ...]:
    """The gaps that keep an answer out of the cache: those that could decide it, and
    those that may be read next time (`_MAY_READ_NEXT_TIME`)."""
    return tuple(item for item in reading.gaps if item.blocking or item.code in _MAY_READ_NEXT_TIME)


# The check a gap is reported under in `skipped`, by what is missing - names an older
# app already knows where it can ("image_text", "document_text").
_CHECK_OF_PART = {
    "picture_text": "image_text",
    "picture": "image_text",
    "picture_description": "image_text",
    "thumbnail": "image_text",
    "document_text": "document_text",
    "article": "linked_page",
    "page": "linked_page",
    "linked_page": "linked_page",
    "linked_article": "linked_page",
    "transcript": "speech",
    "speech": "speech",
    "video": "video",
    "on_screen_text": "video",
    "video_description": "video",
}


def gaps_as_skips(gaps: Sequence[Gap]) -> list[SkippedCheck]:
    """Each gap as the skipped check an older app shows: "post_text was not checked:
    <detail>", marked as a gap in reading (`kind="reading"`)."""
    return [
        SkippedCheck(
            check=_CHECK_OF_PART.get(item.part, "post_text"), reason=item.detail, kind="reading"
        )
        for item in gaps
    ]


def with_reading(
    response: VerifyResponse,
    reading: Reading,
    composed: Composed,
    *,
    partially: bool = False,
    withheld: bool = False,
) -> VerifyResponse:
    """The answer with what was read (`input_read`), and every gap in its skipped
    checks, marked as reading - those the pipeline was told of and the rest."""
    return response.model_copy(
        update={
            "input_read": input_read_response(
                reading, composed, partially=partially, withheld=withheld
            ),
            "skipped": _with_reading_gaps(response.skipped, gaps_as_skips(reading.gaps), ()),
        }
    )


async def answer_without_claims(
    request: Request,
    intake: NormalisedIntake,
    reading: Reading,
    *,
    case_id: UUID,
    reason: str | None = None,
    composed: Composed | None = None,
) -> VerifyResponse:
    """The answer for a link or a post in which no claim was found to check.

    When something that could decide it was not read - its article, its picture, its
    video - or nothing checkable was read at all, the claim may be in what was missed,
    and the verdict is withheld: no verdict, the gaps said, and "paste the text or
    upload the picture or video" (`WITHHELD_SUMMARY`). Otherwise there is nothing to
    fact-check, and the answer says so (`NOTHING_TO_CHECK_SUMMARY`), listing what was
    not read when something was (`NOTHING_TO_CHECK_IN_PART_SUMMARY`): a YouTube video
    nobody may download is never withheld for that alone. It used to be withheld for
    any gap, and every YouTube video has one. When finding claims failed, the answer
    says that.

    `composed` is the text claims were looked for in, for `input_read` to say which
    parts were; the reading's whole document when not given.

    Recorded as a case (the person can report it, and find it in their history), with
    nothing searched and nothing cached, and never charged (`billable`). An older app
    is told the input was not checked (`claim_extraction`), so it does not show
    "Nothing to fact-check" for a post it could not read.
    """
    withheld = withheld_without_claims(reading)
    noted = gaps_as_skips(reading.gaps)
    if withheld:
        noted.append(
            SkippedCheck(
                check="claim_extraction",
                reason="not checked: Factify could not read all of it",
                kind="reading",
            )
        )
    elif reason:
        noted.append(SkippedCheck(check="claim_extraction", reason=reason))
    result = await get_orchestrator(request).verify(  # type: ignore[attr-defined]
        intake, case_id=case_id, claims=[], fresh=True, noted=noted
    )
    language = _reading_language(reading)
    summary: str | None
    if withheld:
        summary = WITHHELD_SUMMARY.get(language, WITHHELD_SUMMARY["en"])
    elif reason:
        summary = None
    elif reading.gaps:
        summary = NOTHING_TO_CHECK_IN_PART_SUMMARY.get(
            language, NOTHING_TO_CHECK_IN_PART_SUMMARY["en"]
        )
    else:
        summary = NOTHING_TO_CHECK_SUMMARY.get(language, NOTHING_TO_CHECK_SUMMARY["en"])
    response = to_response(result)
    event(
        logger,
        "verify request served",
        module="api.verify",
        outcome="ok",
        action=result.action.value,
        claims=0,
        from_cache=False,
        verdict_withheld=withheld,
        read_parts=len(reading.parts),
        read_gaps=[item.code.value for item in reading.gaps],
        reason=reason,
    )
    response = with_reading(
        response.model_copy(update={"summary": summary, "case_id": str(case_id)}),
        reading,
        # Nothing was checked in a withheld answer: no part is said to be.
        Composed(text="")
        if withheld
        else (composed if composed is not None else reading.document()),
        withheld=withheld,
    )
    # Said even when the pipeline did not report what it was told.
    present = {(item.check, item.reason) for item in response.skipped}
    missing = tuple(
        SkippedCheckResponse(check=item.check, reason=item.reason, kind=item.kind)
        for item in noted
        if (item.check, item.reason) not in present
    )
    if not missing:
        return response
    return response.model_copy(update={"skipped": (*response.skipped, *missing)})


def _reading_language(reading: Reading) -> str:
    """The language a fixed sentence about a reading is written in: that of what was
    read in the input's own words, English when nothing was."""
    authored = _authored(reading)
    if not authored.strip():
        return "en"
    return detect(authored).language.value


@router.get(
    "/cases/{case_id}",
    response_model=VerifyResponse,
    summary="Retrieve a previously computed case",
)
async def get_case(case_id: UUID, request: Request) -> VerifyResponse | JSONResponse:
    # A check still running in the background answers with its progress, and a
    # finished one with its result, before the ledger is asked: a check that was
    # served from the cache is stored under the original case, not this one.
    runs: BackgroundChecks | None = getattr(request.app.state, "background_checks", None)
    run = runs.get(str(case_id)) if runs is not None else None
    if run is not None and runs is not None:
        if run.status == "running":
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "case_id": str(case_id),
                    "status": "processing",
                    "claims_done": run.claims_done,
                    "claims_total": run.claims_total,
                    "elapsed_seconds": runs.elapsed(run),
                    # What it is doing (1.8): reading_post, reading_pictures,
                    # reading_video, finding_claims or checking; null before it says.
                    "phase": run.phase,
                },
            )
        if run.status == "failed":
            return JSONResponse(status_code=run.error_status, content={"detail": run.error_detail})
        if run.status == "cancelled":
            return JSONResponse(
                status_code=status.HTTP_410_GONE,
                content={"detail": "this check was stopped before it finished; it cost nothing"},
            )
        return run.response  # type: ignore[no-any-return]

    cases = getattr(request.app.state, "case_reader", None)
    if cases is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")

    stored = await cases.get(case_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such case")
    if not isinstance(stored, VerifyResponse):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="the stored case could not be read in the current contract",
        )
    return await with_receipt(request, stored)


@router.delete(
    "/cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop a check still running in the background",
)
async def cancel_case(case_id: UUID, request: Request) -> Response:
    """Stop a background check, so it is never charged (the website's Stop button).

    Stop used to stop only the page following the check: the check ran on to the
    end and was charged for an answer nobody was waiting for.

    Only the person who started it may stop it; anyone else is told there is no such
    check (404), as for a case id that never existed. 204 when stopped, and again for
    a check already stopped; 409 when it has finished, or has its answer and is being
    charged - too late to stop. Whatever was held for it is given back.
    """
    runs: BackgroundChecks | None = getattr(request.app.state, "background_checks", None)
    run = runs.get(str(case_id)) if runs is not None else None
    user = await signed_in(request)
    if (
        run is None
        or runs is None
        or (run.owner is not None and run.owner != getattr(user, "id", None))
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no check of yours is running under that id",
        )
    if not await runs.cancel(run):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this check has already finished; collect its answer instead",
        )
    event(
        logger, "background check stopped", module="api.verify", outcome="ok", case_id=str(case_id)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# How long one stream stays open: past the longest a background check may run.
_STREAM_SECONDS = BACKGROUND_CEILING_SECONDS + 30.0
# A comment line this often keeps proxies from closing a quiet stream.
_HEARTBEAT_SECONDS = 15.0


def _sse(*lines: str) -> str:
    """One Server-Sent Events message: its lines, then the blank line that ends it."""
    return "".join(f"{line}\n" for line in lines) + "\n"


def _progress_bus(request: Request, key: str) -> Any:
    bus = getattr(request.app.state, "progress_bus", None)
    if bus is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")
    if not valid_key(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such check")
    return bus


@router.get(
    "/cases/{key}/events",
    summary="Follow a check as it runs (Server-Sent Events)",
    response_class=StreamingResponse,
)
async def case_events(key: str, request: Request) -> StreamingResponse:
    """What a check is doing, as it does it: steps, sources, the evidence count.

    `key` is the `X-Request-ID` the app sent with a check, or a background check's case id.
    The stream may be opened before the check starts; everything already published is
    replayed first, and a reconnect with `Last-Event-ID` resumes after that event. It
    ends with `done` or `error`. Nothing in it is about the content being checked -
    see `app/orchestration/progress.py`.
    """
    bus = _progress_bus(request, key)
    try:
        resume = int(request.headers.get("last-event-id") or 0)
    except ValueError:
        resume = 0

    async def stream() -> AsyncIterator[str]:
        # Read by a separate task into a queue, so a heartbeat can be written while
        # waiting without cancelling the reader mid-event.
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def pump() -> None:
            try:
                async for item in bus.subscribe(key):
                    await queue.put(item)
            finally:
                await queue.put(None)

        reader = asyncio.create_task(pump())
        ends = time.monotonic() + _STREAM_SECONDS
        try:
            yield _sse("retry: 2000")
            while time.monotonic() < ends:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield _sse(": waiting")
                    continue
                if item is None:
                    break
                if item["seq"] <= resume:
                    continue
                data = json.dumps(item, separators=(",", ":"))
                yield _sse(f"id: {item['seq']}", f"event: {item['type']}", f"data: {data}")
        finally:
            reader.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cases/{key}/progress", summary="The events of a check so far (polling)")
async def case_progress(key: str, request: Request, after: int = 0) -> dict[str, Any]:
    """The same events as `/events`, for a client that cannot hold a stream open.

    Ask again with `after` set to the last `seq` seen; `finished` says the check ended.
    """
    bus = _progress_bus(request, key)
    events, finished = await bus.since(key, after)
    return {"events": events, "finished": finished}


@router.post(
    "/verify/file",
    summary="Verify an uploaded image, PDF or video",
    # Two shapes, so the response model is declared per status rather than inferred:
    # 200 carries a verdict, 202 carries a case id to poll.
    response_model=None,
    responses={
        200: {"model": VerifyResponse, "description": "Verified synchronously"},
        202: {"model": AcceptedResponse, "description": "Video accepted for processing"},
    },
)
async def verify_file(
    request: Request,
    file: Annotated[UploadFile, File()],
    consent_to_process_media: Annotated[bool, Form()] = False,
    recheck: Annotated[bool, Form()] = False,
    background: Annotated[bool, Form()] = False,
    # "Check what was read" (1.8). Accepted for the contract; an upload is always
    # checked on what could be read, and says what could not (`served_policy`).
    accept_partial: Annotated[bool, Form()] = False,
) -> VerifyResponse | JSONResponse:
    """Images and PDFs resolve in this request unless `background` is set; video
    always returns 202.

    With `background` (what the app sends, 1.4) a picture or PDF is read and checked
    like a background text check: 202 with a case id at once, every claim checked,
    progress from `/v1/cases/{id}`. The upload is still read and vetted here first,
    so a file that is too large or not a picture is refused at once, not after a wait.
    """
    key = _followed_by(request)
    async with _watched(request, None if background else key) as watching:
        user = await signed_in(request)
        cost = check_cost(request, video=_is_video(file))
        await require_credit(request, user, cost)

        if background:
            intake, data = await _read_upload(request, file, consent_to_process_media)
            case_id = uuid4()
            if intake.input_type is InputType.VIDEO:
                return _start_video(
                    request, intake, data, case_id=case_id, recheck=recheck, user=user, cost=cost
                )
            return _in_background(
                request,
                case_id,
                lambda: _checked_picture(request, intake, case_id=case_id, recheck=recheck),
                user=user,
                cost=cost,
            )

        try:
            response = await _checked_file(
                request, file, consent_to_process_media, recheck, user=user, cost=cost
            )
            if isinstance(response, VerifyResponse):
                response = _echo(await with_receipt(request, response), key)
        except BaseException:
            await release_credit(request)
            raise
        # A video is charged by its background check, when it has its answer.
        if isinstance(response, VerifyResponse):
            await _settle(request, user, cost, response)
        if watching is not None:
            # A video is answered with a case id to poll, which is where it ends too.
            answered = (
                response.case_id
                if isinstance(response, VerifyResponse)
                else json.loads(bytes(response.body))["case_id"]
            )
            await watching.done(str(answered))
    return response


async def _checked_file(
    request: Request,
    file: UploadFile,
    consent_to_process_media: bool,
    recheck: bool,
    *,
    user: Any,
    cost: int,
) -> VerifyResponse | JSONResponse:
    """The upload check itself; `verify_file` above meters it (a video meters itself)."""
    intake, data = await _read_upload(request, file, consent_to_process_media)
    case_id = uuid4()

    if intake.input_type is InputType.VIDEO:
        return _start_video(
            request, intake, data, case_id=case_id, recheck=recheck, user=user, cost=cost
        )
    return await _checked_picture(request, intake, case_id=case_id, recheck=recheck)


async def _read_upload(
    request: Request, file: UploadFile, consent_to_process_media: bool
) -> tuple[NormalisedIntake, bytes]:
    """The upload, read within the size limit and identified from its bytes."""
    # Unavailable is said before the upload is read, as for every check.
    get_orchestrator(request)
    settings = request.app.state.settings

    data = await file.read(settings.limits.max_upload_bytes + 1)
    if len(data) > settings.limits.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"the upload exceeds {settings.limits.max_upload_bytes} bytes",
        )

    try:
        # The declared type is passed but never trusted: normalise_upload decides
        # by sniffing the bytes, so a .jpg that is actually a PDF is handled as a PDF.
        intake = normalise_upload(
            data,
            max_bytes=settings.limits.max_upload_bytes,
            declared_type=file.content_type,
            consent=consent_to_process_media,
        )
    except IntakeRejected as rejected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(rejected)
        ) from rejected
    return intake, data


async def _checked_picture(
    request: Request, intake: NormalisedIntake, *, case_id: UUID, recheck: bool
) -> VerifyResponse:
    """A picture or a PDF: read and checked, with the picture's own checks joined in."""
    # The picture's own checks - credentials, earlier copies, the AI and editing
    # signals - run alongside the reading and the fact-check, and join the answer.
    inspection = _inspect_picture(request, intake)
    # What the reading makes of the picture. A designed card, a document or a
    # screenshot is no photograph, and the AI-picture detector's word on it is not
    # taken (`_as_designed`).
    seen = _Seen()
    response = await _checked_upload(
        request,
        intake,
        case_id=case_id,
        recheck=recheck,
        seen=seen,
        synthetic=(
            (lambda: _made_by_ai(inspection, designed=seen.designed))
            if inspection is not None
            else None
        ),
    )
    return await _with_media(response, inspection, designed=seen.designed)


@dataclass(slots=True)
class _Seen:
    """What the reading made of an uploaded picture, for the picture checks beside it."""

    kind: str | None = None
    text_area: float | None = None

    @property
    def designed(self) -> bool:
        return looks_designed(self.kind, self.text_area)


def ai_made(report: MediaReportResponse, *, designed: bool = False) -> bool:
    """Whether an upload's own checks say it was made or altered by AI: its file says
    so, the picture detectors agree, or a face or the voice in a video is past its
    model's line. Never a verdict on its own (`Orchestrator._fabricated`).

    Not the picture models' word on a designed graphic, a document or a screenshot
    (`designed`): they called the Labour Ministry's genuine EPF graphic 100% AI-made
    and PIB's fact-check card 99% (2026-10-02). And for a video, not one picture model
    alone: genuine UN footage of Netanyahu read 99.8% "generated" to it. Two models
    agreeing count; one does not.
    """
    detector = report.detector
    pictured = detector.agreement == "likely_ai" and not designed
    if report.kind == "video":
        pictured = pictured and detector.second_opinion is not None
    return bool(
        report.credentials.declares_ai
        or pictured
        or (detector.face_swapped and not designed)
        or detector.machine_voice
    )


async def _made_by_ai(inspection: asyncio.Task[_MediaShown], *, designed: bool = False) -> bool:
    media, _ = await inspection
    return ai_made(media, designed=designed)


@dataclass(frozen=True, slots=True)
class _Read:
    """What an upload was read as (contract 1.8): its parts, in the order the text
    claims are found in, and what could not be read.

    `shown` is the reading shown beside the answer (`image_reading`). `notes` are the
    gaps as the pipeline reports them, one for each of `reading.gaps`.
    """

    reading: Reading
    shown: OcrOutcome | None = None
    notes: tuple[SkippedCheck, ...] = ()

    def plus(self, part: ReadPart) -> _Read:
        return replace(self, reading=self.reading.plus(parts=(part,)))

    def missing(self, check: str, found: Gap) -> _Read:
        """This reading with a gap, and the note that reports it under `check`."""
        return replace(
            self,
            reading=self.reading.plus(gaps=(found,)),
            notes=(*self.notes, SkippedCheck(check=check, reason=found.detail, kind="reading")),
        )


async def _checked_upload(
    request: Request,
    intake: NormalisedIntake,
    *,
    case_id: UUID,
    recheck: bool,
    read: _Read | None = None,
    synthetic: Callable[[], Awaitable[bool]] | None = None,
    seen: _Seen | None = None,
    started_at: float | None = None,
    probed: bool = False,
) -> VerifyResponse:
    """A picture or a PDF, read and checked. Also a video, already `read`, checked
    through one of its frames.

    `synthetic` says whether the upload's own checks found it AI-made; the pipeline
    asks it only when that could decide the case (`Orchestrator._fabricated`). `seen`
    is told what the picture was read as. `started_at` is when the check's own time
    began (`Orchestrator.verify`): for a video, when its reading was done. `probed`:
    the caller already asked the verdict cache (`_checked_video`, before reading).
    """
    orchestrator = get_orchestrator(request)
    # Kept under what read it as well: a verdict stored for what an older reader made
    # of this picture is not served once the reading has changed.
    keyed = _upload_identity(intake)
    # Read here, rather than handed in: a picture or a PDF, whose reading is
    # remembered for a repeat served from the cache.
    own_reading = read is None

    # Probed before media preparation (hashing, embedding, OCR), for the same reason
    # the text path probes before extraction: a repeat should cost nothing. "Check
    # again" is the exception, as it is there.
    readings = _remembered_readings(request)
    hit = (
        None if recheck or probed else await orchestrator.cached(keyed, case_id=case_id)  # type: ignore[attr-defined]
    )
    if hit is not None:
        served = await cached_full_response(request, hit) or _thin(hit)
        shown = (
            _reading_response(read.shown)
            if read is not None
            else readings.get(intake.primary.sha256)
        )
        if shown is None and read is None and intake.input_type is InputType.IMAGE:
            # Remembered only in memory, so a repeat after a restart reads the picture
            # again - one model call, against a check that is otherwise free - rather
            # than showing a verdict with no sign of what it was about.
            read = await _read_document(request, intake)
            shown = _reading_response(read.shown)
            if shown is not None:
                _remember(readings, intake.primary.sha256, shown)
                _remember_area(request, intake.primary.sha256, read.shown)
        if seen is not None and shown is not None:
            # As the first check judged it: how much of the picture is text is
            # remembered beside the reading, or a screenshot judged designed the first
            # time showed "likely AI" on its repeat.
            seen.kind = shown.kind
            seen.text_area = _remembered_areas(request).get(intake.primary.sha256)
        return served.model_copy(
            update={
                "image_reading": shown,
                "input_read": (
                    _input_read(read.reading, _to_check(read.reading)) if read is not None else None
                ),
            }
        )

    # Read before checking. An image or a PDF used to reach the checker with no claims
    # at all: a screenshot of a forward announcing a ban on ₹500 notes was
    # fingerprinted, never read, and came back "Unconfirmed". Its text is now read and
    # checked exactly as a pasted message is - the same extraction, the same search,
    # the same rules - and a link in it is opened, as a link in a message is. What the
    # picture shows is checked beside its words, under its own label
    # (`app/media/composed.py`).
    if read is None:
        read = await _read_document(request, intake)
    if seen is not None and read.shown is not None:
        seen.kind = read.shown.kind
        seen.text_area = read.shown.text_area
    claims: list[Claim] = []
    own_pages: set[str] = set()
    notes: list[SkippedCheck] = []
    composed = _to_check(read.reading)
    if composed.text.strip():
        # A link in the upload's own words, never in Factify's description of it.
        link = _first_link(_authored(read.reading))
        if link is not None:
            page = await _read_linked_article(request, link)
            if page is not None:
                read = read.plus(
                    ReadPart(
                        kind=PartKind.LINKED_ARTICLE,
                        text=page.text,
                        route=page.route,
                        label=linked_article_label(urlsplit(link).hostname),
                        complete=page.partial is None and not page.truncated,
                    )
                )
                for missed in _page_gaps(page, part="linked_article", linked=True):
                    read = read.missing("linked_page", missed)
                composed = _to_check(read.reading)
                own_pages.add(page_key(link))
        extracted = await _extract_from_document(
            request, intake, composed.text, authored=_authored(read.reading)
        )
        claims = list(extracted.claims)
        if extracted.reason:
            notes.append(SkippedCheck(check="claim_extraction", reason=extracted.reason))

    # With no text to check, the image's own questions are asked instead: has it been
    # published before, and does it carry provenance (see `MediaVerification`).
    result = await orchestrator.verify(  # type: ignore[attr-defined]
        keyed,
        case_id=case_id,
        claims=claims,
        started_at=started_at,
        fresh=recheck,
        own_pages=frozenset(own_pages),
        synthetic=synthetic,
        # What could not be read, where it could decide the answer, is reported with
        # everything the run skips, and keeps the run out of the cache: a reader that
        # failed today may not tomorrow. A gap that could not (the frames left unread
        # for time, the tail of a long transcript) is said all the same
        # (`_with_reading_gaps`), and the answer is kept: the same video would be cut
        # the same way next time, and was never served from the cache.
        noted=_blocking_notes(read),
        # Whether an upload checked past a gap that could decide it may still be TRUE:
        # as it always could, until the owner decides (`UPLOADS_CHECKED_PARTIALLY`).
        partial_input=UPLOADS_CHECKED_PARTIALLY and read.reading.blocked,
    )

    response = await _from_cache(request, result) or to_response(result)
    shown = _reading_response(read.shown)
    if shown is not None and own_reading:
        _remember(readings, intake.primary.sha256, shown)
        _remember_area(request, intake.primary.sha256, read.shown)
    event(
        logger,
        "verify request served",
        module="api.verify",
        outcome="ok",
        action=result.action.value,
        claims=len(claims),
        from_cache=result.from_cache,
        elapsed_ms=result.elapsed_ms,
        input_type=intake.input_type.value,
        read_parts=len(read.reading.parts),
        read_gaps=len(read.reading.gaps),
        document_chars=len(composed.text),
    )
    return response.model_copy(
        update={
            "image_reading": shown,
            "skipped": _with_reading_gaps(response.skipped, read.notes, notes),
            "input_read": _input_read(read.reading, composed),
        }
    )


def _upload_identity(intake: NormalisedIntake) -> NormalisedIntake:
    """An upload as its verdict is cached: by its bytes, and by the reader that read it."""
    return replace(intake, cache_identity=f"{intake.cache_identity}|reader:{READER_VERSION}")


# How many words of its own an upload needs - on it, said in it, shown across it -
# before what it shows is checked beside them: three, as `Reading.substantive`
# counts.
_OWN_WORDS = 3


def _authored(reading: Reading) -> str:
    """The upload's own words: everything read from it but Factify's descriptions."""
    return "\n".join(part.text for part in reading.parts if not part.described)


def _to_check(reading: Reading) -> Composed:
    """The text an upload's claims are found in.

    Its own words and what it shows, each under its label (`compose`), when it has
    words of its own (`_OWN_WORDS`). A photograph with none - or a watermark, a sign -
    is its own words alone (`Reading.document(descriptions=False)`), often nothing:
    with no claims it is checked as a picture, for where it was published before and
    what its file says (`MediaVerification`). Claims made only of Factify's
    description of an old flood photograph are nothing a search can settle, and they
    took the place of the picture's own questions (2026-10-03 review).
    """
    if len(_authored(reading).split()) >= _OWN_WORDS:
        return compose(reading)
    return reading.document(descriptions=False)


def _blocking_notes(read: _Read) -> tuple[SkippedCheck, ...]:
    """The notes of the gaps that could decide the answer (`Gap.blocking`)."""
    blocking = {item.detail for item in read.reading.gaps if item.blocking}
    return tuple(note for note in read.notes if note.reason in blocking)


def _with_reading_gaps(
    skipped: tuple[SkippedCheckResponse, ...],
    gaps: Sequence[SkippedCheck],
    notes: Sequence[SkippedCheck],
) -> tuple[SkippedCheckResponse, ...]:
    """The answer's skipped checks, with what could not be read marked as reading.

    The pipeline reports the reading gaps it was given (`noted`) among its own; each
    is marked "reading" here, and one it did not report is added. Then `notes`, said
    after everything else, as they always were.
    """
    said = {(gap.check, gap.reason) for gap in gaps}
    marked = [
        item.model_copy(update={"kind": "reading"}) if (item.check, item.reason) in said else item
        for item in skipped
    ]
    present = {(item.check, item.reason) for item in marked}
    marked.extend(
        SkippedCheckResponse(check=gap.check, reason=gap.reason, kind="reading")
        for gap in gaps
        if (gap.check, gap.reason) not in present
    )
    marked.extend(
        SkippedCheckResponse(check=note.check, reason=note.reason, kind=note.kind) for note in notes
    )
    return tuple(marked)


# Whether an upload with a gap that could decide its answer - speech that could not be
# heard, a long clip's speech cut at the time limit, a scanned PDF's later pages - is
# checked as partial: never TRUE, `checked_partially` set (`roll_up`). Off, as before
# 1.8: such an upload may still be TRUE, its gaps said and the answer kept out of the
# cache. Links and posts read in part are checked as partial; whether uploads should
# be too is the owner's decision (2026-10-02 review), not made here.
UPLOADS_CHECKED_PARTIALLY = False


def _input_read(reading: Reading, composed: Composed) -> InputReadResponse:
    """What was read from an upload, part by part, for the answer (contract 1.8)."""
    return input_read_response(
        reading, composed, partially=UPLOADS_CHECKED_PARTIALLY and reading.blocked
    )


def input_read_response(
    reading: Reading,
    composed: Composed,
    *,
    partially: bool = False,
    withheld: bool = False,
) -> InputReadResponse:
    """What was read from the input, part by part, for the answer (contract 1.8).

    A part is `checked` when it is in the text claims were found in (`composed`), at
    the offsets given - what a picture or a video shows included. `partially`: the
    answer was checked past a blocking gap; `withheld`: it was not checked at all.
    """
    parts = []
    for index, part in enumerate(reading.parts):
        span = composed.span_of(index)
        parts.append(
            ReadPartResponse(
                kind=part.kind.value,
                label=part.label,
                text=part.text,
                checked=span is not None,
                route=part.route,
                complete=part.complete,
                note=part.note,
                media_url=f"{_THUMBNAILS}{part.media_key}" if part.media_key else None,
                char_start=span[0] if span is not None else None,
                char_end=span[1] if span is not None else None,
                seconds_read=round(part.seconds_read) if part.seconds_read is not None else None,
                seconds_total=(
                    round(part.seconds_total) if part.seconds_total is not None else None
                ),
                language=part.language,
            )
        )
    return InputReadResponse(
        kind=reading.kind,
        platform=reading.platform,
        url=reading.url,
        author=reading.author,
        handle=reading.handle,
        published_at=reading.published_at,
        parts=tuple(parts),
        gaps=tuple(
            ReadGapResponse(
                part=item.part, code=item.code.value, detail=item.detail, blocking=item.blocking
            )
            for item in reading.gaps
        ),
        limits=reading.limits,
        complete=reading.complete,
        verdict_withheld=withheld,
        checked_partially=partially and not withheld and reading.blocked,
    )


# What was read for recent answers, by the identity they are cached under, so a
# repeat served from the verdict cache - which reads nothing - can still say what was
# read: the parts, the gaps, the picture and video checks. In memory and bounded,
# like `_remembered_readings`; the case's own record (`case_readings`) outlives it.
_RECALLED_FIELDS = ("input_read", "media_report", "media_reports", "image_reading", "speech")


def remember_reading(request: Request, identity: str, response: VerifyResponse) -> None:
    """Keep what an answer says was read, for a repeat of it served from the cache."""
    memo = getattr(request.app.state, "input_reads", None)
    if memo is None:
        memo = {}
        request.app.state.input_reads = memo
    kept: dict[str, Any] = {name: getattr(response, name) for name in _RECALLED_FIELDS}
    kept["skipped"] = tuple(item for item in response.skipped if item.kind == "reading")
    memo.pop(identity, None)
    memo[identity] = kept
    while len(memo) > _READINGS_KEPT:
        memo.pop(next(iter(memo)))


def recalled(request: Request, identity: str, served: VerifyResponse) -> VerifyResponse:
    """A cached answer with what was read when it was first checked, where it lacks it."""
    memo = getattr(request.app.state, "input_reads", None)
    kept = memo.get(identity) if isinstance(memo, dict) else None
    if not kept:
        return served
    update: dict[str, Any] = {
        name: kept[name] for name in _RECALLED_FIELDS if kept[name] and not getattr(served, name)
    }
    present = {(item.check, item.reason) for item in served.skipped}
    missing = tuple(item for item in kept["skipped"] if (item.check, item.reason) not in present)
    if missing:
        update["skipped"] = (*served.skipped, *missing)
    return served.model_copy(update=update) if update else served


# Where the picture checks' own copies of earlier appearances are served from.
_THUMBNAILS = "/v1/media/thumbnails/"

_MediaShown = tuple[MediaReportResponse, tuple[AdvisoryResponse, ...]]


def _inspect_picture(
    request: Request, intake: NormalisedIntake
) -> asyncio.Task[_MediaShown] | None:
    """Start the picture checks for an uploaded image, or None for anything else.

    Remembered per picture in memory, like its reading: a repeat check pays for
    neither the reverse image search nor the detector a second time.
    """
    inspector = getattr(request.app.state, "media_inspector", None)
    data = intake.primary.data
    if inspector is None or intake.input_type is not InputType.IMAGE or data is None:
        return None
    memo = _remembered_media(request)
    key = intake.primary.sha256

    async def run() -> _MediaShown:
        known = memo.get(key)
        if known is not None:
            return known
        report = await inspector.inspect_image(data, mime=_image_mime(data) or "image/jpeg")
        shown = (
            media_report_to_response(report, thumbnails=_THUMBNAILS),
            tuple(advisory_to_response(item) for item in report.advisories),
        )
        memo.pop(key, None)
        memo[key] = shown
        while len(memo) > _READINGS_KEPT:
            memo.pop(next(iter(memo)))
        return shown

    return asyncio.create_task(run())


async def _with_media(
    response: VerifyResponse,
    inspection: asyncio.Task[_MediaShown] | None,
    *,
    designed: bool = False,
) -> VerifyResponse:
    """The answer with the picture checks beside it. A check that failed is left out.

    For a `designed` picture - a graphic, a document, a screenshot - without the
    AI-picture and face models' word on it (`_as_designed`).
    """
    if inspection is None:
        return response
    try:
        media, advisories = await inspection
    except Exception:
        logger.exception("the picture checks failed; the answer is sent without them")
        return response
    if designed:
        media, advisories = _as_designed(media, advisories)
    return with_earlier_copy(
        response.model_copy(
            update={"media_report": media, "advisories": (*response.advisories, *advisories)}
        )
    )


# The advisories that are the AI-picture and face models' word on a picture.
_PICTURE_MODELS = frozenset({"ai_generation", "face_swap"})


def _as_designed(
    media: MediaReportResponse, advisories: tuple[AdvisoryResponse, ...]
) -> _MediaShown:
    """The picture checks for a designed graphic, a document or a screenshot.

    The AI-picture model is trained on photographs, and on made pictures it is
    confidently wrong: the Labour Ministry's EPF graphic read 100% AI-made, PIB's
    fact-check card 99%, a gazette screenshot 94% (2026-10-02), each shown as a
    suspicion on a genuine post. Its word is left out, and the detector is reported
    as not having judged a text card - which the app already words - while the
    editing signals and the earlier copies stand.
    """
    detector = media.detector
    if detector.status != "checked":
        return media, advisories
    kept = tuple(item for item in advisories if item.provider not in _PICTURE_MODELS)
    return (
        media.model_copy(
            update={
                "detector": DetectorResponse(
                    status="not_checked", why="text_card", on_server=detector.on_server
                )
            }
        ),
        kept,
    )


def _same_page(a: str, b: str) -> bool:
    def bare(url: str) -> str:
        parts = urlsplit(url.strip())
        return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"

    return bool(a) and bool(b) and bare(a) == bare(b)


def with_earlier_copy(response: VerifyResponse) -> VerifyResponse:
    """A media match cited in the answer shows the earlier copy's picture, when the
    picture checks fetched that same page: its thumbnail is on our own address."""
    report = response.media_report
    earliest = report.history.earliest if report is not None else None
    if earliest is None or earliest.thumbnail_url is None:
        return response
    claims = []
    changed = False
    for claim in response.claims:
        evidence = []
        for item in claim.evidence:
            if item.earlier_media is not None and _same_page(item.citation_url, earliest.url):
                item = item.model_copy(
                    update={
                        "earlier_media": item.earlier_media.model_copy(
                            update={"thumbnail_url": earliest.thumbnail_url}
                        )
                    }
                )
                changed = True
            evidence.append(item)
        claims.append(claim.model_copy(update={"evidence": tuple(evidence)}))
    return response.model_copy(update={"claims": tuple(claims)}) if changed else response


def _remembered_media(request: Request) -> dict[str, _MediaShown]:
    memo = getattr(request.app.state, "media_reports", None)
    if memo is None:
        memo = {}
        request.app.state.media_reports = memo
    return memo


def _start_video(
    request: Request,
    intake: NormalisedIntake,
    data: bytes,
    *,
    case_id: UUID,
    recheck: bool,
    user: Any,
    cost: int,
) -> JSONResponse:
    """Check a video in the background and answer with its case id at once.

    It used to be recorded as "not processed" and nothing else: the 202 led to an
    empty case. It is now read - what is said in it, the words shown across it and
    what it shows (`_checked_video`) - and checked, with every keyframe put through
    the picture checks, and the app collects the answer from `/v1/cases/{id}`.

    Charged as any background check is, when it has its answer. It was charged when
    it was accepted, so a video whose check failed, or that was stopped, still cost
    three checks, against "a check that fails costs nothing" (2026-10-02).
    """
    return _in_background(
        request,
        case_id,
        lambda: _checked_video(request, intake, data, case_id=case_id, recheck=recheck),
        user=user,
        cost=cost,
        estimated_seconds=90,
    )


# How long the words on a video's frames may take to read, in all. A frame takes a
# second or two on the server's CPU, shared with the speech reader; past this the
# frames left are not read, and the answer says so. They are read so that any first
# few cover the whole clip (`read_frames_text`).
FRAMES_TEXT_SECONDS = 90.0

# How long what is said in a video may take to read. Whisper read the RBI clip's
# 2:09 in 45-48 s on four threads of a development machine; the server's four cores
# are shared with the frames' words and the picture checks, and ten minutes of speech
# would take most of a check's time. Past this the rest is not read, and the answer
# says how much was (`SpeechReader.read_video_outcome`).
SPEECH_SECONDS = 150.0


async def _checked_video(
    request: Request, intake: NormalisedIntake, data: bytes, *, case_id: UUID, recheck: bool
) -> VerifyResponse:
    """A video: read - what is said, the words shown across it, what it shows - and
    checked from all three, with its keyframes put through the picture checks.

    It used to be checked from one frame of its first 90 seconds and what was said:
    an RBI clip's "REPO RATE UNCHANGED AT 5.25%" card ran from 1:53 to its end and was
    never seen, and the one frame read was a wipe (2026-10-02).
    """
    began = time.perf_counter()
    window = _video_window(request)
    keyed = _upload_identity(intake)
    # A repeat is answered before the video is read: reading it - its speech, the
    # words on its frames, one description - took a minute and more, and was spent
    # again on every repeat only to be served the stored verdict afterwards.
    hit = (
        None if recheck else await get_orchestrator(request).cached(keyed, case_id=case_id)  # type: ignore[attr-defined]
    )
    if hit is not None:
        served = await cached_full_response(request, hit) or _thin(hit)
        return recalled(request, keyed.cache_identity, served)

    extracted, video = await read_video(request, data, window=window)
    if video is None:
        # Nothing could be taken from the clip: said, and nothing else claimed.
        await _record_unprocessed_video(request, case_id=case_id, intake=intake)
        result = await get_orchestrator(request).verify(  # type: ignore[attr-defined]
            intake, case_id=uuid4(), claims=[], fresh=True
        )
        response = to_response(result)
        return response.model_copy(
            update={
                "case_id": str(case_id),
                "skipped": (
                    *response.skipped,
                    SkippedCheckResponse(
                        check="video_frames",
                        reason=extracted.reason or "no frames could be taken from the video",
                    ),
                ),
            }
        )

    settings = request.app.state.settings
    inspection = video.inspection
    heard = video.heard
    read = video.read

    # The answer is checked through one of the frames read - the picture questions
    # (has it been published before) are asked of it - and kept under the video's own
    # identity, never the frame's: the same frame can open another video.
    middle = replace(
        normalise_upload(
            video.middle,
            max_bytes=settings.limits.max_upload_bytes,
            declared_type="image/jpeg",
            consent=True,
        ),
        cache_identity=intake.cache_identity,
    )

    async def video_made_by_ai() -> bool:
        if inspection is None:
            return False
        return ai_made(media_report_to_response(await inspection, thumbnails=_THUMBNAILS))

    # The check's time is counted from when the video's own began: reading a long
    # clip takes minutes, and the person's wait (`BACKGROUND_CEILING_SECONDS`) holds
    # the reading and the searching together. However long the reading took, the
    # searching keeps `BACKGROUND_MIN_READING_SECONDS`.
    searching = _searching_seconds(time.perf_counter() - began)
    budget = check_seconds.set(searching) if searching is not None else None
    try:
        response = await _checked_upload(
            request,
            middle,
            case_id=case_id,
            recheck=recheck,
            read=read,
            synthetic=video_made_by_ai,
            started_at=time.perf_counter(),
            probed=True,
        )
    finally:
        if budget is not None:
            check_seconds.reset(budget)
    notes = (SkippedCheckResponse(check="video_frames", reason=video.note()),)
    if heard.transcript is not None:
        response = response.model_copy(
            update={
                "speech": SpeechResponse(
                    text=heard.transcript.text,
                    language=heard.transcript.language,
                    cut_off=heard.transcript.cut_off,
                )
            }
        )
    response = response.model_copy(update={"skipped": (*response.skipped, *notes)})
    if inspection is not None:
        try:
            report = await inspection
        except Exception:
            logger.exception("the video's picture checks failed")
        else:
            response = response.model_copy(
                update={
                    "media_report": media_report_to_response(report, thumbnails=_THUMBNAILS),
                    "advisories": (
                        *response.advisories,
                        *(advisory_to_response(item) for item in report.advisories),
                    ),
                }
            )
    if not response.from_cache:
        remember_reading(request, keyed.cache_identity, response)
    return response


@dataclass(slots=True)
class VideoRead:
    """A video read whole: what is said, the words shown across it, what it shows,
    and the picture checks of its keyframes, started beside the reading."""

    extracted: ExtractedVideo
    taken: FramesRead
    heard: SpeechOutcome
    shown_words: FramesText
    looked: _Described
    read: _Read
    duration: float
    # The frame the answer is checked through: the middle one of those read.
    middle: bytes
    inspection: asyncio.Task[Any] | None
    window: int

    def note(self) -> str:
        """What was read of the video and what was checked, in one line."""
        return _video_note(
            self.extracted,
            self.taken,
            self.heard,
            self.shown_words,
            self.looked,
            window=self.window,
        )


async def read_video(
    request: Request, data: bytes, *, window: int
) -> tuple[ExtractedVideo, VideoRead | None]:
    """Read a video - an upload, or one downloaded from a post - and start its picture
    checks. None beside what the extractor said when no frame could be taken at all.
    """
    # What is said takes longest to read, so it is read from the start, beside the
    # frames being taken.
    hearing = asyncio.create_task(_heard(request, data, max_seconds=window))
    try:
        extracted = await KeyframeExtractor.reading(read_seconds=window).extract(data)
    except BaseException:
        hearing.cancel()
        raise
    if not extracted.succeeded:
        hearing.cancel()
        return extracted, None

    frames = [frame.data for frame in extracted.keyframes]
    inspector = getattr(request.app.state, "media_inspector", None)
    # The face model reads frames spread evenly across the clip (`even_frames`).
    even = [frame.data for frame in extracted.even_frames]
    inspection = (
        asyncio.create_task(inspector.inspect_video(data, frames, even)) if inspector else None
    )
    duration = extracted.probe.duration_seconds if extracted.probe is not None else 0.0
    taken = extracted.read or FramesRead(duration_seconds=duration, reason="not taken")
    if not taken.frames:
        # None could be taken across the clip - a recording whose length its file
        # does not give, or every grab failed - so the picture checks' own frames are
        # read instead, and the answer says so.
        taken = _keyframes_read(extracted, taken)

    # Read while the keyframes are checked, side by side: what is said
    # (`app/media/speech.py`), the words shown (`app/media/frame_text.py`) and what it
    # shows, from one contact sheet of its frames (`app/media/sheet.py`).
    try:
        heard, shown_words, looked = await asyncio.gather(
            hearing,
            read_frames_text(
                local_reader(getattr(request.app.state, "ocr", None)),
                [frame.data for frame in taken.frames],
                budget_seconds=FRAMES_TEXT_SECONDS,
            ),
            _described_video(request, taken),
        )
    except BaseException:
        hearing.cancel()
        if inspection is not None:
            inspection.cancel()
        raise
    picture = (
        taken.frames[len(taken.frames) // 2].data if taken.frames else frames[len(frames) // 2]
    )
    return extracted, VideoRead(
        extracted=extracted,
        taken=taken,
        heard=heard,
        shown_words=shown_words,
        looked=looked,
        read=_video_reading(taken, heard, shown_words, looked, duration=duration),
        duration=duration,
        middle=picture,
        inspection=inspection,
        window=window,
    )


def _video_window(request: Request) -> int:
    """How much of a video is read: `social.max_video_seconds`, ten minutes."""
    social = getattr(request.app.state.settings, "social", None)
    seconds = getattr(social, "max_video_seconds", None)
    return int(seconds) if isinstance(seconds, int | float) and seconds > 0 else READ_SECONDS


def _searching_seconds(spent: float) -> float | None:
    """How long a background check may search and read sources once `spent` seconds
    went on reading its video: its usual time, unless that would take the whole check
    past `BACKGROUND_CEILING_SECONDS`, and never less than
    `BACKGROUND_MIN_READING_SECONDS`. None outside a background check.
    """
    usual = check_seconds.get()
    if usual is None:
        return None
    return min(usual, max(BACKGROUND_MIN_READING_SECONDS, BACKGROUND_CEILING_SECONDS - spent))


async def _heard(request: Request, video: bytes, *, max_seconds: float) -> SpeechOutcome:
    """What is said in a video, and what happened if nothing is (`SpeechOutcome`).

    A reader that fails takes nothing else down - the video is still checked from its
    frames - and the answer says the speech could not be read. Read for at most
    `SPEECH_SECONDS`.
    """
    reader = getattr(request.app.state, "speech_reader", None)
    return await read_speech(reader, video, max_seconds=max_seconds, time_limit=SPEECH_SECONDS)


def _keyframes_read(extracted: ExtractedVideo, taken: FramesRead) -> FramesRead:
    """The picture checks' frames, read when none could be taken across the clip.

    Taken from its first `DEFAULT_MAX_SECONDS`, at its cuts and evenly. Before the
    video was read across its length, its middle keyframe was always read; with no
    frames to read at all, a silent captioned clip had nothing left to check.
    """
    found = {frame.timestamp_ms: frame for frame in (*extracted.keyframes, *extracted.even_frames)}
    frames = tuple(found[moment] for moment in sorted(found))
    if not frames:
        return taken
    duration = taken.duration_seconds
    reached = min(duration, float(DEFAULT_MAX_SECONDS)) if duration > 0 else 0.0
    return FramesRead(
        frames=frames,
        # As far as the frames go when the clip's length is not known: nothing beyond
        # can be said to be cut off, and the gap says the length was not known.
        window_seconds=round(max(reached, frames[-1].timestamp_ms / 1000), 2),
        duration_seconds=duration,
        reason=taken.reason,
        from_keyframes=True,
    )


@dataclass(frozen=True, slots=True)
class _Described:
    """What a video shows, in the hosted reader's words, and the sheet it saw."""

    outcome: OcrOutcome
    # The contact sheet, kept on our own address for the answer to show; and how many
    # frames were on it.
    sheet_key: str | None = None
    frames: int = 0


def _hosted_reader(ocr: Any) -> Any | None:
    """The hosted picture reader behind the server's reader, when it describes videos."""
    hosted = ocr.hosted if isinstance(ocr, LocalFirstOcr) else ocr
    return hosted if hasattr(hosted, "describe_video") else None


async def _described_video(request: Request, taken: FramesRead) -> _Described:
    """What a video shows, from one contact sheet of its frames: one model call for the
    whole video, never one a frame. Never raises."""
    hosted = _hosted_reader(getattr(request.app.state, "ocr", None))
    if hosted is None:
        return _Described(OcrOutcome(reason="unavailable: no picture reader is set up"))
    if not taken.frames:
        return _Described(OcrOutcome(reason="no frames to describe"))
    # Off the event loop: choosing decodes and compares up to two dozen frames.
    sheet, count = await asyncio.to_thread(_sheet_of, taken.frames)
    if sheet is None:
        return _Described(OcrOutcome(reason="the frames could not be laid out"))
    try:
        outcome: OcrOutcome = await hosted.describe_video(
            sheet,
            frames=count,
            span=f"0:00-{clock(taken.window_seconds * 1000)}",
        )
    except Exception as error:
        logger.exception("the video could not be described")
        return _Described(OcrOutcome(reason=f"failed: {type(error).__name__}"))
    inspector = getattr(request.app.state, "media_inspector", None)
    key = None
    if outcome.succeeded and inspector is not None:
        key = await asyncio.to_thread(inspector.keep_picture, sheet)
    return _Described(outcome, sheet_key=key, frames=count)


def _sheet_of(frames: Sequence[Keyframe]) -> tuple[bytes | None, int]:
    """One contact sheet of the frames that between them show the clip, and how many
    are on it (`app/media/sheet.py`)."""
    picked = pick_for_sheet(frames)
    return contact_sheet(picked), len(picked)


def _video_reading(
    taken: FramesRead,
    heard: SpeechOutcome,
    shown: FramesText,
    looked: _Described,
    *,
    duration: float,
) -> _Read:
    """A video's reading: what is said, the words shown, and what it shows, in that
    order, and every part of it that could not be read."""
    read = _Read(reading=Reading(kind="video"))
    transcript = heard.transcript
    if transcript is not None:
        read = read.plus(
            ReadPart(
                kind=PartKind.TRANSCRIPT,
                text=transcript.text,
                route="whisper",
                label=SAID_IN_VIDEO,
                complete=not transcript.cut_off,
                seconds_read=heard.audio_seconds,
                seconds_total=duration or None,
                language=transcript.language,
            )
        )
    if shown.text:
        read = read.plus(
            ReadPart(
                kind=PartKind.ON_SCREEN_TEXT,
                text=shown.text,
                route="frames.ocr",
                label=TEXT_IN_VIDEO,
                complete=shown.complete,
                note=_frames_span(taken, shown.frames_read),
            )
        )
    description = described(looked.outcome.description) if looked.outcome.succeeded else ""
    if description:
        read = read.plus(
            ReadPart(
                kind=PartKind.VIDEO_DESCRIPTION,
                text=description,
                route="ocr.hosted",
                label=VIDEO_DESCRIBED,
                note=f"described from {looked.frames} of the frames",
                media_key=looked.sheet_key,
            )
        )

    if taken.from_keyframes:
        # Only the opening stretch's frames were read, and the clip may run on past
        # them: past `DEFAULT_MAX_SECONDS`, or for as long as its file does not say.
        length = f"of its {clock(duration * 1000)}" if duration > 0 else "(its length is unknown)"
        read = read.missing(
            "video",
            gap(
                "video",
                GapCode.CUT_OFF,
                f"No frames could be taken across the video ({taken.reason}); its words "
                f"and what it shows were read from {len(taken.frames)} frames of its first "
                f"{clock(taken.window_seconds * 1000)} {length}.",
                blocking=duration <= 0 or taken.cut_off,
            ),
        )
    elif taken.cut_off:
        read = read.missing(
            "video",
            gap(
                "video",
                GapCode.CUT_OFF,
                f"Only the first {clock(taken.window_seconds * 1000)} of the video's "
                f"{clock(duration * 1000)} was read; what is shown or said after that "
                "was not checked.",
            ),
        )
    elif not taken.frames:
        read = read.missing(
            "video",
            gap(
                "video",
                GapCode.VIDEO_UNREAD,
                f"No frame could be taken to read what the video shows ({taken.reason}).",
            ),
        )
    if heard.unread:
        read = read.missing(
            "speech",
            gap(
                "transcript",
                GapCode.SPEECH_UNREAD,
                f"What is said in the video could not be read ({heard.reason}).",
            ),
        )
    elif transcript is not None and transcript.timed_out:
        # Reading stopped at `SPEECH_SECONDS`: what is said after that could be the
        # claim, so this gap counts.
        of = f" of {clock(duration * 1000)}" if duration > 0 else ""
        read = read.missing(
            "speech",
            gap(
                "transcript",
                GapCode.CUT_OFF,
                f"What is said in the video was read for its first "
                f"{clock((heard.audio_seconds or 0.0) * 1000)}{of}; there was no time to "
                "read the rest.",
            ),
        )
    elif transcript is not None and transcript.cut_off and not taken.cut_off:
        read = read.missing(
            "speech",
            gap(
                "transcript",
                GapCode.CUT_OFF,
                "More is said in the video than is kept; only the start of it was checked.",
                blocking=False,
            ),
        )
    if taken.frames and shown.reason is not None:
        read = read.missing(
            "video_text",
            gap(
                "on_screen_text",
                GapCode.READER_UNAVAILABLE
                if shown.reason.startswith("unavailable")
                else GapCode.VIDEO_UNREAD,
                f"The words shown in the video could not be read ({shown.reason}).",
            ),
        )
    elif shown.frames_read < shown.frames_total:
        read = read.missing(
            "video_text",
            gap(
                "on_screen_text",
                GapCode.CUT_OFF,
                f"The words on {shown.frames_read} of {shown.frames_total} frames were read; "
                "there was no time for the rest.",
                blocking=False,
            ),
        )
    elif shown.cut_off:
        read = read.missing(
            "video_text",
            gap(
                "on_screen_text",
                GapCode.CUT_OFF,
                "More words are shown in the video than are kept; the first of them were checked.",
                blocking=False,
            ),
        )

    if shown.text or description:
        read = replace(
            read,
            shown=OcrOutcome(
                text=shown.text,
                language=detect(shown.text) if shown.text else None,
                model_id=looked.outcome.model_id,
                description=description,
                kind=looked.outcome.kind if looked.outcome.succeeded else "OTHER",
                publisher=looked.outcome.publisher,
            ),
        )
    return read


def _frames_span(taken: FramesRead, frames_read: int) -> str:
    """ "read from 23 frames between 0:00 and 2:08"."""
    if taken.first_ms is None or taken.last_ms is None:
        return f"read from {frames_read} frames"
    return (
        f"read from {frames_read} frames between {clock(taken.first_ms)} and {clock(taken.last_ms)}"
    )


def _video_note(
    extracted: ExtractedVideo,
    taken: FramesRead,
    heard: SpeechOutcome,
    shown: FramesText,
    looked: _Described,
    *,
    window: float,
) -> str:
    """What was read of a video and what was checked, exactly, in one line.

    It said "checked 12 still frames; analysed the first 90s" when one frame of the
    first 90 seconds had been read for its words, which overstated what was read.
    """
    duration = taken.duration_seconds or (
        extracted.probe.duration_seconds if extracted.probe is not None else 0.0
    )
    # "of 2:09", or nothing when the file does not say how long it is.
    of = f" of {clock(duration * 1000)}" if duration > 0 else ""
    said: list[str] = []
    if taken.frames and taken.first_ms is not None and taken.last_ms is not None:
        span = f"{clock(taken.first_ms)} to {clock(taken.last_ms)}{of}"
        if shown.frames_read:
            count = (
                f"{len(taken.frames)}"
                if shown.frames_read == len(taken.frames)
                else f"{shown.frames_read} of {len(taken.frames)}"
            )
            said.append(f"read the words on {count} frames taken from {span}")
        else:
            said.append(
                f"took {len(taken.frames)} frames from {span} but could not read their "
                f"words ({shown.reason})"
            )
        if looked.outcome.succeeded and looked.outcome.description:
            said.append(f"described what it shows from {looked.frames} of them")
        else:
            said.append(f"could not describe what it shows ({looked.outcome.reason})")
    else:
        said.append(f"could not take frames to read ({taken.reason})")
    if heard.status == "read" and heard.audio_seconds is not None:
        heard_for = clock(heard.audio_seconds * 1000)
        timed_out = heard.transcript is not None and heard.transcript.timed_out
        if timed_out:
            said.append(
                f"listened to the first {heard_for}{of} for speech, and had no time for the rest"
            )
        elif duration - heard.audio_seconds > 1.0:
            said.append(f"listened to the first {heard_for}{of} for speech")
        else:
            said.append(f"listened to all {heard_for} of it for speech")
    elif heard.status == "no_speech":
        said.append("heard no speech in it")
    elif heard.status == "no_audio":
        said.append("it has no sound")
    else:
        said.append(f"could not read its speech ({heard.reason})")
    if taken.from_keyframes:
        said.append(
            f"its frames were taken from its first {clock(taken.window_seconds * 1000)} only, "
            f"as none could be taken across it ({taken.reason})"
        )
    elif taken.cut_off:
        said.append(f"nothing after {clock(window * 1000)} was read")
    checked = min(duration, float(DEFAULT_MAX_SECONDS)) if duration else DEFAULT_MAX_SECONDS
    faces = (
        f", and the face-swap check at {len(extracted.even_frames)},"
        if extracted.even_frames
        else ""
    )
    said.append(
        f"the AI-picture and earlier-copy checks looked at {len(extracted.keyframes)} "
        f"frames{faces} from its first {clock(checked * 1000)}"
    )
    return "; ".join(said)


_THUMBNAIL_KEY = re.compile(r"^[0-9a-f]{32}$")


@router.post(
    "/cases/{case_id}/correction-text",
    response_model=CorrectionTextResponse,
    summary="A polite message to send back to the chat with the correction",
)
async def correction_text(
    case_id: UUID, payload: CorrectionTextRequest, request: Request
) -> CorrectionTextResponse:
    """Built from the stored answer by template - no model - in English or Hindi."""
    cases = getattr(request.app.state, "case_reader", None)
    if cases is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")
    stored = await cases.get(case_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such case")
    built = correction_message(stored, payload.language)
    return CorrectionTextResponse(message=built.message, links=built.links)


@router.get(
    "/cases/{case_id}/sources/{evidence_id}",
    response_model=SourceReaderResponse,
    summary="A cited passage in its article, for reading in the app",
)
async def read_case_source(
    case_id: UUID, evidence_id: str, request: Request, url: str | None = None
) -> SourceReaderResponse:
    """The quoted paragraph with its neighbours, the headline, date and read time.

    `evidence_id` is the stored citation's id. A result fresh from `/v1/verify`
    carries the check's own ids rather than the stored ones, so `url` - the cited
    page - finds the same citation in the stored case.
    """
    cases = getattr(request.app.state, "case_reader", None)
    fetcher = getattr(request.app.state, "url_reader", None)
    if cases is None or fetcher is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")
    stored = await cases.get(case_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such case")
    cited = [item for claim in stored.claims for item in claim.evidence]
    evidence = next((e for e in cited if e.id == evidence_id), None) or next(
        (e for e in cited if url and e.citation_url == url), None
    )
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such source")

    views: SourceViews | None = getattr(request.app.state, "source_views", None)
    if views is None:
        views = SourceViews()
        request.app.state.source_views = views
    key = f"{case_id}:{evidence.citation_url}:{evidence.source_excerpt[:80]}"
    known = views.get(key)
    if known is not None:
        return known  # type: ignore[no-any-return]

    view = await read_source(
        fetcher,
        url=evidence.citation_url,
        quote=evidence.source_excerpt,
        publisher=evidence.publisher,
        # The page's own date when the ledger has it; the reader reads it off the
        # page otherwise. Never `observed_at`, which is when we fetched it.
        published_at=(
            datetime.combine(evidence.published_on, datetime.min.time(), tzinfo=UTC)
            if evidence.published_on
            else None
        ),
        headline=evidence.title,
        vendor=getattr(
            getattr(request.app.state, "web_search_resolver", None), "_vendor_extract", None
        ),
    )
    inspector = getattr(request.app.state, "media_inspector", None)
    image_url = None
    if view.image and inspector is not None:
        image_url = f"{_THUMBNAILS}{inspector.thumbnails.put(view.image)}"
    response = SourceReaderResponse(
        url=view.url,
        domain=view.domain,
        publisher=view.publisher,
        headline=view.headline,
        published_at=view.published_at,
        read_minutes=view.read_minutes,
        image_url=image_url,
        paragraphs=view.paragraphs,
        quote=QuoteLocationResponse(
            text=view.quote,
            paragraph_index=view.quote_paragraph,
            char_start=view.quote_start,
            char_end=view.quote_end,
        ),
        match_basis=evidence.match_basis,
        credibility=evidence.credibility,
        tier=evidence.tier,
        direction=evidence.direction,
        complete=view.complete,
        limitations=view.limitations,
    )
    views.put(key, response)
    return response


@router.get(
    "/media/thumbnails/{key}",
    summary="A small copy of an earlier appearance of a checked picture",
    response_class=Response,
)
async def media_thumbnail(key: str, request: Request) -> Response:
    """Served from here so the app never loads a third-party image directly."""
    inspector = getattr(request.app.state, "media_inspector", None)
    data = inspector.thumbnails.get(key) if inspector and _THUMBNAIL_KEY.match(key) else None
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such thumbnail")
    return Response(
        content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


# How many images of a scanned PDF are read. A forged circular is one or two pages;
# a long scanned document is read from its start, and the rest is said to be unread.
_SCANNED_PAGES_READ = 3


async def _read_document(request: Request, intake: NormalisedIntake) -> _Read:
    """What an uploaded image or PDF says and shows, and anything that could not be read.

    An image is read by the image reader (`app/extraction/ocr.py`): its words, and
    what it shows, each a part under its own label (`app/media/composed.py`). A PDF's
    own text layer is used when it has one; a scanned PDF has none, so its page
    images are read the same way a screenshot is.
    """
    primary = intake.primary
    reader = getattr(request.app.state, "ocr", None)
    if intake.input_type is InputType.PDF:
        return await _read_pdf(request, intake)
    read = _Read(reading=Reading(kind="image"))
    if primary.data is None or intake.input_type is not InputType.IMAGE:
        return read

    if reader is None:
        return read.missing(
            "image_text",
            gap("picture_text", GapCode.READER_UNAVAILABLE, "reading images is not set up"),
        )
    reading: OcrOutcome = await reader.transcribe(
        primary.data, mime_type=primary.mime_type or "image/jpeg"
    )
    if not reading.succeeded:
        return read.missing(
            "image_text",
            gap(
                "picture_text",
                GapCode.PICTURE_UNREAD,
                f"the image could not be read ({reading.reason})",
            ),
        )
    read = replace(read, shown=reading)
    read = read.plus(
        ReadPart(
            kind=PartKind.PICTURE_TEXT,
            text=reading.text.strip(),
            route="ocr.local" if (reading.model_id or "").startswith("rapidocr") else "ocr.hosted",
            label=picture_text_label(1, 1),
            complete=not reading.cut_off,
            language=reading.language.language.value if reading.language else None,
        )
    )
    if reading.description:
        read = read.plus(
            ReadPart(
                kind=PartKind.PICTURE_DESCRIPTION,
                text=described(reading.description),
                route="ocr.hosted",
                label=PICTURE_DESCRIBED,
            )
        )
    if reading.cut_off:
        read = read.missing(
            "image_text",
            gap(
                "picture_text",
                GapCode.CUT_OFF,
                "the image holds more text than is read at once; only its start was checked",
            ),
        )
    return read


async def _read_pdf(request: Request, intake: NormalisedIntake) -> _Read:
    """A PDF's text: its own text layer, or its first pages read as pictures."""
    primary = intake.primary
    reader = getattr(request.app.state, "ocr", None)
    read = _Read(reading=Reading(kind="pdf"))
    if primary.data is None:
        return read

    def text(body: str, route: str) -> ReadPart:
        # Bare, with no label: a PDF's text is checked as it was before (2026-10-03).
        return ReadPart(kind=PartKind.DOCUMENT_TEXT, text=body[:_MAX_ARTICLE_CHARS], route=route)

    def unread(reason: str) -> _Read:
        return read.missing("document_text", gap("document_text", GapCode.PAGES_UNREAD, reason))

    try:
        pdf = await asyncio.to_thread(extract_pdf, primary.data)
    except PdfRejected as rejected:
        return unread(rejected.reason)
    if not pdf.needs_ocr and not pdf.text_is_broken:
        return read.plus(text(pdf.text, "pdf.text"))

    # Scanned, or typed with its Hindi scrambled in the text layer ("विज्ञान" as
    # "िव ान"): the pages are read as a person sees them - the document itself, cut
    # to its first pages, in one call.
    if reader is not None:
        whole = await _read_pages(reader, primary.data, page_count=pdf.page_count)
        if whole is not None:
            pages, gaps = whole
            read = replace(read, shown=pages).plus(text(pages.text, "pdf.ocr"))
            for note in gaps:
                read = read.missing(
                    "document_text",
                    gap(
                        "document_text",
                        GapCode.PAGES_UNREAD
                        if note.reason.startswith("read the first")
                        else GapCode.CUT_OFF,
                        note.reason,
                    ),
                )
            return read
    if not pdf.needs_ocr:
        return unread("the document's text is scrambled and unreadable")

    first: OcrOutcome | None = None
    pages_read: list[str] = []
    if reader is not None:
        for image in pdf.embedded_images[:_SCANNED_PAGES_READ]:
            mime = _image_mime(image)
            if mime is None:
                continue
            # The pages' words are all that is used: no description is asked for.
            outcome: OcrOutcome = await (
                reader.transcribe(image, mime_type=mime, describe=False)
                if isinstance(reader, LocalFirstOcr)
                else reader.transcribe(image, mime_type=mime)
            )
            if outcome.has_text:
                pages_read.append(outcome.text)
                first = first or outcome
    if not pages_read:
        return unread("the document has no readable text")
    return replace(read, shown=first).plus(text("\n\n".join(pages_read), "pdf.ocr"))


async def _read_pages(
    reader: Any, data: bytes, *, page_count: int
) -> tuple[OcrOutcome, list[SkippedCheck]] | None:
    """A PDF's first pages read by the model as a document, or None when that did not
    produce any text (the caller then falls back to what it has)."""
    try:
        pages = await asyncio.to_thread(first_pages, data, _SCANNED_PAGES_READ)
    except (PdfReadError, ValueError, KeyError, OSError):
        return None
    read: OcrOutcome = await reader.transcribe(pages, mime_type=PDF_MIME)
    if not read.has_text:
        return None
    gaps: list[SkippedCheck] = []
    if page_count > _SCANNED_PAGES_READ:
        gaps.append(
            SkippedCheck(
                check="document_text",
                reason=f"read the first {_SCANNED_PAGES_READ} of {page_count} pages",
            )
        )
    if read.cut_off:
        gaps.append(
            SkippedCheck(
                check="document_text",
                reason=(
                    "the document holds more text than is read at once; only its start was checked"
                ),
            )
        )
    return read, gaps


async def _extract_from_document(
    request: Request, intake: NormalisedIntake, document: str, *, authored: str | None = None
) -> ExtractedClaims:
    """Claims from the text read out of an upload, anchored in that text.

    Its language is that of the `authored` parts - the words on it and said in it -
    when given: Factify's labels and description are English, and would make a Hindi
    card read as English.
    """
    pipeline = getattr(request.app.state, "claim_pipeline", None)
    if pipeline is None:
        return ExtractedClaims(reason="claim extraction is not configured")
    extracted: ExtractedClaims = await pipeline.extract(
        document,
        # Keyed by the text, not the picture: the same picture read anew - its
        # description, a video's frames - is found new claims in, not served the
        # claims found in an older reading of it.
        content_hash=text_hash(document),
        input_kind=intake.input_type.value,
        language=detect(authored if authored and authored.strip() else document).language.value,
    )
    return extracted


def _image_mime(data: bytes) -> str | None:
    """The type of an image pulled out of a PDF, from its first bytes."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    return None


def _reading_response(reading: OcrOutcome | None) -> ImageReadingResponse | None:
    if reading is None:
        return None
    return ImageReadingResponse(
        text=reading.text.strip(),
        description=reading.description or None,
        kind=reading.kind or None,
        publisher=reading.publisher or None,
        language=reading.language.language.value if reading.language else None,
    )


# What was read from recent images, by image hash, so a repeat served from the verdict
# cache - which makes no model call - can still show what the picture said. Bounded,
# and in memory: a restart forgets it, and a repeat then shows the verdict without it.
_READINGS_KEPT = 500


def _remembered_readings(request: Request) -> dict[str, ImageReadingResponse]:
    readings = getattr(request.app.state, "image_readings", None)
    if readings is None:
        readings = {}
        request.app.state.image_readings = readings
    return readings


def _remember(
    readings: dict[str, ImageReadingResponse], key: str, reading: ImageReadingResponse
) -> None:
    readings.pop(key, None)
    readings[key] = reading
    while len(readings) > _READINGS_KEPT:
        readings.pop(next(iter(readings)))


def _remembered_areas(request: Request) -> dict[str, float | None]:
    """How much of each recent picture is text (`OcrOutcome.text_area`), by image hash,
    beside its reading: what makes it designed (`looks_designed`) on a repeat."""
    areas = getattr(request.app.state, "image_text_areas", None)
    if areas is None:
        areas = {}
        request.app.state.image_text_areas = areas
    return areas


def _remember_area(request: Request, key: str, reading: OcrOutcome | None) -> None:
    if reading is None:
        return
    areas = _remembered_areas(request)
    areas.pop(key, None)
    areas[key] = reading.text_area
    while len(areas) > _READINGS_KEPT:
        areas.pop(next(iter(areas)))


async def _record_unprocessed_video(request: Request, *, case_id: UUID, intake: object) -> None:
    """Persist an honest empty case for a video this build cannot process."""
    database = getattr(request.app.state, "database", None)
    if database is None:
        return
    try:
        from app.db.repositories import CaseRepository

        async with database.connection() as conn:
            await CaseRepository(conn).create(
                request_id=str(case_id),
                input_type="video",
                language=getattr(getattr(intake, "language", None), "language", None)
                and intake.language.language.value,  # type: ignore[attr-defined]
                case_id=case_id,
            )
    except Exception:
        logger.exception("could not record the accepted video case")


@router.get(
    "/cases/{case_id}/evidence",
    response_model=list[EvidenceResponse],
    summary="Every citation behind a case",
)
async def get_case_evidence(case_id: UUID, request: Request) -> list[EvidenceResponse]:
    """The evidence list on its own, for a client rendering the ledger.

    Advisories are deliberately not served here. They are not evidence, and an
    endpoint named `/evidence` returning them would undo in the URL what the type
    system enforces everywhere else.
    """
    cases = getattr(request.app.state, "case_reader", None)
    if cases is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")

    stored = await cases.get(case_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such case")

    return [item for claim in stored.claims for item in claim.evidence]


@router.get(
    "/receipts/{receipt_id}",
    response_model=ReceiptResponse,
    summary="Verify a result receipt",
)
async def get_receipt(receipt_id: str, request: Request) -> ReceiptResponse:
    """Re-verify a receipt against the evidence currently stored.

    The check runs on every read rather than being cached: a receipt that verified
    yesterday and fails today is precisely the signal this endpoint exists to give.
    """
    receipts = getattr(request.app.state, "receipt_reader", None)
    if receipts is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")

    payload = await receipts.verify(receipt_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such receipt")

    return ReceiptResponse(**payload)


@router.post(
    "/cases/{case_id}/report",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Flag a verdict for human review",
)
async def report_case(case_id: UUID, request: Request) -> dict[str, str]:
    """A person disagrees with a verdict, or wants human eyes on it.

    This is the endpoint behind the app's Report button, which previously showed
    "Reported for human review" while sending nothing anywhere — a fabricated
    confirmation in a product whose one claim is that it does not fabricate.

    The reason is recorded as `user_reported`, distinct from the pipeline's own
    abstention routing, because "the system was unsure" and "a person disagreed"
    deserve different reviewer attention. 404 when the case does not exist: a report
    must point at a verdict that was actually issued.

    Once per case while it waits for a reviewer: a second report, from the same person
    or another, answers the same way with the item already queued.
    """
    queue = _review_queue(request)
    reader = getattr(request.app.state, "case_reader", None)
    if reader is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")

    stored = await reader.get(case_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such case")

    item_id = await queue.report(case_id)
    event(
        logger,
        "case reported by user",
        module="api.verify",
        outcome="ok",
        case_id=str(case_id),
    )
    return {"item_id": str(item_id), "status": "queued for human review"}


@router.get(
    "/review",
    response_model=list[ReviewItemResponse],
    summary="Cases the system declined to decide (M43)",
)
async def pending_reviews(request: Request) -> list[ReviewItemResponse]:
    # Reviewers only: the queue names cases and why each was held back.
    await _staff(request)
    queue = _review_queue(request)
    return [
        ReviewItemResponse(
            item_id=str(item.item_id),
            case_id=str(item.case_id),
            reason=item.reason.value,
            context=item.context,
            machine_status=item.machine_status,
            created_at=item.created_at,
        )
        for item in await queue.pending()
    ]


@router.post(
    "/review/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record a human label beside the machine verdict",
)
async def record_review(item_id: UUID, payload: ReviewLabelRequest, request: Request) -> None:
    """The machine verdict is never overwritten — both are kept (M43)."""
    await _staff(request)
    queue = _review_queue(request)
    await queue.record(
        item_id=item_id,
        label=HumanLabel(payload.label),
        reviewer=payload.reviewer,
        notes=payload.notes,
    )


def _review_queue(request: Request) -> Any:
    """The composed review queue — the pool adapter, which mirrors `ReviewQueue`."""
    queue = getattr(request.app.state, "review_queue", None)
    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the review queue is not available; the service is not fully configured",
        )
    return queue


@internal.post("/ingest-tick", status_code=status.HTTP_202_ACCEPTED)
async def ingest_tick(
    request: Request,
    x_factify_trigger: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """The scheduler's entry point (M24).

    Authenticated with a shared secret compared in constant time. A deployment with
    no configured secret denies every call, so an unconfigured service cannot be
    driven by anyone who finds the path.
    """
    settings = request.app.state.settings
    if not authenticate_trigger(x_factify_trigger, settings.ingest_trigger_secret):
        # 404 rather than 401: this endpoint is not public, and confirming it exists
        # to an unauthenticated caller is information they have no use for.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    # It answered "accepted" and ran nothing: the worker it looked for was never
    # created, so the corpus stood still from 2026-08-18.
    ingestion = getattr(request.app.state, "ingestion", None)
    if ingestion is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")

    result = await ingestion.tick()
    return {
        "status": "done",
        "feeds": str(result.feeds_attempted),
        "items_new": str(result.items_new),
        "factchecks_kept": str(result.factchecks_kept),
    }
