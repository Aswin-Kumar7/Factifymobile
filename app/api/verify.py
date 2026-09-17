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
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.schemas import (
    AcceptedResponse,
    ClaimResponse,
    ComponentResponse,
    EvidenceResponse,
    ReceiptResponse,
    ReviewItemResponse,
    ReviewLabelRequest,
    SkippedCheckResponse,
    StrengthResponse,
    VerifyRequest,
    VerifyResponse,
    advisory_to_response,
    evidence_to_response,
)
from app.extraction.claims import ExtractedClaims
from app.extraction.language import detect
from app.extraction.web import extract as extract_article
from app.intake.normalizer import (
    InputType,
    IntakeRejected,
    NormalisedIntake,
    normalise_text,
    normalise_upload,
    normalise_url,
)
from app.knowledge.registry import authenticate_trigger
from app.observability.logging import event
from app.orchestration.pipeline import SkippedCheck, VerificationResult
from app.orchestration.review import HumanLabel
from app.security.fetcher import FetchResult

logger = logging.getLogger("facify.api.verify")

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

    if not text.strip() and intake.input_type is InputType.URL:
        # A submitted link carries no text of its own — normalisation is local and
        # deliberately does not fetch. Read the page here, the same way a retrieved
        # source is read (M16), so "check this link" checks the article instead of
        # abstaining on an empty body. This was the gap that made every URL a no-op.
        article = await _read_linked_article(request, intake.primary.source_url or "")
        if article is None:
            return ExtractedClaims(reason="the linked page could not be read")
        text = article
        # The article's own language, detected on its body — not the URL's, which
        # was detected on an empty string and is always the default.
        language = detect(text).language.value

    if not text.strip():
        return ExtractedClaims(reason="no readable text in this submission")

    return await pipeline.extract(  # type: ignore[no-any-return]
        text,
        content_hash=intake.primary.sha256,
        input_kind=intake.input_type.value,
        language=language,
    )


# Longest article body sent to extraction. A news story fits well within this; a
# very long reference page is truncated to its opening, where the headline claims sit.
_MAX_ARTICLE_CHARS = 6000


async def _read_linked_article(request: Request, url: str) -> str | None:
    """Fetch a submitted link and return its readable article text, or None.

    Only HTML is read here: a PDF or image shared as a link is a file, and the file
    endpoint handles those. A page with no extractable body — a login wall, a
    JavaScript shell, a social-media permalink — returns None, and the caller says so
    plainly rather than presenting an empty read as "nothing to check".
    """
    reader = getattr(request.app.state, "url_reader", None)
    if reader is None or not url:
        return None

    result = await reader.fetch(url, provider="url_intake")
    if not isinstance(result, FetchResult):
        return None

    content_type = (result.content_type or "").lower()
    if content_type and "html" not in content_type and "xml" not in content_type:
        return None

    article = extract_article(result.text, url=url)
    if not article.is_usable:
        return None

    # Title and body together: the headline carries the primary claim, the body the
    # rest, so even a one-paragraph story yields something to check. The body is
    # capped: extraction takes at most a handful of claims and the consequential ones
    # sit near the top, while a long page (a Wikipedia article runs to tens of
    # thousands of characters) would push one extraction call past the model's
    # per-minute token budget and come back 429.
    body = (article.body or "")[:_MAX_ARTICLE_CHARS]
    parts = [part for part in (article.title, body) if part and part.strip()]
    return "\n\n".join(parts) if parts else None


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
            "action_reason": result.case_decision.reason,
            "elapsed_ms": result.elapsed_ms,
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
        )
        for outcome in result.claims
    )

    return VerifyResponse(
        case_id=str(result.case_id),
        action=result.action,
        action_reason=result.case_decision.reason,
        rule_version=result.rule_version,
        claims=claims,
        advisories=tuple(advisory_to_response(item) for item in result.advisories),
        skipped=tuple(
            SkippedCheckResponse(check=item.check, reason=item.reason) for item in result.skipped
        ),
        completeness_note=result.completeness_note(),
        receipt_url=receipt_url,
        retrieved_at=datetime.now(UTC),
        from_cache=result.from_cache,
        elapsed_ms=result.elapsed_ms,
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify a URL or a block of text",
)
async def verify(payload: VerifyRequest, request: Request) -> VerifyResponse:
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

    case_id = uuid4()
    extracted = await extract_claims_for(request, intake)

    result = await orchestrator.verify(  # type: ignore[attr-defined]
        intake, case_id=case_id, claims=list(extracted.claims)
    )

    cached = await cached_full_response(request, result)
    if cached is not None:
        return cached

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
    )
    return to_response(result)


@router.get(
    "/cases/{case_id}",
    response_model=VerifyResponse,
    summary="Retrieve a previously computed case",
)
async def get_case(case_id: UUID, request: Request) -> VerifyResponse:
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
    return stored


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
) -> VerifyResponse | JSONResponse:
    """Images and PDFs resolve synchronously; video returns 202.

    Video is split off because it cannot finish inside the 3-8 second budget. Holding
    the request open would end in a gateway timeout, which tells the client nothing
    it can act on — a case id it can poll does.
    """
    orchestrator = get_orchestrator(request)
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
        # The 202 must lead somewhere. No video worker is deployed in this build,
        # and until this write existed the returned case id pointed at nothing:
        # the client polled `/v1/cases/{id}`, got 404 fifteen times, and gave up on
        # a promise the server never intended to keep. Recording the case makes the
        # poll terminate in an honest answer — routed to review, nothing checked —
        # instead of an infinite pending.
        asyncio.get_running_loop().create_task(
            _record_unprocessed_video(request, case_id=case_id, intake=intake)
        )
        accepted = AcceptedResponse(case_id=str(case_id), poll_url=f"/v1/cases/{case_id}")
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED, content=accepted.model_dump(mode="json")
        )

    result = await orchestrator.verify(intake, case_id=case_id, claims=[])  # type: ignore[attr-defined]

    cached = await cached_full_response(request, result)
    if cached is not None:
        return cached

    return to_response(result)


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
    x_facify_trigger: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """The scheduler's entry point (M24).

    Authenticated with a shared secret compared in constant time. A deployment with
    no configured secret denies every call, so an unconfigured service cannot be
    driven by anyone who finds the path.
    """
    settings = request.app.state.settings
    if not authenticate_trigger(x_facify_trigger, settings.ingest_trigger_secret):
        # 404 rather than 401: this endpoint is not public, and confirming it exists
        # to an unauthenticated caller is information they have no use for.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    worker = getattr(request.app.state, "ingestion_worker", None)
    if worker is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="unavailable")

    return {"status": "accepted"}
