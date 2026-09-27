"""Collecting the news, on a schedule, while the service runs.

The ingestion worker (`ingest.py`) was built and never run: nothing created it, and
`/internal/ingest-tick` answered "accepted" without calling it, so the corpus stopped
at 2026-08-18 and local search was switched off because its data was stale. This runs
it: a tick every few minutes in the background, each reading a small batch of due
feeds (`data/feeds.json`, 50 of them: newsrooms, fact-checkers, PIB and the RBI), and
the same tick behind `/internal/ingest-tick` for a deployment that schedules from
outside.

After a tick, the fact-checks held are read again, so a fact-check published this
morning answers a check this afternoon without the fact-check API being asked.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.db.repositories import CorpusRepository, FeedRepository, SourceRepository
from app.knowledge.clustering import OriginClusterer
from app.knowledge.ingest import IngestionWorker, TickResult
from app.knowledge.registry import FeedDefinition, FeedRegistry, load_registry
from app.observability.logging import event

logger = logging.getLogger("factify.knowledge.schedule")

# Feeds read per tick. Small, because a tick holds one database connection while it
# fetches, and the requests people are waiting on share the pool.
_BATCH = 3


class IngestionSchedule:
    """Runs ingestion ticks: now and then in the background, or on demand."""

    def __init__(
        self,
        *,
        database: Any,
        fetcher: Any,
        embedder: Any | None = None,
        interval_seconds: float = 0,
        after_tick: Callable[[], Awaitable[None]] | None = None,
        definitions: tuple[FeedDefinition, ...] | None = None,
        batch: int = _BATCH,
    ) -> None:
        self._database = database
        self._fetcher = fetcher
        self._embedder = embedder
        self._interval = interval_seconds
        self._after_tick = after_tick
        self._definitions = definitions if definitions is not None else load_registry()
        self._by_url = {d.url: d for d in self._definitions}
        self._batch = batch
        self._clusterer = OriginClusterer()
        self._synced = False
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    async def tick(self) -> TickResult:
        """One batch of due feeds. Two ticks never overlap."""
        async with self._lock:
            async with self._database.connection() as conn:
                registry = FeedRegistry(FeedRepository(conn))
                if not self._synced:
                    await registry.sync(self._definitions)
                    self._synced = True
                worker = IngestionWorker(
                    fetcher=self._fetcher,
                    registry=registry,
                    corpus=CorpusRepository(conn),
                    sources=SourceRepository(conn),
                    clusterer=self._clusterer,
                    embedder=self._embedder,
                )
                result = await worker.tick(self._by_url, limit=self._batch)
            if self._after_tick is not None and (result.items_new or result.factchecks_kept):
                await self._after_tick()
            return result

    def start(self) -> None:
        """Tick in the background, every `interval_seconds`. Off at 0."""
        if self._interval <= 0 or self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        # A little after startup, so the first requests are not competing with it.
        await asyncio.sleep(min(60.0, self._interval))
        while True:
            try:
                result = await self.tick()
                event(
                    logger,
                    "scheduled ingestion tick",
                    module="knowledge.schedule",
                    outcome="ok" if result.succeeded else "degraded",
                    feeds=result.feeds_attempted,
                    items_new=result.items_new,
                    factchecks_kept=result.factchecks_kept,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # A tick that fails is logged and the next one tried: ingestion is
                # a background job, and the service it feeds must not notice.
                logger.exception("scheduled ingestion tick failed")
            await asyncio.sleep(self._interval)
