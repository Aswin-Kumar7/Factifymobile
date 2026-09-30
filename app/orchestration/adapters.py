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
from datetime import datetime
from typing import Any

from app.cache.keys import CacheKeyParts
from app.cache.service import CachedVerdict, CacheService
from app.config import ProviderSettings
from app.db.pool import Database
from app.db.repositories import AccountRepository, LoginRepository
from app.governor.governor import Governor, ProviderUnavailable, Skip, SkipReason, pace
from app.security.ratelimit import SlidingWindowLimiter

logger = logging.getLogger("factify.orchestration.adapters")


class PoolGovernor:
    """The governor, holding the pool and the one burst window that counts."""

    def __init__(self, database: Database, providers: dict[str, ProviderSettings]) -> None:
        self._database = database
        self._providers = providers
        self._burst = SlidingWindowLimiter()

    async def acquire(self, provider: str) -> Any:
        outcome = await self.try_acquire(provider)
        if isinstance(outcome, Skip):
            raise ProviderUnavailable(provider, outcome.reason)
        return outcome

    async def try_acquire(self, provider: str) -> Any:
        # Paced before a connection is taken. A call waiting for room under a
        # provider's per-minute ceiling can wait for seconds, and holding one of the
        # pool's connections all that time would starve every other request.
        settings = self._providers.get(provider)
        if not await pace(provider, settings, self._burst):
            async with self._database.connection() as conn:
                governor = Governor(conn, self._providers, burst=self._burst)
                return governor._record_skip(provider, SkipReason.RATE_LIMITED)
        async with self._database.connection() as conn:
            return await Governor(conn, self._providers, burst=self._burst).try_acquire(
                provider, paced=True
            )


class PoolCacheService:
    """The cache surfaces, one short-lived connection per operation."""

    def __init__(self, database: Database, *, reads: bool = True) -> None:
        self._database = database
        # Off: nothing stored is served, so every check runs afresh (`cache_reads`).
        self._reads = reads

    async def get_verdict(self, parts: CacheKeyParts) -> CachedVerdict | None:
        if not self._reads:
            return None
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
        if not self._reads:
            return None
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


class PoolAccountStore:
    """Accounts and the credit ledger, one short-lived connection per operation."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def upsert(self, user: Any) -> bool:
        async with self._database.connection() as conn:
            return await AccountRepository(conn).upsert(
                user_id=user.id, email=user.email, name=user.name, avatar_url=user.avatar_url
            )

    async def record(self, user_id: str, delta: int, reason: str, request_key: str) -> bool:
        async with self._database.connection() as conn:
            return await AccountRepository(conn).record(
                user_id=user_id, delta=delta, reason=reason, request_key=request_key
            )

    async def totals(self, user_id: str) -> tuple[int, int, int]:
        async with self._database.connection() as conn:
            return await AccountRepository(conn).totals(user_id=user_id)

    async def profile(self, user_id: str) -> dict[str, object] | None:
        async with self._database.connection() as conn:
            return await AccountRepository(conn).profile(user_id=user_id)

    async def set_name(self, user_id: str, name: str) -> None:
        async with self._database.connection() as conn:
            await AccountRepository(conn).set_name(user_id=user_id, name=name)

    async def set_survey(self, user_id: str, state: str, answers: dict[str, object] | None) -> None:
        async with self._database.connection() as conn:
            await AccountRepository(conn).set_survey(user_id=user_id, state=state, answers=answers)


class PoolLoginStore:
    """Sign-in (`LocalAuth`'s store), one short-lived connection per operation."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def login_by_email(self, email: str) -> dict[str, Any] | None:
        async with self._database.connection() as conn:
            return await LoginRepository(conn).by_email(email)

    async def login_by_google(self, sub: str) -> dict[str, Any] | None:
        async with self._database.connection() as conn:
            return await LoginRepository(conn).by_google(sub)

    async def create_user(self, **fields: Any) -> bool:
        async with self._database.connection() as conn:
            return await LoginRepository(conn).create(**fields)

    async def link_google(self, *, user_id: str, sub: str) -> None:
        async with self._database.connection() as conn:
            await LoginRepository(conn).link_google(user_id=user_id, sub=sub)

    async def create_session(
        self, *, token_hash: str, user_id: str, method: str, expires_at: datetime
    ) -> None:
        async with self._database.connection() as conn:
            await LoginRepository(conn).open_session(
                token_hash=token_hash, user_id=user_id, method=method, expires_at=expires_at
            )

    async def session_user(self, token_hash: str, now: datetime) -> dict[str, Any] | None:
        async with self._database.connection() as conn:
            return await LoginRepository(conn).session_person(token_hash, now)

    async def delete_session(self, token_hash: str) -> None:
        async with self._database.connection() as conn:
            await LoginRepository(conn).close_session(token_hash)
