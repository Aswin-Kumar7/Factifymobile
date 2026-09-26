"""The call governor (M14).

Since 2026-09-26 it no longer refuses on volume. Daily caps are spend alarms and the
per-minute ceiling paces calls instead of dropping them; limits on what a person may
check live in the per-user credit book, decided on the server. What still refuses is
an explicit emergency stop (`daily_hard_cap`), a disabled provider, and a budget store
it cannot reach. The paragraphs below describe the refusing design this replaced.

No external provider can be called more times per day than its budget allows, and
running out is an honest, first-class state rather than an error.

Three things this module is deliberately built around.

**Caps sit below the provider's own limit.** We degrade on our terms, with a recorded
reason and a response that says what was not checked, rather than discovering the
ceiling as a stream of provider errors in front of judges.

**The per-minute ceiling matters more than the daily one.** A day's budget is spent
gradually; three items shared in quick succession during a demo hit a rate limit in
seconds. Volume and burst are guarded separately because they fail at different times
for different reasons.

**Exhaustion continues the pipeline.** A skipped provider is not a failed request. The
case proceeds with whatever evidence it has, which usually means abstaining — and
abstention with a stated reason is a correct answer, not a degraded one.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum

from app.config import ProviderSettings
from app.db.repositories import BudgetRepository, Conn
from app.observability.logging import event
from app.observability.metrics import metrics
from app.security.ratelimit import RateLimit, SlidingWindowLimiter

logger = logging.getLogger("factify.governor")

# Longest a call waits for room under a provider's per-minute ceiling before it is
# given up on. Inside the request's own deadline, which cancels a wait that outlasts it.
_PACE_MAX_WAIT_SECONDS = 20.0


async def pace(
    provider: str,
    settings: ProviderSettings | None,
    burst: SlidingWindowLimiter,
    *,
    max_wait: float = _PACE_MAX_WAIT_SECONDS,
) -> bool:
    """Wait for room under a provider's per-minute ceiling. False if none came in time.

    Paced, not refused. The ceiling mirrors a provider's own rate limit, which clears
    in seconds; refusing turned a burst of claims into claims marked "rate limited"
    that a short wait would have checked. Needs no database, so a caller holding a
    pooled connection can do this first and not hold the connection while it waits.
    """
    if settings is None or not settings.per_minute_cap:
        return True
    limit = RateLimit(requests=settings.per_minute_cap, window_seconds=60)
    waited = 0.0
    while True:
        decision = burst.check(f"provider:{provider}", limit)
        if decision.allowed:
            return True
        remaining = max_wait - waited
        if remaining <= 0:
            return False
        pause = min(max(decision.reset_after_seconds, 0.05), remaining)
        await asyncio.sleep(pause)
        waited += pause


class SkipReason(StrEnum):
    """Why a provider was not called. Quoted verbatim in the response.

    A small closed set on purpose: these strings reach the user in "what we could not
    check", and an open-ended reason field would produce a different sentence every
    time for the same underlying situation.
    """

    CAPACITY_LIMITED = "capacity limited"
    RATE_LIMITED = "rate limited"
    DISABLED = "disabled"
    GOVERNOR_UNAVAILABLE = "governor unavailable"
    # The provider was called and every call failed: an outage, a revoked key, an
    # exhausted plan. Not "no results", which is an answer; this is the absence of one.
    PROVIDER_ERROR = "provider error"


class ProviderUnavailable(Exception):
    """The provider will not be called. Carries the reason for the ledger.

    Named for the outcome rather than one cause: exhaustion, a burst ceiling, an
    operator disabling the provider and the budget store being unreachable all end
    here, and each carries its own `reason`.
    """

    def __init__(self, provider: str, reason: SkipReason) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider}: {reason.value}")


@dataclass(frozen=True, slots=True)
class Skip:
    """A recorded decision not to call a provider."""

    provider: str
    reason: SkipReason

    @property
    def note(self) -> str:
        """The sentence the response uses when saying what was not checked."""
        return f"{self.provider}: {self.reason.value}"


@dataclass(frozen=True, slots=True)
class Grant:
    """Permission to make exactly one call."""

    provider: str
    granted_at: float


class Governor:
    """Gate in front of every metered provider.

    Holds the per-minute limiter in memory and the daily counter in the database:
    burst protection needs to be fast and local, while the daily budget must survive
    a restart, since a container recycling at noon must not reset the day's spend.
    """

    def __init__(
        self,
        conn: Conn,
        providers: dict[str, ProviderSettings],
        *,
        burst: SlidingWindowLimiter | None = None,
        pace_max_wait: float = _PACE_MAX_WAIT_SECONDS,
    ) -> None:
        self._budget = BudgetRepository(conn)
        self._pace_max_wait = pace_max_wait
        self._providers = providers
        # Injectable because the limiter only limits if it is shared. A Governor
        # constructed per request gets a fresh window per request, which counts each
        # burst against itself and nothing against the process — the ceiling the
        # limiter exists to impose. `PoolGovernor` passes one process-wide window in.
        self._burst = burst if burst is not None else SlidingWindowLimiter()
        self._skips: list[Skip] = []

    @property
    def skips(self) -> tuple[Skip, ...]:
        """Every provider skipped during this request, with its reason."""
        return tuple(self._skips)

    def _record_skip(self, provider: str, reason: SkipReason) -> Skip:
        skip = Skip(provider=provider, reason=reason)
        self._skips.append(skip)
        metrics.record_skip(provider, reason.value)
        event(
            logger,
            "provider skipped",
            module="governor",
            outcome="skipped",
            provider=provider,
            failure_reason=reason.value,
            level=logging.INFO,
        )
        return skip

    async def try_acquire(self, provider: str, *, paced: bool = False) -> Grant | Skip:
        """Take one unit of budget, or explain why not.

        Returns a value rather than raising, because "we did not call this provider"
        is an ordinary branch of a successful request. `paced` says the caller has
        already waited for room under the per-minute ceiling (see `PoolGovernor`).
        """
        settings = self._providers.get(provider)

        if settings is None or not settings.enabled or settings.api_key is None:
            return self._record_skip(provider, SkipReason.DISABLED)

        if not paced and not await pace(
            provider, settings, self._burst, max_wait=self._pace_max_wait
        ):
            return self._record_skip(provider, SkipReason.RATE_LIMITED)

        try:
            used = await self._budget.consume(provider=provider, hard_cap=settings.daily_hard_cap)
        except Exception:
            # Fails closed. If we cannot account for a call, we do not make it — an
            # unaccounted call is exactly the one that overruns a free tier.
            logger.exception("governor could not reach the budget store")
            return self._record_skip(provider, SkipReason.GOVERNOR_UNAVAILABLE)

        # Only the emergency stop refuses.
        if used is None:
            return self._record_skip(provider, SkipReason.CAPACITY_LIMITED)

        # The alarm: once, as the day's spend crosses it. Calls continue.
        if settings.daily_cap and used == settings.daily_cap:
            event(
                logger,
                "provider spend alarm",
                module="governor",
                outcome="degraded",
                provider=provider,
                used=used,
                alarm=settings.daily_cap,
                level=logging.WARNING,
            )

        return Grant(provider=provider, granted_at=time.perf_counter())

    async def acquire(self, provider: str) -> Grant:
        """Take one unit or raise. For callers that cannot proceed without it."""
        outcome = await self.try_acquire(provider)
        if isinstance(outcome, Skip):
            raise ProviderUnavailable(provider, outcome.reason)
        return outcome

    @asynccontextmanager
    async def call(self, provider: str) -> AsyncIterator[Grant]:
        """Wrap one provider call, recording its outcome and latency.

        Every external call goes through this. There is no path that spends a unit
        without recording that it was spent, and none that records a success it did
        not observe.
        """
        grant = await self.acquire(provider)
        try:
            yield grant
        except Exception:
            metrics.record_failure(provider, (time.perf_counter() - grant.granted_at) * 1000)
            raise
        else:
            metrics.record_success(provider, (time.perf_counter() - grant.granted_at) * 1000)

    async def usage(self, provider: str) -> dict[str, int]:
        """Today's spend against today's cap, for the usage endpoint."""
        row = await self._budget.usage(provider=provider)
        settings = self._providers.get(provider)
        return {
            "used": 0 if row is None else int(row["used"]),
            "alarm": settings.daily_cap if settings else 0,
            "hard_cap": settings.daily_hard_cap if settings else 0,
        }

    def capacity_notes(self) -> tuple[str, ...]:
        """What the response says about checks that did not happen."""
        return tuple(skip.note for skip in self._skips)
