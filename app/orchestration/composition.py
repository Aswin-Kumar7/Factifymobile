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

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.accounts import CreditBook, SupabaseIdentity
from app.accounts.google import GoogleOAuth
from app.accounts.local_auth import Identities, LocalAuth
from app.config import Settings, supabase_url_for
from app.db.pool import Database
from app.domain.claim import Claim
from app.domain.enums import SourceRisk
from app.domain.evidence import Advisory
from app.embeddings.image import ImageEmbedder
from app.embeddings.text import TextEmbedder
from app.extraction.claims import ClaimPipeline
from app.extraction.llm import LLMExtractor
from app.extraction.local_ocr import LocalFirstOcr, LocalOcr
from app.extraction.model_wire import WireFormat
from app.extraction.ocr import OcrExtractor
from app.extraction.translate import FallbackTranslator, GoogleTranslator, ModelTranslator
from app.intake.normalizer import NormalisedIntake
from app.knowledge.factchecks import FactCheckKeeper, load_factcheck_records
from app.knowledge.memory import EvidenceMemory
from app.knowledge.schedule import IngestionSchedule
from app.media.detectors.local import build as build_local_detector
from app.media.discovery import ReverseImageDiscovery
from app.media.report import MediaInspector
from app.media.speech import build as build_speech_reader
from app.media.synthetic import SightengineDetector
from app.observability.logging import event
from app.orchestration.adapters import (
    PoolAccountStore,
    PoolCacheService,
    PoolGovernor,
    PoolLoginStore,
    PoolReviewQueue,
)
from app.orchestration.ledger import CaseReader, Ledger
from app.orchestration.media import MediaVerification
from app.orchestration.pipeline import Orchestrator, SkippedCheck, VerificationResult
from app.orchestration.receipt import ReceiptReader, ReceiptSigner
from app.security.fetcher import SecureFetcher
from app.sources.base import SourceResolver
from app.sources.corpus import CorpusCorroboration, CorpusResolver
from app.sources.credibility import SourceCredibility
from app.sources.factcheck import FactCheckResolver
from app.sources.official_presence import OfficialPresenceCheck
from app.sources.reasoning import PassageReasoner
from app.sources.stance import LocalStance
from app.sources.verification import SourceVerification
from app.sources.websearch import WebSearchResolver

logger = logging.getLogger("factify.composition")

# Two fetchers with different patience, because they wait on different things. A
# model call legitimately takes tens of seconds; a news page that has not answered in
# twenty is not going to. One shared timeout meant every dead source burned the
# model's budget — measured in the audit, where fetch timeouts outlasted verification.
SOURCE_TIMEOUT_SECONDS = 20.0

# A link the person submitted gets less patience than a source, because it has a
# second reader behind it and the person is waiting. The Hindu took 15 seconds to
# fail our fetch — a third of the request's budget — before the vendor read it in 1.5.
LINK_TIMEOUT_SECONDS = 8.0
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
        signer: ReceiptSigner | None = None,
        embedder: Any | None = None,
    ) -> None:
        self._embedder = embedder
        self._database = database
        self._orchestrator = orchestrator
        self._media = media
        self._signer = signer

    async def cached(self, intake: NormalisedIntake, *, case_id: UUID) -> VerificationResult | None:
        """The stored verdict for this input, probed before extraction or media work.

        `verify` below prepares media — hashing, embedding, OCR — before the inner
        orchestrator reaches its own cache probe, and the endpoint extracts claims
        before calling `verify` at all. Asking here first lets a repeat skip both.
        """
        return await self._orchestrator.cached(intake, case_id=case_id)

    async def verify(
        self,
        intake: NormalisedIntake,
        *,
        case_id: UUID,
        claims: list[Claim],
        advisories: list[Advisory] | None = None,
        source_risk: SourceRisk = SourceRisk.UNKNOWN,
        started_at: float | None = None,
        fresh: bool = False,
        own_pages: frozenset[str] = frozenset(),
        synthetic: Any | None = None,
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
            started_at=started_at,
            fresh=fresh,
            own_pages=own_pages,
            synthetic=synthetic,
        )

        # Written after the verdict exists and never allowed to change it. A cached
        # result is not rewritten: it was persisted when first computed, and writing
        # it again would record a second case for one verification. The connection is
        # checked out here, after every fetch and model call has already finished.
        if not result.from_cache:
            async with self._database.connection() as conn:
                written = await Ledger(conn, signer=self._signer, embedder=self._embedder).persist(
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
            # Nothing is routed to human review automatically any more.
            #
            # Every abstention used to be queued for a person, and 241 of 491 cases
            # ended there — a queue nobody was working, behind an answer that told the
            # user "queued for human review" and nothing else. An undecided claim is
            # now answered as UNCONFIRMED, which is a finding the user can act on, and
            # the review queue holds only what a user reports as wrong through
            # `/v1/cases/{id}/report`. People review disputed answers, not every
            # answer the rules declined to give.

        return result


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

    # Every fact-check held: the ClaimReviews kept from fact-checkers' own pages, and
    # the headlines their feeds brought in.
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
    cache = PoolCacheService(database, reads=settings.cache_reads)

    # The reasoner reads fetched passages and judges them against the claim. Only
    # built when a model is configured; without it the corpus resolver falls back to
    # word overlap, which cannot detect contradiction and reports as much.
    reasoner: PassageReasoner | None = None
    local_stance: LocalStance | None = None
    if settings.llm.enabled and settings.llm.api_key:
        if settings.local.stance:
            candidate = LocalStance(
                directory=settings.local.directory, threads=settings.local.threads
            )
            local_stance = candidate if candidate.available else None
        reasoner = PassageReasoner(
            fetcher=SecureFetcher(timeout_seconds=MODEL_TIMEOUT_SECONDS),
            governor=governor,
            endpoint=settings.llm.endpoint,
            api_key=settings.llm.api_key.get_secret_value(),
            model_id=settings.models.extraction,
            api_format=WireFormat(settings.llm.api_format),
            # Ranks a page's passages against the claim before any of them are read.
            # Already loaded at startup, so this costs nothing per request.
            embedder=embedder,
            # Our own relevance and support models read each page first and answer
            # the clear cases (app/sources/local_reading.py).
            stance=local_stance,
        )

    corpus = CorpusResolver(
        database=database,
        embedder=embedder,
        fetcher=source_fetcher,
        reasoner=reasoner,
    )
    # Each fact-check the API points at is kept, so the next check finds it here.
    keeper = FactCheckKeeper(database=database, fetcher=source_fetcher)
    factchecks = FactCheckResolver(
        records=records,
        governor=governor,
        # Live only when the provider is configured and credentialled. The API is
        # the strongest, cheapest evidence class — one adjudication settles a claim
        # that would otherwise need corroboration across several origins — so it is
        # on whenever the key is present, and falls back to the ingested records
        # (and a clean skip) when quota or credentials are not.
        api_available=settings.factcheck.usable,
        fetcher=source_fetcher,
        endpoint=settings.factcheck.endpoint,
        api_key=(
            settings.factcheck.api_key.get_secret_value() if settings.factcheck.api_key else ""
        ),
        # Semantic relevance, so a paraphrased fact-check ("Coronavirus is a result
        # of 5G") is recognised as adjudicating the claim it restates.
        embedder=embedder,
        # And a reader for the borderline band, so a check of a neighbouring claim
        # on the same subject cannot have its rating applied here.
        reasoner=reasoner,
        keeper=keeper,
    )
    keeper.on_kept = factchecks.add_records
    resolvers: list[SourceResolver] = [factchecks]
    if settings.corpus_retrieval:
        resolvers.insert(0, corpus)

    # The open-web path, when a search provider is configured. Reaches the web through
    # a search API to find pages no local source covers, and reads them with the same
    # reasoner — corroboration-grade evidence, gated by a verbatim quote like every
    # other resolver. Off unless FACTIFY_WEBSEARCH__* is set.
    web_search: WebSearchResolver | None = None
    if settings.websearch.usable and reasoner is not None:
        web_search = WebSearchResolver(
            fetcher=source_fetcher,
            reasoner=reasoner,
            provider=settings.websearch_provider,
            endpoint=settings.websearch.endpoint,
            api_key=settings.websearch.api_key.get_secret_value()
            if settings.websearch.api_key
            else "",
            # Only credible publishers are read and cited from the open web.
            credibility=SourceCredibility.load(),
            governor=governor,
            # A fact-checker's page found by search is kept too.
            keeper=keeper,
            # And the pages a claim was cited against before, under any wording of it.
            memory=EvidenceMemory(database, embedder=embedder, same_claim=reasoner.same_claim),
            # Which results are read: the most relevant, by our own model.
            relevance=local_stance,
        )
        resolvers.append(web_search)

    async def _reload_factchecks() -> None:
        factchecks.replace_records(await load_factcheck_records(database))

    # The news, collected on a schedule while the service runs (data/feeds.json), and
    # the fact-checks re-read after each batch that brought anything new.
    ingestion = IngestionSchedule(
        database=database,
        fetcher=SecureFetcher(timeout_seconds=25.0, max_bytes=8 * 1024 * 1024),
        embedder=embedder,
        interval_seconds=settings.ingestion_interval_seconds,
        after_tick=_reload_factchecks,
    )

    review_queue = PoolReviewQueue(database)

    # Receipts are issued only when a signing key is configured. Without one the
    # endpoint reports unavailable rather than handing out something nobody can check
    # — an unsigned receipt is a claim about a claim.
    signer: ReceiptSigner | None = None
    if settings.receipt_signing_key:
        signer = ReceiptSigner(key=settings.receipt_signing_key.get_secret_value())

    # A company's own list of locations, for a claim that it opened one somewhere.
    presence = (
        OfficialPresenceCheck(web=web_search, reasoner=reasoner)
        if web_search is not None and reasoner is not None
        else None
    )
    orchestrator = Orchestrator(
        cache=cache,
        governor=governor,
        resolvers=resolvers,
        extractor_version=_extractor_version(),
        model_id=settings.models.extraction,
        corroboration=CorpusCorroboration(database=database),
        presence=presence,
        # Every source checked against the claim before anything decides. Needs the
        # reader's model; without one, sources are only deduplicated.
        verification=(
            SourceVerification(checker=reasoner, ranker=SourceCredibility.load())
            if reasoner is not None
            else None
        ),
        # Claims in the ten newer Indian languages are translated into English to find
        # and read English sources (app/extraction/translate.py).
        # Google first; when it refuses (it rate-limits the free endpoint), the
        # configured model translates instead, one small metered call per claim.
        translator=(
            FallbackTranslator(
                GoogleTranslator(
                    fetcher=SecureFetcher(timeout_seconds=8.0),
                    api_key=(
                        settings.translation_key.get_secret_value()
                        if settings.translation == "google_cloud" and settings.translation_key
                        else None
                    ),
                ),
                (
                    ModelTranslator(
                        fetcher=SecureFetcher(timeout_seconds=MODEL_TIMEOUT_SECONDS),
                        governor=governor,
                        endpoint=settings.llm.endpoint,
                        api_key=settings.llm.api_key.get_secret_value(),
                        model_id=settings.models.extraction,
                        api_format=WireFormat(settings.llm.api_format),
                    )
                    if settings.llm.enabled and settings.llm.api_key
                    else None
                ),
            )
            if settings.translation != "off"
            else None
        ),
    )

    anon_key = settings.auth.anon_key.get_secret_value() if settings.auth.anon_key else None
    project = supabase_url_for(settings)
    # This server's own sign-in: an email and a password, or Google.
    local_auth = LocalAuth(
        PoolLoginStore(database),
        session_days=settings.auth.session_days,
        min_password_length=settings.auth.min_password_length,
    )
    google_secret = (
        settings.auth.google_client_secret.get_secret_value()
        if settings.auth.google_client_secret
        else None
    )
    google_oauth = (
        GoogleOAuth(
            client_id=settings.auth.google_client_id,
            client_secret=google_secret,
            redirect_uri=f"{settings.auth.public_url.rstrip('/')}/v1/auth/google/callback",
            fetcher=SecureFetcher(timeout_seconds=15.0),
        )
        if settings.auth.google_client_id and google_secret and settings.auth.public_url
        else None
    )
    from app.orgs.month_close import MonthlyBilling
    from app.orgs.payments import Razorpay
    from app.orgs.store import OrgStore

    org_store = OrgStore(database)
    billing = settings.billing
    # Last month's extra usage, billed in the background once Razorpay is set up.
    monthly_billing = (
        MonthlyBilling(
            store=org_store,
            razorpay=Razorpay(
                billing.razorpay_key_id,
                billing.razorpay_key_secret.get_secret_value(),
                billing.razorpay_webhook_secret.get_secret_value()
                if billing.razorpay_webhook_secret
                else None,
            ),
            interval_seconds=billing.extra_usage_billing_hours * 3600,
        )
        if billing.razorpay_key_id and billing.razorpay_key_secret
        else None
    )

    state: dict[str, Any] = {
        "database": database,
        "orgs": org_store,
        "monthly_billing": monthly_billing,
        "local_auth": local_auth,
        "google_oauth": google_oauth,
        # A request's session: this server's own first, then a Supabase session from
        # before, while that project is still configured.
        "identity": Identities(
            local_auth,
            SupabaseIdentity(url=project, anon_key=anon_key) if project and anon_key else None,
        ),
        "credits": CreditBook(
            PoolAccountStore(database),
            signup_credits=settings.auth.signup_credits,
            enforce=settings.auth.enforce_credits,
        ),
        "embedder": embedder,
        # Reused to read a submitted link: a URL carries no text of its own, so the
        # verify path fetches the page and runs it through the same web reader (M16)
        # that reads retrieved sources. Shared with the corpus resolver rather than a
        # second client, so one connection pool serves both.
        "url_reader": SecureFetcher(timeout_seconds=LINK_TIMEOUT_SECONDS),
        # The same resolver the pipeline uses, so a submitted link can fall through
        # to the vendor's extract when the publisher will not serve us — the second
        # rung of the ladder a retrieved source already climbs.
        "web_search_resolver": web_search,
        # And the fact-check index, for a shared fact-check that will not serve us its
        # page: its rating as the fact-checker published it there.
        "factcheck_resolver": factchecks,
        "case_reader": CaseReader(database, ranker=SourceCredibility.load()),
        "ingestion": ingestion,
        "factcheck_keeper": keeper,
        "review_queue": review_queue,
        "orchestrator": ServedOrchestrator(
            database=database,
            orchestrator=orchestrator,
            media=MediaVerification(database=database, embedder=image_embedder),
            signer=signer,
            embedder=embedder,
        ),
    }

    if signer is not None:
        state["receipt_reader"] = ReceiptReader(database=database, signer=signer)

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
                api_format=WireFormat(settings.llm.api_format),
            ),
            cache=cache,  # type: ignore[arg-type]
        )
        # Reads an uploaded picture: its text, and what it shows. The same model and
        # budget as extraction - one call per image, and a repeat is served from the
        # verdict cache before it is made.
        state["ocr"] = OcrExtractor(
            fetcher=SecureFetcher(timeout_seconds=MODEL_TIMEOUT_SECONDS),
            governor=governor,
            endpoint=settings.llm.endpoint,
            api_key=settings.llm.api_key.get_secret_value(),
            model_id=settings.models.extraction,
            api_format=WireFormat(settings.llm.api_format),
        )

    # Text in pictures is read on our own server first (app/extraction/local_ocr.py);
    # the hosted reader above is asked only when ours finds too little to go on.
    if settings.local.ocr:
        local_ocr = LocalOcr(directory=settings.local.directory, threads=settings.local.threads)
        if local_ocr.available:
            state["ocr"] = LocalFirstOcr(local=local_ocr, hosted=state.get("ocr"))

    # The picture checks (app/media/report.py): content credentials and the editing
    # signals always; reverse image search when Google Vision is configured, and the
    # AI-image detector when Sightengine is. A missing provider is reported as "not
    # checked" on the answer, never as a clean result.
    media_fetcher = SecureFetcher(timeout_seconds=15.0)
    local_detector = build_local_detector(settings)
    if local_detector is not None:
        # Loaded in the background: the service answers at once, and the models are
        # ready by the time a picture arrives.
        asyncio.get_running_loop().run_in_executor(None, local_detector.warm)
    # What is said in a video (app/media/speech.py): read on our own server, loaded
    # on the first video rather than held from the start - unless `warm_video`.
    state["speech_reader"] = build_speech_reader(settings)
    if settings.local.warm_video:
        loop = asyncio.get_running_loop()
        if local_detector is not None:
            loop.run_in_executor(None, local_detector.warm_video)
        if state["speech_reader"] is not None:
            loop.run_in_executor(None, state["speech_reader"].load)
    vision = settings.vision
    synthetic = settings.synthetic
    state["media_inspector"] = MediaInspector(
        discovery=(
            ReverseImageDiscovery(
                fetcher=media_fetcher,
                governor=governor,  # type: ignore[arg-type]
                endpoint=vision.endpoint,
                api_key=vision.api_key.get_secret_value(),
            )
            if vision.enabled and vision.api_key and vision.endpoint
            else None
        ),
        # Our own detectors first (app/media/detectors); the hosted one only when
        # they are not installed and it is configured.
        detector=local_detector
        or (
            SightengineDetector(
                fetcher=media_fetcher,
                governor=governor,  # type: ignore[arg-type]
                endpoint=synthetic.endpoint or "https://api.sightengine.com/1.0/check.json",
                account=synthetic.account,
                secret=synthetic.api_key.get_secret_value(),
            )
            if synthetic.enabled and synthetic.api_key and synthetic.account
            else None
        ),
        fetcher=media_fetcher,
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
        image_reading_configured="ocr" in state,
        reverse_image_search=vision.enabled and vision.api_key is not None,
        ai_image_detector=(
            "local:" + "+".join(local_detector.models)
            if local_detector is not None
            else synthetic.enabled and synthetic.api_key is not None
        ),
        local_ocr=isinstance(state.get("ocr"), LocalFirstOcr),
        local_stance=reasoner is not None and local_stance is not None,
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
