"""The call governor (M14).

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
    ) -> None:
        self._budget = BudgetRepository(conn)
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

    async def try_acquire(self, provider: str) -> Grant | Skip:
        """Take one unit of budget, or explain why not.

        Returns a value rather than raising, because "we did not call this provider"
        is an ordinary branch of a successful request.
        """
        settings = self._providers.get(provider)

        if settings is None or not settings.enabled or settings.api_key is None:
            return self._record_skip(provider, SkipReason.DISABLED)

        # A cap of zero is configured-but-budgeted-to-nothing, which is exhaustion
        # from the first call rather than an absent provider. The distinction reaches
        # the user: "capacity limited" invites trying later, "disabled" does not.
        if settings.daily_cap == 0:
            return self._record_skip(provider, SkipReason.CAPACITY_LIMITED)

        if settings.per_minute_cap:
            burst = self._burst.check(
                f"provider:{provider}",
                RateLimit(requests=settings.per_minute_cap, window_seconds=60),
            )
            if not burst.allowed:
                return self._record_skip(provider, SkipReason.RATE_LIMITED)

        try:
            taken = await self._budget.try_consume(provider=provider, cap=settings.daily_cap)
        except Exception:
            # Fails closed. If we cannot account for a call, we do not make it — an
            # unaccounted call is exactly the one that overruns a free tier.
            logger.exception("governor could not reach the budget store")
            return self._record_skip(provider, SkipReason.GOVERNOR_UNAVAILABLE)

        if not taken:
            return self._record_skip(provider, SkipReason.CAPACITY_LIMITED)

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
        if row is None:
            settings = self._providers.get(provider)
            return {"used": 0, "cap": settings.daily_cap if settings else 0}
        return {"used": int(row["used"]), "cap": int(row["cap"])}

    def capacity_notes(self) -> tuple[str, ...]:
        """What the response says about checks that did not happen."""
        return tuple(skip.note for skip in self._skips)
