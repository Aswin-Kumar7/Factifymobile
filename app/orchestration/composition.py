"""Composition root — where the served application is actually assembled.

Until this module existed, `app.state.orchestrator` was never assigned anywhere in
the repository. `get_orchestrator` read it, found `None`, and returned 503, so every
request to `/verify` failed with "service unavailable" no matter how healthy the
system underneath was. The only place an `Orchestrator` had ever been constructed was
the audit runner, with a single resolver and stubs for the cache and the governor.

Two shapes are in tension here and the split below is how they are reconciled:

  - **Process-lifetime objects.** The embedders load ONNX weights and cost seconds;
    the fetchers hold connection pools; the resolvers hold both. All are built once.
  - **Connection-scoped objects.** `CacheService` and `Governor` each take a live
    connection rather than the pool, because both read and write inside the caller's
    transaction. Holding one connection for the life of the process would pin a pool
    slot forever and serialise every request behind it.

So the object in `app.state` is a thin per-request assembler rather than an
`Orchestrator` itself. It keeps the expensive things and builds the cheap ones per
call, which is what lets the fixed order in `Orchestrator` stay exactly as written.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.config import Settings
from app.db.pool import Database
from app.domain.claim import Claim
from app.domain.enums import SourceRisk
from app.domain.evidence import Advisory
from app.embeddings.image import ImageEmbedder
from app.embeddings.text import TextEmbedder
from app.extraction.claims import ClaimPipeline
from app.extraction.llm import LLMExtractor
from app.intake.normalizer import NormalisedIntake
from app.observability.logging import event
from app.orchestration.adapters import PoolCacheService, PoolGovernor, PoolReviewQueue
from app.orchestration.ledger import CaseReader, Ledger
from app.orchestration.media import MediaVerification
from app.orchestration.pipeline import Orchestrator, SkippedCheck, VerificationResult
from app.security.fetcher import SecureFetcher
from app.sources.base import SourceResolver
from app.sources.corpus import CorpusCorroboration, CorpusResolver
from app.sources.factcheck import FactCheckRecord, FactCheckResolver, parse_rating_from_title
from app.sources.reasoning import PassageReasoner

logger = logging.getLogger("facify.composition")

# Two fetchers with different patience, because they wait on different things. A
# model call legitimately takes tens of seconds; a news page that has not answered in
# twenty is not going to. One shared timeout meant every dead source burned the
# model's budget — measured in the audit, where fetch timeouts outlasted verification.
SOURCE_TIMEOUT_SECONDS = 20.0
MODEL_TIMEOUT_SECONDS = 90.0


class ServedOrchestrator:
    """The process-lifetime verification surface.

    One `Orchestrator` for the process, not one per request. The per-request version
    held a pool connection across the *whole* verification — six source fetches at a
    20 second timeout and a model call at up to 90 — so ten concurrent requests
    pinned the entire pool, and the reasoner then needed an eleventh connection
    while all ten were held. It also rebuilt `Semaphore(6)` and the burst window per
    request, which made both limiters count against nothing: the publisher-socket
    ceiling and the per-minute cap only exist if there is exactly one of each.

    Database work now goes through the pool adapters, which check a connection out
    for the microseconds the query takes. What remains per request is what must be:
    media claim preparation, and the ledger write at the end.
    """

    def __init__(
        self,
        *,
        database: Database,
        orchestrator: Orchestrator,
        media: MediaVerification | None = None,
        review_queue: PoolReviewQueue | None = None,
    ) -> None:
        self._database = database
        self._orchestrator = orchestrator
        self._media = media
        self._review_queue = review_queue

    async def verify(
        self,
        intake: NormalisedIntake,
        *,
        case_id: UUID,
        claims: list[Claim],
        advisories: list[Advisory] | None = None,
        source_risk: SourceRisk = SourceRisk.UNKNOWN,
    ) -> VerificationResult:
        # An image arrives with no claims, because there is no text to extract them
        # from. Without this the resolvers had nothing to run against and every
        # upload returned a clean, empty 200.
        #
        # Media resolvers carry per-request findings, so this request gets its own
        # orchestrator over them. The text path — every other request — uses the
        # shared one, which is what keeps the semaphore a real ceiling.
        orchestrator = self._orchestrator
        if self._media is not None and not claims:
            media_claims, media_resolvers = await self._media.prepare(intake)
            if media_claims:
                claims = media_claims
                orchestrator = self._orchestrator.with_resolvers(
                    [*self._orchestrator.resolvers, *media_resolvers]
                )

        result = await orchestrator.verify(
            intake,
            case_id=case_id,
            claims=claims,
            advisories=advisories,
            source_risk=source_risk,
        )

        # Written after the verdict exists and never allowed to change it. A cached
        # result is not rewritten: it was persisted when first computed, and writing
        # it again would record a second case for one verification. The connection is
        # checked out here, after every fetch and model call has already finished.
        if not result.from_cache:
            async with self._database.connection() as conn:
                written = await Ledger(conn).persist(
                    result,
                    request_id=str(case_id),
                    input_type=intake.input_type.value,
                    language=intake.language.language.value,
                    consent_to_process_media=getattr(intake, "consent_to_process_media", False),
                )
            if not written:
                result.skipped.append(
                    SkippedCheck(
                        check="ledger",
                        reason="the verdict was not recorded; it cannot be retrieved later",
                    )
                )
            elif self._review_queue is not None:
                # Routed only after a successful persist: the queue row carries a
                # foreign key to the case, and M43's whole promise — abstentions go
                # to a human — was never kept because nothing ever called route().
                # A routing failure is logged inside the queue and must not touch
                # the verdict.
                try:
                    await self._review_queue.route(result)
                except Exception:
                    logger.exception("review routing failed; the verdict stands")

        return result


async def load_factcheck_records(database: Database) -> list[FactCheckRecord]:
    """Published adjudications, read from the corpus.

    Deliberately sourced from `corpus_item` rather than `factcheck_record`: the
    dedicated table holds zero rows, because ingestion writes fact-checker feeds into
    the corpus like any other source. Reading the empty table instead would leave the
    resolver with nothing and look like an absence of fact-checks rather than a wiring
    mistake.
    """
    async with database.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT ci.title, ci.canonical_url, ci.publisher, ci.published_at
              FROM corpus_item ci
              JOIN source s ON s.id = ci.source_id
             WHERE s.source_class = 'factchecker'
               AND ci.canonical_url IS NOT NULL
            """
        )
        rows = list(await cursor.fetchall())

    return [
        FactCheckRecord(
            claim_text=str(row["title"] or ""),
            normalized_text=" ".join(str(row["title"] or "").lower().split()),
            url=str(row["canonical_url"]),
            rating=parse_rating_from_title(str(row["title"] or "")),
            publisher=row["publisher"],
            published_at=row["published_at"],
            retrieved_at=row["published_at"],
        )
        for row in rows
    ]


async def build(settings: Settings) -> dict[str, Any]:
    """Assemble everything the served application needs.

    Returns the objects to attach to `app.state`. Raises nothing on a missing
    optional provider — an unconfigured extractor yields no claims *and a reason*,
    which the response surfaces, rather than failing the boot.
    """
    if settings.database_url is None:
        raise RuntimeError("database_url is required to serve; nothing can be verified without it")

    database = Database(str(settings.database_url))
    await database.open()

    embedder = (
        TextEmbedder(model_id=settings.models.text_embedding)
        if settings.models.text_embedding
        else TextEmbedder()
    )

    source_fetcher = SecureFetcher(timeout_seconds=SOURCE_TIMEOUT_SECONDS)

    records = await load_factcheck_records(database)

    # Order is not significant — the pipeline runs resolvers concurrently — but the
    # set is: corpus retrieval is what makes the 2,000-item ingested corpus reachable
    # at all, and fact-checks are the only Tier C source there is.
    # CLIP, for near-duplicate media verification. Loaded once: it is ~350 MiB
    # resident and the whole point of local inference is not paying that per request.
    image_embedder = ImageEmbedder()

    # One governor and one cache for the process. The burst window and the fetch
    # semaphore only limit anything if there is exactly one of each; per-request
    # copies counted every request against itself and nothing against the process.
    governor = PoolGovernor(database, settings.providers)
    cache = PoolCacheService(database)

    # The reasoner reads fetched passages and judges them against the claim. Only
    # built when a model is configured; without it the corpus resolver falls back to
    # word overlap, which cannot detect contradiction and reports as much.
    reasoner: PassageReasoner | None = None
    if settings.llm.enabled and settings.llm.api_key:
        reasoner = PassageReasoner(
            fetcher=SecureFetcher(timeout_seconds=MODEL_TIMEOUT_SECONDS),
            governor=governor,
            endpoint=settings.llm.endpoint,
            api_key=settings.llm.api_key.get_secret_value(),
            model_id=settings.models.extraction,
        )

    corpus = CorpusResolver(
        database=database,
        embedder=embedder,
        fetcher=source_fetcher,
        reasoner=reasoner,
    )
    resolvers: list[SourceResolver] = [
        corpus,
        FactCheckResolver(records=records, api_available=False),
    ]

    review_queue = PoolReviewQueue(database)

    orchestrator = Orchestrator(
        cache=cache,
        governor=governor,
        resolvers=resolvers,
        extractor_version=_extractor_version(),
        model_id=settings.models.extraction,
        corroboration=CorpusCorroboration(resolver=corpus, database=database),
    )

    state: dict[str, Any] = {
        "database": database,
        "embedder": embedder,
        "case_reader": CaseReader(database),
        "review_queue": review_queue,
        "orchestrator": ServedOrchestrator(
            database=database,
            orchestrator=orchestrator,
            media=MediaVerification(database=database, embedder=image_embedder),
            review_queue=review_queue,
        ),
    }

    if settings.llm.enabled and settings.llm.api_key:
        # Built once. The previous shape checked a connection out and then held it
        # across the model call — up to 90 seconds of pool time per extraction spent
        # waiting on a provider. The pool adapters check connections out only for the
        # budget row and the cache row.
        state["claim_pipeline"] = ClaimPipeline(
            LLMExtractor(
                fetcher=SecureFetcher(timeout_seconds=MODEL_TIMEOUT_SECONDS),
                governor=governor,  # type: ignore[arg-type]
                endpoint=settings.llm.endpoint,
                api_key=settings.llm.api_key.get_secret_value(),
                model_id=settings.models.extraction,
            ),
            cache=cache,  # type: ignore[arg-type]
        )

    await _prewarm(embedder, image_embedder)

    event(
        logger,
        "application composed",
        module="composition",
        outcome="ok",
        resolvers=[r.name for r in resolvers],
        factcheck_records=len(records),
        extraction_configured="claim_pipeline" in state,
    )
    return state


async def _prewarm(embedder: TextEmbedder, image_embedder: ImageEmbedder) -> None:
    """Load both ONNX models before the first request instead of inside it.

    Lazy loading put ~2s of text-model load and ~4s of CLIP load inside whichever
    request arrived first — on demo day, the judge's. Worse, the load ran on the
    event loop, so every concurrent request stalled behind it. Paying the cost at
    startup moves it to a moment nobody is waiting on.

    Failures are logged and swallowed: an embedder that cannot load degrades exactly
    as it would have at first use, and a warmup problem must not stop the service
    from answering the requests that do not need it.
    """
    import asyncio

    def _warm() -> None:
        embedder.embed(["warmup"], language="en")
        _ = image_embedder.available

    try:
        await asyncio.to_thread(_warm)
        event(logger, "models prewarmed", module="composition", outcome="ok")
    except Exception as error:
        event(
            logger,
            "model prewarm failed; first use will retry",
            module="composition",
            outcome="degraded",
            failure_reason=f"{type(error).__name__}: {error}",
            level=logging.WARNING,
        )


def _extractor_version() -> str:
    from app.extraction.llm import EXTRACTOR_VERSION

    return EXTRACTOR_VERSION
