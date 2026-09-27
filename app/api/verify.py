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
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pypdf.errors import PdfReadError

from app.api.accounts import charge, check_cost, require_credit, signed_in
from app.api.schemas import (
    AcceptedResponse,
    AdvisoryResponse,
    ClaimResponse,
    ComponentResponse,
    CorrectionTextRequest,
    CorrectionTextResponse,
    EvidenceResponse,
    ImageReadingResponse,
    MediaReportResponse,
    QuoteLocationResponse,
    ReceiptResponse,
    ReceiptSummaryResponse,
    ReviewItemResponse,
    ReviewLabelRequest,
    SkippedCheckResponse,
    SourceReaderResponse,
    StrengthResponse,
    VerifyRequest,
    VerifyResponse,
    advisory_to_response,
    claim_anchor_response,
    evidence_to_response,
    media_report_to_response,
)
from app.domain.claim import Claim
from app.extraction.claims import ExtractedClaims
from app.extraction.language import detect
from app.extraction.model_wire import PDF_MIME
from app.extraction.ocr import OcrOutcome
from app.extraction.pdf import PdfRejected, first_pages
from app.extraction.pdf import extract as extract_pdf
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
from app.knowledge.registry import authenticate_trigger
from app.media.video import KeyframeExtractor
from app.observability.logging import event
from app.observability.middleware import REQUEST_ID_HEADER
from app.orchestration.correction import correction_message
from app.orchestration.deep import DeepChecks
from app.orchestration.pipeline import SkippedCheck, VerificationResult, claim_progress
from app.orchestration.progress import CheckProgress, current_progress, valid_key
from app.orchestration.review import HumanLabel
from app.orchestration.summary import case_summary
from app.security.fetcher import FetchResult
from app.sources.base import DEEP, current_depth
from app.sources.outlets import outlet_name
from app.sources.reader import SourceViews, read_source
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
    pipeline = getattr(request.app.state, "claim_pipeline", None)
    if pipeline is None:
        return ExtractedClaims(reason="claim extraction is not configured")

    text = intake.primary.text or ""
    language = intake.language.language.value

    # A forward that carries a link: "Must read! https://..." The message was checked
    # and the article it points at was never opened, so the substance of most shared
    # news went unread. The article is read and checked alongside the message, which
    # keeps whatever the message itself claims.
    partial: str | None = None
    if intake.input_type is InputType.TEXT:
        link = _first_link(text)
        if link is not None:
            page = await _read_linked_article(request, link)
            if page is not None:
                text = f"{text}\n\n{page.text}"
                partial = page.partial

    if not text.strip() and intake.input_type is InputType.URL:
        # A submitted link carries no text of its own — normalisation is local and
        # deliberately does not fetch. Read the page here, the same way a retrieved
        # source is read (M16), so "check this link" checks the article instead of
        # abstaining on an empty body. This was the gap that made every URL a no-op.
        page = await _read_linked_article(request, intake.primary.source_url or "")
        if page is None:
            return ExtractedClaims(reason="the linked page could not be read")
        text = page.text
        partial = page.partial
        # The article's own language, detected on its body — not the URL's, which
        # was detected on an empty string and is always the default.
        language = detect(text).language.value

    if not text.strip():
        return ExtractedClaims(reason="no readable text in this submission")

    extracted: ExtractedClaims = await pipeline.extract(
        text,
        content_hash=intake.primary.sha256,
        input_kind=intake.input_type.value,
        language=language,
    )
    if partial and extracted.claims:
        extracted = replace(extracted, partial_source=partial)
    return extracted


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
# very long reference page is truncated to its opening, where the headline claims sit.
_MAX_ARTICLE_CHARS = 6000

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
    return LinkedPage("\n\n".join(parts), partial) if parts else None


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
    those rows actually hold.
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
            SkippedCheckResponse(check=item.check, reason=item.reason) for item in result.skipped
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
    deep = payload.mode == "deep"
    key = _followed_by(request)

    # A deep check is followed by its case id, from the 202; see `_start_deep`.
    async with _watched(request, None if deep else key) as watching:
        # Who is asking, and whether they may: decided here, from the credit ledger.
        user = await signed_in(request)
        cost = check_cost(request, deep=deep)
        await require_credit(request, user, cost)

        if deep:
            return _start_deep(payload, request, user, cost)

        response = await with_receipt(request, await _checked(payload, request, arrived))
        await charge(request, user, cost, deep=deep)
        if watching is not None:
            await watching.done(response.case_id)
    return _echo(response, key)


def _start_deep(payload: VerifyRequest, request: Request, user: Any, cost: int) -> JSONResponse:
    """Start a deep check in the background and answer with its case id at once.

    The same check as a normal one, run with the deep profile (`DEEP`): more claims,
    queries and pages, and three minutes instead of fifty-five seconds. Charged only
    when it finishes with an answer.
    """
    runs: DeepChecks = request.app.state.deep_checks
    case_id = uuid4()

    async def work(progress: Any) -> VerifyResponse:
        depth = current_depth.set(DEEP)
        counting = claim_progress.set(progress)
        try:
            async with _watched(request, str(case_id)) as watching:
                response = await with_receipt(
                    request,
                    await _checked(payload, request, time.perf_counter(), case_id=case_id),
                )
                await charge(request, user, cost, deep=True)
                if watching is not None:
                    await watching.done(str(case_id))
        finally:
            claim_progress.reset(counting)
            current_depth.reset(depth)
        return response

    runs.start(str(case_id), work)
    accepted = AcceptedResponse(
        case_id=str(case_id),
        poll_url=f"/v1/cases/{case_id}",
        estimated_seconds=int(DEEP.seconds * 2 / 3),
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content=accepted.model_dump(mode="json")
    )


async def _checked(
    payload: VerifyRequest, request: Request, arrived: float, *, case_id: UUID | None = None
) -> VerifyResponse:
    """The check itself; `verify` above decides who may run it and records the cost."""
    orchestrator = get_orchestrator(request)

    try:
        intake = (
            normalise_url(payload.url, consent=payload.consent_to_process_media)
            if payload.url
            else normalise_text(payload.text or "", consent=payload.consent_to_process_media)
        )
    except IntakeRejected as rejected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(rejected)
        ) from rejected

    case_id = case_id or uuid4()

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
        return await cached_full_response(request, hit) or to_response(hit)

    extracted = await extract_claims_for(request, intake)

    # A link nobody could open is not a verdict about the link.
    #
    # The gap was reported as a skipped check and the response still read "not
    # enough evidence to decide" — a sentence about evidence, for a page that was
    # never fetched. Measured on an Olympics.com report of a result carried
    # worldwide: zero bytes, zero claims, and an answer that blamed the record.
    # "We could not read this page" and "we read it and found nothing" are
    # different answers and the caller has to be able to tell them apart.
    #
    # Nor is a link with no claims to check. It used to pass through when extraction
    # ran cleanly and found nothing, and a verification of zero claims came back
    # "Unconfirmed" — on a Reuters bot wall and on a page whose every claim failed
    # its anchor. Unconfirmed means sources were looked for; here none were.
    if not extracted.claims and intake.input_type is InputType.URL:
        reason = extracted.reason or "no checkable claims were found on the page"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{reason}. Nothing was checked. Try pasting the text of "
                "the page instead of the link."
            ),
        )

    # The pages the person submitted, which can never be evidence for themselves.
    own_pages: set[str] = set()
    if intake.primary.source_url:
        own_pages.add(page_key(intake.primary.source_url))
    embedded = (
        _first_link(intake.primary.text or "") if intake.input_type is InputType.TEXT else None
    )
    if embedded is not None:
        own_pages.add(page_key(embedded))

    result = await orchestrator.verify(  # type: ignore[attr-defined]
        intake,
        case_id=case_id,
        claims=list(extracted.claims),
        started_at=arrived,
        fresh=payload.recheck,
        own_pages=frozenset(own_pages),
    )

    cached = await cached_full_response(request, result)
    if cached is not None:
        return cached

    # Extraction failing is a gap in the answer, not a failure of the request. It is
    # attached so the response can say the text could not be read into claims rather
    # than presenting "nothing to check" as "nothing wrong".
    if extracted.reason:
        result.skipped.append(SkippedCheck(check="claim_extraction", reason=extracted.reason))
    if extracted.partial_source:
        result.skipped.append(SkippedCheck(check="linked_page", reason=extracted.partial_source))

    event(
        logger,
        "verify request served",
        module="api.verify",
        outcome="ok",
        action=result.action.value,
        claims=len(extracted.claims),
        from_cache=result.from_cache,
        elapsed_ms=result.elapsed_ms,
    )
    return to_response(result)


@router.get(
    "/cases/{case_id}",
    response_model=VerifyResponse,
    summary="Retrieve a previously computed case",
)
async def get_case(case_id: UUID, request: Request) -> VerifyResponse | JSONResponse:
    # A deep check still running answers with its progress, and a finished one with
    # its result, before the ledger is asked: a deep check that was served from the
    # cache is stored under the original case, not this one.
    runs: DeepChecks | None = getattr(request.app.state, "deep_checks", None)
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
                },
            )
        if run.status == "failed":
            return JSONResponse(status_code=run.error_status, content={"detail": run.error_detail})
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


# How long one stream stays open: past a deep check's three minutes.
_STREAM_SECONDS = 300.0
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

    `key` is the `X-Request-ID` the app sent with a check, or a deep check's case id.
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
) -> VerifyResponse | JSONResponse:
    """Images and PDFs resolve synchronously; video returns 202.

    Video is split off because it cannot finish inside the 3-8 second budget. Holding
    the request open would end in a gateway timeout, which tells the client nothing
    it can act on — a case id it can poll does.
    """
    key = _followed_by(request)
    async with _watched(request, key) as watching:
        user = await signed_in(request)
        cost = check_cost(request, deep=False)
        await require_credit(request, user, cost)

        response = await _checked_file(request, file, consent_to_process_media, recheck)
        if isinstance(response, VerifyResponse):
            response = _echo(await with_receipt(request, response), key)
        await charge(request, user, cost, deep=False)
        if watching is not None:
            # A video is answered with a case id to poll, which is where it ends too.
            case_id = (
                response.case_id
                if isinstance(response, VerifyResponse)
                else json.loads(bytes(response.body))["case_id"]
            )
            await watching.done(case_id)
    return response


async def _checked_file(
    request: Request, file: UploadFile, consent_to_process_media: bool, recheck: bool
) -> VerifyResponse | JSONResponse:
    """The upload check itself; `verify_file` above meters it."""
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(rejected)
        ) from rejected

    case_id = uuid4()

    if intake.input_type is InputType.VIDEO:
        return _start_video(request, intake, data, case_id=case_id, recheck=recheck)

    # The picture's own checks - credentials, earlier copies, the AI and editing
    # signals - run alongside the reading and the fact-check, and join the answer.
    inspection = _inspect_picture(request, intake)
    response = await _checked_upload(request, intake, case_id=case_id, recheck=recheck)
    return await _with_media(response, inspection)


async def _checked_upload(
    request: Request, intake: NormalisedIntake, *, case_id: UUID, recheck: bool
) -> VerifyResponse:
    """A picture or a PDF, read and checked. Also a video's representative frame."""
    orchestrator = get_orchestrator(request)

    # Probed before media preparation (hashing, embedding, OCR), for the same reason
    # the text path probes before extraction: a repeat should cost nothing. "Check
    # again" is the exception, as it is there.
    readings = _remembered_readings(request)
    hit = (
        None if recheck else await orchestrator.cached(intake, case_id=case_id)  # type: ignore[attr-defined]
    )
    if hit is not None:
        served = await cached_full_response(request, hit) or to_response(hit)
        shown = readings.get(intake.primary.sha256)
        if shown is None and intake.input_type is InputType.IMAGE:
            # Remembered only in memory, so a repeat after a restart reads the picture
            # again - one model call, against a check that is otherwise free - rather
            # than showing a verdict with no sign of what it was about.
            _, reading, _ = await _read_document(request, intake)
            shown = _reading_response(reading)
            if shown is not None:
                _remember(readings, intake.primary.sha256, shown)
        return served.model_copy(update={"image_reading": shown})

    # Read before checking. An image or a PDF used to reach the checker with no claims
    # at all: a screenshot of a forward announcing a ban on ₹500 notes was
    # fingerprinted, never read, and came back "Unconfirmed". Its text is now read and
    # checked exactly as a pasted message is - the same extraction, the same search,
    # the same rules - and a link in it is opened, as a link in a message is.
    document, reading, notes = await _read_document(request, intake)
    claims: list[Claim] = []
    own_pages: set[str] = set()
    if document.strip():
        link = _first_link(document)
        if link is not None:
            page = await _read_linked_article(request, link)
            if page is not None:
                document = f"{document}\n\n{page.text}"
                own_pages.add(page_key(link))
        extracted = await _extract_from_document(request, intake, document)
        claims = list(extracted.claims)
        if extracted.reason:
            notes.append(SkippedCheck(check="claim_extraction", reason=extracted.reason))

    # With no text to check, the image's own questions are asked instead: has it been
    # published before, and does it carry provenance (see `MediaVerification`).
    result = await orchestrator.verify(  # type: ignore[attr-defined]
        intake,
        case_id=case_id,
        claims=claims,
        fresh=recheck,
        own_pages=frozenset(own_pages),
    )

    response = await cached_full_response(request, result) or to_response(result)
    shown = _reading_response(reading)
    if shown is not None:
        _remember(readings, intake.primary.sha256, shown)
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
    )
    return response.model_copy(
        update={
            "image_reading": shown,
            "skipped": (
                *response.skipped,
                *(SkippedCheckResponse(check=n.check, reason=n.reason) for n in notes),
            ),
        }
    )


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
    response: VerifyResponse, inspection: asyncio.Task[_MediaShown] | None
) -> VerifyResponse:
    """The answer with the picture checks beside it. A check that failed is left out."""
    if inspection is None:
        return response
    try:
        media, advisories = await inspection
    except Exception:
        logger.exception("the picture checks failed; the answer is sent without them")
        return response
    return with_earlier_copy(
        response.model_copy(
            update={"media_report": media, "advisories": (*response.advisories, *advisories)}
        )
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
    request: Request, intake: NormalisedIntake, data: bytes, *, case_id: UUID, recheck: bool
) -> JSONResponse:
    """Check a video in the background and answer with its case id at once.

    It used to be recorded as "not processed" and nothing else: the 202 led to an
    empty case. It is now checked from its still frames (`app/media/video.py`) - the
    middle one read and fact-checked like a picture, and every one put through the
    picture checks - and the app collects the answer from `/v1/cases/{id}`.
    """
    runs: DeepChecks = request.app.state.deep_checks

    async def work(progress: Any) -> VerifyResponse:
        del progress
        # Followed by its case id, which the app has from the 202, like a deep check.
        async with _watched(request, str(case_id)) as watching:
            response = await with_receipt(
                request,
                await _checked_video(request, intake, data, case_id=case_id, recheck=recheck),
            )
            if watching is not None:
                await watching.done(str(case_id))
        return response

    runs.start(str(case_id), work)
    accepted = AcceptedResponse(
        case_id=str(case_id), poll_url=f"/v1/cases/{case_id}", estimated_seconds=45
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content=accepted.model_dump(mode="json")
    )


async def _checked_video(
    request: Request, intake: NormalisedIntake, data: bytes, *, case_id: UUID, recheck: bool
) -> VerifyResponse:
    extracted = await KeyframeExtractor().extract(data)
    if not extracted.succeeded:
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

    frames = [frame.data for frame in extracted.keyframes]
    settings = request.app.state.settings
    middle = normalise_upload(
        frames[len(frames) // 2],
        max_bytes=settings.limits.max_upload_bytes,
        declared_type="image/jpeg",
        consent=True,
    )
    inspector = getattr(request.app.state, "media_inspector", None)
    inspection = asyncio.create_task(inspector.inspect_video(data, frames)) if inspector else None
    response = await _checked_upload(request, middle, case_id=case_id, recheck=recheck)
    notes = (
        SkippedCheckResponse(
            check="video_frames",
            reason=f"checked {len(frames)} still frames"
            + (f"; {'; '.join(extracted.limitations)}" if extracted.limitations else ""),
        ),
    )
    response = response.model_copy(update={"skipped": (*response.skipped, *notes)})
    if inspection is None:
        return response
    try:
        report = await inspection
    except Exception:
        logger.exception("the video's picture checks failed")
        return response
    return response.model_copy(
        update={
            "media_report": media_report_to_response(report, thumbnails=_THUMBNAILS),
            "advisories": (
                *response.advisories,
                *(advisory_to_response(item) for item in report.advisories),
            ),
        }
    )


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


async def _read_document(
    request: Request, intake: NormalisedIntake
) -> tuple[str, OcrOutcome | None, list[SkippedCheck]]:
    """The text of an uploaded image or PDF, what the image showed, and any gap.

    An image is read by the image reader (`app/extraction/ocr.py`). A PDF's own text
    layer is used when it has one; a scanned PDF has none, so its page images are
    read the same way a screenshot is.
    """
    primary = intake.primary
    reader = getattr(request.app.state, "ocr", None)
    notes: list[SkippedCheck] = []
    if primary.data is None:
        return "", None, notes

    if intake.input_type is InputType.IMAGE:
        if reader is None:
            notes.append(SkippedCheck(check="image_text", reason="reading images is not set up"))
            return "", None, notes
        reading: OcrOutcome = await reader.transcribe(
            primary.data, mime_type=primary.mime_type or "image/jpeg"
        )
        if not reading.succeeded:
            notes.append(
                SkippedCheck(
                    check="image_text", reason=f"the image could not be read ({reading.reason})"
                )
            )
            return "", None, notes
        if reading.cut_off:
            notes.append(
                SkippedCheck(
                    check="image_text",
                    reason=(
                        "the image holds more text than is read at once; only its start was checked"
                    ),
                )
            )
        return reading.text, reading, notes

    if intake.input_type is InputType.PDF:
        try:
            pdf = await asyncio.to_thread(extract_pdf, primary.data)
        except PdfRejected as rejected:
            notes.append(SkippedCheck(check="document_text", reason=rejected.reason))
            return "", None, notes
        if not pdf.needs_ocr and not pdf.text_is_broken:
            return pdf.text[:_MAX_ARTICLE_CHARS], None, notes

        # Scanned, or typed with its Hindi scrambled in the text layer ("विज्ञान" as
        # "िव ान"): the pages are read as a person sees them - the document itself, cut
        # to its first pages, in one call.
        if reader is not None:
            whole = await _read_pages(reader, primary.data, page_count=pdf.page_count)
            if whole is not None:
                read, gaps = whole
                notes.extend(gaps)
                return read.text[:_MAX_ARTICLE_CHARS], read, notes
        if not pdf.needs_ocr:
            notes.append(
                SkippedCheck(
                    check="document_text", reason="the document's text is scrambled and unreadable"
                )
            )
            return "", None, notes

        first: OcrOutcome | None = None
        pages: list[str] = []
        if reader is not None:
            for image in pdf.embedded_images[:_SCANNED_PAGES_READ]:
                mime = _image_mime(image)
                if mime is None:
                    continue
                outcome: OcrOutcome = await reader.transcribe(image, mime_type=mime)
                if outcome.has_text:
                    pages.append(outcome.text)
                    first = first or outcome
        if not pages:
            notes.append(
                SkippedCheck(check="document_text", reason="the document has no readable text")
            )
        return "\n\n".join(pages)[:_MAX_ARTICLE_CHARS], first, notes

    return "", None, notes


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
    request: Request, intake: NormalisedIntake, document: str
) -> ExtractedClaims:
    """Claims from the text read out of an upload, anchored in that text."""
    pipeline = getattr(request.app.state, "claim_pipeline", None)
    if pipeline is None:
        return ExtractedClaims(reason="claim extraction is not configured")
    extracted: ExtractedClaims = await pipeline.extract(
        document,
        content_hash=intake.primary.sha256,
        input_kind=intake.input_type.value,
        language=detect(document).language.value,
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
