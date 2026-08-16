"""M12 — limits are enforced, observable, and configurable without redeploy."""

from __future__ import annotations

import pytest

from app.security.ratelimit import (
    LimitPolicy,
    RateLimit,
    SlidingWindowLimiter,
    caller_key,
)

pytestmark = pytest.mark.unit


class FakeClock:
    """Time under test control, so no test sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestEnforcement:
    def test_requests_within_the_allowance_are_permitted(self) -> None:
        limiter = SlidingWindowLimiter(clock=FakeClock())
        limit = RateLimit(requests=3, window_seconds=60)

        outcomes = [limiter.check("caller", limit).allowed for _ in range(3)]

        assert outcomes == [True, True, True]

    def test_the_request_past_the_allowance_is_refused(self) -> None:
        limiter = SlidingWindowLimiter(clock=FakeClock())
        limit = RateLimit(requests=2, window_seconds=60)

        for _ in range(2):
            limiter.check("caller", limit)

        assert not limiter.check("caller", limit).allowed

    def test_callers_are_limited_independently(self) -> None:
        limiter = SlidingWindowLimiter(clock=FakeClock())
        limit = RateLimit(requests=1, window_seconds=60)

        limiter.check("caller-a", limit)

        assert limiter.check("caller-b", limit).allowed

    def test_a_zero_allowance_permits_nothing(self) -> None:
        limiter = SlidingWindowLimiter(clock=FakeClock())

        assert not limiter.check("caller", RateLimit(requests=0, window_seconds=60)).allowed


class TestSlidingWindow:
    def test_capacity_returns_gradually_rather_than_all_at_once(self) -> None:
        """A fixed window lets a caller take double the limit across a boundary.

        That burst is exactly what trips a per-minute provider ceiling during
        judging, which is why the window slides.
        """
        clock = FakeClock()
        limiter = SlidingWindowLimiter(clock=clock)
        limit = RateLimit(requests=2, window_seconds=60)

        limiter.check("caller", limit)
        clock.advance(30)
        limiter.check("caller", limit)

        assert not limiter.check("caller", limit).allowed

        # The first hit ages out; one slot returns, not both.
        clock.advance(31)
        assert limiter.check("caller", limit).allowed
        assert not limiter.check("caller", limit).allowed

    def test_the_window_fully_clears_over_time(self) -> None:
        clock = FakeClock()
        limiter = SlidingWindowLimiter(clock=clock)
        limit = RateLimit(requests=2, window_seconds=60)

        limiter.check("caller", limit)
        limiter.check("caller", limit)
        clock.advance(61)

        assert limiter.check("caller", limit).allowed


class TestObservability:
    def test_an_allowed_request_reports_its_remaining_allowance(self) -> None:
        limiter = SlidingWindowLimiter(clock=FakeClock())
        limit = RateLimit(requests=5, window_seconds=60)

        decision = limiter.check("caller", limit)

        assert decision.headers()["X-RateLimit-Limit"] == "5"
        assert decision.headers()["X-RateLimit-Remaining"] == "4"

    def test_a_refused_request_tells_the_caller_when_to_retry(self) -> None:
        clock = FakeClock()
        limiter = SlidingWindowLimiter(clock=clock)
        limit = RateLimit(requests=1, window_seconds=60)

        limiter.check("caller", limit)
        clock.advance(10)
        decision = limiter.check("caller", limit)

        assert not decision.allowed
        assert decision.headers()["Retry-After"] == "50"

    def test_retry_after_is_never_zero(self) -> None:
        """A client told to wait zero seconds retries immediately and hammers."""
        limiter = SlidingWindowLimiter(clock=FakeClock())
        limit = RateLimit(requests=0, window_seconds=0.1)

        assert limiter.check("caller", limit).retry_after_seconds >= 1


class TestPolicy:
    def test_uploads_carry_a_stricter_allowance_than_text(self) -> None:
        """An upload costs decode, keyframes and possibly a metered call; a text
        request costs a cache probe. Treating them alike lets one caller drain the
        day's budget through the expensive door."""
        policy = LimitPolicy()

        assert policy.for_path("/v1/verify/file").requests < policy.for_path("/v1/verify").requests

    def test_unknown_paths_fall_back_to_the_default(self) -> None:
        policy = LimitPolicy()

        assert policy.for_path("/healthz") == policy.default

    def test_limits_are_data_not_code(self) -> None:
        """Configurable without redeploy — the M12 gate."""
        policy = LimitPolicy(verify=RateLimit(requests=1, window_seconds=1))

        assert policy.for_path("/v1/verify").requests == 1

    def test_a_negative_allowance_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            RateLimit(requests=-1, window_seconds=60)


class TestCallerIdentity:
    def test_an_api_key_identifies_the_caller_when_present(self) -> None:
        assert caller_key(api_key="k1", device_id="d1", client_host="1.2.3.4") == "key:k1"

    def test_a_device_identifier_is_used_when_there_is_no_key(self) -> None:
        assert caller_key(api_key=None, device_id="d1", client_host="1.2.3.4") == "device:d1"

    def test_the_address_is_the_last_resort(self) -> None:
        """Falling back to the address alone puts a whole shared network behind one
        allowance, so it is only used when nothing better was supplied."""
        assert caller_key(api_key=None, device_id=None, client_host="1.2.3.4") == "addr:1.2.3.4"

    def test_an_unknown_caller_still_gets_a_key(self) -> None:
        assert caller_key(api_key=None, device_id=None, client_host=None) == "addr:unknown"
