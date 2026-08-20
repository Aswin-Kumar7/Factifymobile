"""Audit entry point (M46).

    python -m app.audit.run collect    # build the manifest from the live corpus
    python -m app.audit.run report     # run the whole manifest, regenerate the report

`report` runs every item through the real pipeline — real extraction, real
retrieval, real verdict engine. Nothing is stubbed, and an item whose source has
changed since collection is recorded as a failure rather than repaired.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from uuid import uuid4

from app.audit.collect import collect
from app.audit.harness import AuditHarness, ItemResult
from app.audit.manifest import Expectation, Manifest, ManifestItem, content_hash
from app.config import Settings
from app.db.pool import Database
from app.domain.enums import ClaimStatus
from app.extraction.claims import ClaimPipeline
from app.extraction.llm import LLMExtractor
from app.extraction.web import extract
from app.intake.normalizer import normalise_text
from app.orchestration.pipeline import Orchestrator
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.factcheck import FactCheckRecord, FactCheckResolver, parse_rating_from_title

REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "audit-report.md"


class _NullCache:
    """The audit measures the pipeline, not the cache.

    A cache hit would report the latency of a dictionary lookup and the verdict of
    an earlier run, which is not what this is measuring.
    """

    async def get_verdict(self, parts: object) -> None:
        return None


class _NoGovernor:
    """Caps are not applied during an audit.

    The daily cap is smaller than the manifest, so honouring it would make a full
    run impossible by construction. The per-minute limit still has to be respected —
    exceeding it earns 429s rather than conserving anything — but that is done by
    pacing the harness between items, where the wait does not land inside the
    measured latency.
    """

    async def acquire(self, provider: str) -> None:
        return None

    async def try_acquire(self, provider: str) -> None:
        return None


async def _build_verifier(settings: Settings, conn: object) -> object:
    """Wire the real pipeline, including the fact-check corpus from the database."""
    rows = await (
        await conn.execute(  # type: ignore[attr-defined]
            """
            SELECT ci.title, ci.canonical_url, ci.publisher, ci.published_at
              FROM corpus_item ci
              JOIN source s ON s.id = ci.source_id
             WHERE s.source_class = 'factchecker'
            """
        )
    ).fetchall()

    records = [
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

    # Two fetchers with different patience, because they wait on different things.
    #
    # A model call legitimately takes tens of seconds; a news page that has not
    # responded in twenty is not going to. Sharing one 90-second timeout meant
    # every dead source burned a minute and a half, and a 52-item audit spent
    # longer in fetch timeouts than in verification.
    sources = SecureFetcher(timeout_seconds=20.0, max_bytes=8 * 1024 * 1024)
    fetcher = SecureFetcher(timeout_seconds=90.0, max_bytes=8 * 1024 * 1024)
    pipeline = ClaimPipeline(
        LLMExtractor(
            fetcher=fetcher,
            governor=_NoGovernor(),  # type: ignore[arg-type]
            endpoint=settings.llm.endpoint,
            api_key=settings.llm.api_key.get_secret_value() if settings.llm.api_key else "",
            model_id=settings.models.extraction,
        )
    )
    orchestrator = Orchestrator(
        cache=_NullCache(),  # type: ignore[arg-type]
        governor=_NoGovernor(),
        resolvers=[FactCheckResolver(records=records, api_available=False)],
        extractor_version="audit",
        model_id=settings.models.extraction,
    )

    async def verify(item: ManifestItem) -> ItemResult:
        began = time.perf_counter()
        skipped: list[str] = []

        if not item.text and not item.url:
            return ItemResult(
                item=item,
                observed=Expectation.ABSTAIN.value,
                elapsed_ms=0,
                error="item carries neither text nor a URL",
            )

        # Fetch the article when there is one. Extracting from the headline alone
        # produced almost nothing: 60 characters give the model no room, and it
        # paraphrases, so anchor verification then discards the claim as "not found
        # in source" — correctly. The headline is a label for the item, not the
        # document under test.
        source = item.text or ""
        changed = False
        if item.url:
            fetched = await sources.fetch(item.url, provider="audit_source")
            if isinstance(fetched, FetchResult):
                article = extract(fetched.text, url=item.url)
                if len(article.body) > 400:
                    source = article.body
                    if item.content_hash:
                        # A source that changed since collection is recorded, never
                        # repaired. The item still runs; the report says it moved.
                        changed = content_hash(fetched.body) != item.content_hash
            else:
                skipped.append(f"source fetch: {fetched.reason}")

        if not source:
            return ItemResult(
                item=item,
                observed=Expectation.ABSTAIN.value,
                elapsed_ms=int((time.perf_counter() - began) * 1000),
                provider_failures=tuple(skipped),
                error="no readable text at the source",
            )

        intake = normalise_text(source)

        extracted = await pipeline.extract(
            source,
            content_hash=intake.primary.sha256,
            input_kind="text",
            language=item.language,
        )
        if extracted.reason:
            skipped.append(f"extraction: {extracted.reason}")

        result = await orchestrator.verify(intake, case_id=uuid4(), claims=list(extracted.claims))

        # The observed status is the strongest decisive claim, or ABSTAIN. That is
        # the answer a user acts on, so it is the answer being scored.
        observed = Expectation.ABSTAIN.value
        for outcome in result.claims:
            if outcome.decision.status is not ClaimStatus.UNVERIFIED:
                observed = outcome.decision.status.value
                break

        evidence = result.evidence
        return ItemResult(
            item=item,
            observed=observed,
            elapsed_ms=int((time.perf_counter() - began) * 1000),
            evidence_count=len(evidence),
            citation_urls=tuple(e.citation_url for e in evidence),
            provider_failures=tuple(skipped + [s.check for s in result.skipped]),
            source_changed=changed,
        )

    verify._fetcher = fetcher  # type: ignore[attr-defined]
    verify._sources = sources  # type: ignore[attr-defined]
    return verify


async def do_collect(settings: Settings) -> None:
    db = Database(str(settings.database_url), min_size=1, max_size=3)
    await db.open()
    async with db.connection() as conn:
        manifest = await collect(conn)
    await db.close()

    path = manifest.save()
    print(f"collected {len(manifest.items)} items -> {path}")
    for name, count in manifest.by_category().items():
        print(f"  {name:26} {count}")

    shortfall = manifest.shortfall()
    if shortfall:
        print(f"\nGENUINE-CONTENT FLOOR NOT MET: {shortfall}")
        sys.exit(1)
    print(f"\ngenuine-content floor met: {manifest.genuine_count} items")


async def do_report(settings: Settings) -> None:
    manifest = Manifest.load()
    print(f"running {len(manifest.items)} items ({manifest.genuine_count} genuine)")

    db = Database(str(settings.database_url), min_size=1, max_size=3)
    await db.open()
    async with db.connection() as conn:
        verify = await _build_verifier(settings, conn)
        harness = AuditHarness(
            verify=verify,
            corpus_version=manifest.corpus_version,
            pace_seconds=60.0 / max(1, settings.llm.per_minute_cap),
        )
        report = await harness.run(manifest)
    await verify._fetcher.aclose()  # type: ignore[attr-defined]
    await verify._sources.aclose()  # type: ignore[attr-defined]
    await db.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report.render(), encoding="utf-8")
    print(f"\nreport -> {REPORT_PATH}")

    cited, decisive = report.citation_coverage
    print(f"  decisive results     {decisive}")
    print(f"  citation coverage    {cited}/{decisive}")
    print(f"  uncited decisive     {len(report.uncited_decisive)}  (must be 0)")
    rate = report.false_positive_rate()
    shown = "not reportable" if rate is None else f"{rate[0]:.1%} (n={rate[1]})"
    print(f"  false-positive rate  {shown}")


def main() -> None:
    logging.disable(logging.INFO)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

    command = sys.argv[1] if len(sys.argv) > 1 else "report"
    settings = Settings()

    if command == "collect":
        asyncio.run(do_collect(settings))
    elif command == "report":
        asyncio.run(do_report(settings))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
