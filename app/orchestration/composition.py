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

from app.cache.service import CacheService
from app.config import Settings
from app.db.pool import Database
from app.domain.claim import Claim
from app.domain.enums import SourceRisk
from app.domain.evidence import Advisory
from app.embeddings.text import TextEmbedder
from app.extraction.claims import ClaimPipeline, ExtractedClaims
from app.extraction.llm import LLMExtractor
from app.governor.governor import Governor
from app.intake.normalizer import NormalisedIntake
from app.observability.logging import event
from app.orchestration.pipeline import Orchestrator, VerificationResult
from app.security.fetcher import SecureFetcher
from app.sources.base import SourceResolver
from app.sources.corpus import CorpusResolver
from app.sources.factcheck import FactCheckRecord, FactCheckResolver, parse_rating_from_title

logger = logging.getLogger("facify.composition")

# Two fetchers with different patience, because they wait on different things. A
# model call legitimately takes tens of seconds; a news page that has not answered in
# twenty is not going to. One shared timeout meant every dead source burned the
# model's budget — measured in the audit, where fetch timeouts outlasted verification.
SOURCE_TIMEOUT_SECONDS = 20.0
MODEL_TIMEOUT_SECONDS = 90.0


class RequestScopedOrchestrator:
    """Builds an `Orchestrator` per request over shared, expensive components.

    Presents the same `verify` signature the endpoint already calls, so the API layer
    does not need to know that the cache and the governor are connection-bound.
    """

    def __init__(
        self,
        *,
        database: Database,
        resolvers: list[SourceResolver],
        settings: Settings,
        extractor_version: str,
    ) -> None:
        self._database = database
        self._resolvers = resolvers
        self._settings = settings
        self._extractor_version = extractor_version

    async def verify(
        self,
        intake: NormalisedIntake,
        *,
        case_id: UUID,
        claims: list[Claim],
        advisories: list[Advisory] | None = None,
        source_risk: SourceRisk = SourceRisk.UNKNOWN,
    ) -> VerificationResult:
        async with self._database.connection() as conn:
            orchestrator = Orchestrator(
                cache=CacheService(conn),
                governor=Governor(conn, self._settings.providers),
                resolvers=self._resolvers,
                extractor_version=self._extractor_version,
                model_id=self._settings.models.extraction,
            )
            return await orchestrator.verify(
                intake,
                case_id=case_id,
                claims=claims,
                advisories=advisories,
                source_risk=source_risk,
            )


class RequestScopedClaimPipeline:
    """Extraction, with the governor and the extraction cache bound per request.

    The same connection-scoping problem the orchestrator has, for the same reason:
    `LLMExtractor` calls `governor.acquire` before every model call, and the governor
    writes the day's spend to the database. A process-lifetime governor would hold one
    connection open for the life of the container.

    Wiring the governor is not optional here. It is the only thing standing between a
    burst of requests and the daily quota, and the free tier is the ceiling.
    """

    def __init__(self, *, database: Database, settings: Settings, endpoint: str, api_key: str):
        self._database = database
        self._settings = settings
        self._endpoint = endpoint
        self._api_key = api_key
        self._fetcher = SecureFetcher(timeout_seconds=MODEL_TIMEOUT_SECONDS)

    async def extract(
        self,
        text: str,
        *,
        content_hash: str,
        input_kind: str = "text",
        language: str | None = None,
    ) -> ExtractedClaims:
        async with self._database.connection() as conn:
            pipeline = ClaimPipeline(
                LLMExtractor(
                    fetcher=self._fetcher,
                    governor=Governor(conn, self._settings.providers),
                    endpoint=self._endpoint,
                    api_key=self._api_key,
                    model_id=self._settings.models.extraction,
                ),
                cache=CacheService(conn),
            )
            return await pipeline.extract(
                text, content_hash=content_hash, input_kind=input_kind, language=language
            )


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
    resolvers: list[SourceResolver] = [
        CorpusResolver(database=database, embedder=embedder, fetcher=source_fetcher),
        FactCheckResolver(records=records, api_available=False),
    ]

    state: dict[str, Any] = {
        "database": database,
        "embedder": embedder,
        "orchestrator": RequestScopedOrchestrator(
            database=database,
            resolvers=resolvers,
            settings=settings,
            extractor_version=_extractor_version(),
        ),
    }

    if settings.llm.enabled and settings.llm.api_key:
        state["claim_pipeline"] = RequestScopedClaimPipeline(
            database=database,
            settings=settings,
            endpoint=settings.llm.endpoint,
            api_key=settings.llm.api_key.get_secret_value(),
        )

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


def _extractor_version() -> str:
    from app.extraction.llm import EXTRACTOR_VERSION

    return EXTRACTOR_VERSION
