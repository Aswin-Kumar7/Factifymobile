"""Pool-backed adapters — connection-scoped services made safe to hold forever.

`CacheService` and `Governor` take a live connection, which forced the composition
root to build them per request and to hold one pool connection across the *entire*
verification — including up to six source fetches at a 20 second timeout each and a
model call at up to 90. With `max_size=10`, ten concurrent verifications pinned the
whole pool, and the reasoner then needed an eleventh connection while all ten were
held: starvation that surfaced as the reasoner silently degrading to word overlap
under exactly the load where its answers matter most.

Per-request construction also voided two limiters without breaking any test:

  - `Orchestrator._semaphore` capped concurrent fetches *per request*, so the
    "never open forty sockets against six publishers" ceiling did not exist across
    requests — the only place it matters.
  - `Governor._burst` rate-limited *per request*, so the per-minute window each
    request saw was always empty.

These adapters hold the pool, not a connection. Each operation checks a connection
out for exactly as long as the database work takes — microseconds, not the lifetime
of an HTTP fetch — and the process-wide state (the burst window) lives here, where
there is exactly one of it.
"""

from __future__ import annotations

import logging
from typing import Any

from app.cache.keys import CacheKeyParts
from app.cache.service import CachedVerdict, CacheService
from app.config import ProviderSettings
from app.db.pool import Database
from app.governor.governor import Governor
from app.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger("factify.orchestration.adapters")


class PoolGovernor:
    """The governor, holding the pool and the one burst window that counts."""

    def __init__(self, database: Database, providers: dict[str, ProviderSettings]) -> None:
        self._database = database
        self._providers = providers
        self._burst = SlidingWindowLimiter()

    async def acquire(self, provider: str) -> Any:
        async with self._database.connection() as conn:
            return await Governor(conn, self._providers, burst=self._burst).acquire(provider)

    async def try_acquire(self, provider: str) -> Any:
        async with self._database.connection() as conn:
            return await Governor(conn, self._providers, burst=self._burst).try_acquire(provider)


class PoolCacheService:
    """The cache surfaces, one short-lived connection per operation."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_verdict(self, parts: CacheKeyParts) -> CachedVerdict | None:
        async with self._database.connection() as conn:
            return await CacheService(conn).get_verdict(parts)

    async def put_verdict(
        self,
        parts: CacheKeyParts,
        payload: dict[str, Any],
        *,
        case_id: object | None = None,
        is_negative: bool = False,
        developing: bool = False,
    ) -> None:
        async with self._database.connection() as conn:
            await CacheService(conn).put_verdict(
                parts,
                payload,
                case_id=case_id,
                is_negative=is_negative,
                developing=developing,
            )

    async def get_extraction(self, *, content_hash: str, extractor_version: str) -> Any:
        async with self._database.connection() as conn:
            return await CacheService(conn).get_extraction(
                content_hash=content_hash, extractor_version=extractor_version
            )

    async def put_extraction(self, *args: Any, **kwargs: Any) -> Any:
        async with self._database.connection() as conn:
            return await CacheService(conn).put_extraction(*args, **kwargs)


class PoolReviewQueue:
    """The review queue over short-lived connections.

    Same shape as the other adapters, and the reason the review endpoints stopped
    returning 503: `ReviewQueue` binds to one connection, so nothing process-lifetime
    could ever hold one, so nothing was ever composed, so `/v1/review` was
    unreachable in every deployment there has ever been.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    async def route(self, result: Any) -> Any:
        from app.db.repositories import ReviewRepository
        from app.orchestration.review import ReviewQueue

        async with self._database.connection() as conn:
            return await ReviewQueue(repository=ReviewRepository(conn)).route(result)

    async def pending(self, limit: int = 50) -> Any:
        from app.db.repositories import ReviewRepository
        from app.orchestration.review import ReviewQueue

        async with self._database.connection() as conn:
            return await ReviewQueue(repository=ReviewRepository(conn)).pending(limit)

    async def record(self, **kwargs: Any) -> None:
        from app.db.repositories import ReviewRepository
        from app.orchestration.review import ReviewQueue

        async with self._database.connection() as conn:
            await ReviewQueue(repository=ReviewRepository(conn)).record(**kwargs)

    async def report(self, case_id: Any) -> Any:
        """A user-initiated report: this verdict deserves human eyes.

        Distinct from `route`, which the pipeline calls for its own abstentions.
        The reason string names the source so a reviewer can tell "the system was
        unsure" from "a person disagreed" — those want different attention.
        """
        from app.db.repositories import ReviewRepository
        from app.orchestration.review import ReviewReason

        async with self._database.connection() as conn:
            return await ReviewRepository(conn).enqueue(
                case_id=case_id, reason=ReviewReason.USER_REPORTED.value, machine_status=None
            )
