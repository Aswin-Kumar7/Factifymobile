"""The governor protects the account, not the product (2026-09-26).

Daily caps used to refuse, which made them a limit on everyone's checks: about 27 a
day for the whole service. Now a daily cap is a spend alarm, only an explicit
emergency stop refuses, and the per-minute ceiling waits for room instead of dropping
the call. What a person may check is the per-user credit book's decision.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.config import ProviderSettings
from app.governor import governor as governor_module
from app.governor.governor import Governor, Grant, Skip, SkipReason
from app.security.ratelimit import SlidingWindowLimiter


class _Budget:
    """The day's counter, in memory."""

    def __init__(self) -> None:
        self.used = 0

    async def consume(self, *, provider: str, hard_cap: int = 0, day: Any = None) -> int | None:
        if hard_cap and self.used >= hard_cap:
            return None
        self.used += 1
        return self.used


def _governor(settings: ProviderSettings, **kwargs: Any) -> Governor:
    governor = Governor(None, {"llm": settings}, **kwargs)  # type: ignore[arg-type]
    governor._budget = _Budget()  # type: ignore[assignment]
    return governor


class TestTheDailyCapIsAnAlarm:
    @pytest.mark.anyio
    async def test_crossing_it_never_refuses_a_call(self, caplog: Any) -> None:
        governor = _governor(ProviderSettings(enabled=True, api_key="k", daily_cap=2))

        with caplog.at_level(logging.WARNING, logger="factify.governor"):
            outcomes = [await governor.try_acquire("llm") for _ in range(5)]

        assert all(isinstance(outcome, Grant) for outcome in outcomes)
        alarms = [r for r in caplog.records if r.getMessage() == "provider spend alarm"]
        assert len(alarms) == 1  # once, as the day's spend crosses it

    @pytest.mark.anyio
    async def test_only_the_emergency_stop_refuses(self) -> None:
        governor = _governor(ProviderSettings(enabled=True, api_key="k", daily_hard_cap=2))

        outcomes = [await governor.try_acquire("llm") for _ in range(3)]

        assert isinstance(outcomes[0], Grant) and isinstance(outcomes[1], Grant)
        assert isinstance(outcomes[2], Skip)
        assert outcomes[2].reason is SkipReason.CAPACITY_LIMITED


class TestTheMinuteCeilingWaitsInsteadOfRefusing:
    @staticmethod
    def _clock(monkeypatch: Any) -> SlidingWindowLimiter:
        """A limiter on a clock that moves only when the governor sleeps."""
        now = [1000.0]

        async def _sleep(seconds: float) -> None:
            now[0] += seconds

        monkeypatch.setattr(governor_module.asyncio, "sleep", _sleep)
        return SlidingWindowLimiter(clock=lambda: now[0])

    @pytest.mark.anyio
    async def test_a_burst_waits_for_room_and_is_granted(self, monkeypatch: Any) -> None:
        limiter = self._clock(monkeypatch)
        governor = _governor(
            ProviderSettings(enabled=True, api_key="k", per_minute_cap=2),
            burst=limiter,
            pace_max_wait=90,
        )

        outcomes = [await governor.try_acquire("llm") for _ in range(3)]

        # The third call used to come back RATE_LIMITED; it now waits for the window.
        assert all(isinstance(outcome, Grant) for outcome in outcomes)

    @pytest.mark.anyio
    async def test_a_wait_longer_than_allowed_gives_up(self, monkeypatch: Any) -> None:
        limiter = self._clock(monkeypatch)
        governor = _governor(
            ProviderSettings(enabled=True, api_key="k", per_minute_cap=2),
            burst=limiter,
            pace_max_wait=5,
        )

        outcomes = [await governor.try_acquire("llm") for _ in range(3)]

        assert isinstance(outcomes[2], Skip)
        assert outcomes[2].reason is SkipReason.RATE_LIMITED
