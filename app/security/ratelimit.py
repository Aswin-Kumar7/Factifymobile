"""Rate limiting (M12).

Protects the service and — more importantly — the free-tier quotas from a single
caller. The governor (M14) caps what we spend at a provider; this caps who gets to
make us spend it.

Uploads carry a separate, stricter limit. A text request costs a cache probe; a video
upload costs decode, keyframe extraction and possibly a metered reverse-image call,
so treating them the same would let one caller drain a day's budget through the
expensive door while looking well-behaved on the cheap one.

A sliding window rather than a fixed one: fixed windows let a caller send a full
allowance either side of a boundary and take double the limit in a moment, which is
exactly the burst that trips a per-minute provider ceiling during judging.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class RateLimit:
    """An allowance and the window it applies over."""

    requests: int
    window_seconds: float

    def __post_init__(self) -> None:
        if self.requests < 0:
            raise ValueError("requests must not be negative")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of one check, shaped for the response headers it becomes."""

    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: float

    @property
    def retry_after_seconds(self) -> int:
        """Whole seconds, rounded up — a client told to wait 0s will hammer."""
        return max(1, int(self.reset_after_seconds + 0.999))

    def headers(self) -> dict[str, str]:
        """Standard rate-limit headers, so a caller can back off deliberately."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_after_seconds)),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after_seconds)
        return headers


class SlidingWindowLimiter:
    """In-process sliding-window limiter.

    Per-process, which is honest about what it is: with several instances the
    effective limit multiplies. That is acceptable while the governor is the thing
    actually protecting the quota, and it is the reason this is not the only defence.
    A shared counter belongs in the database when there is more than one instance.
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._clock = clock or time.monotonic

    def check(self, key: str, limit: RateLimit) -> Decision:
        """Take one unit if the window allows it."""
        if limit.requests == 0:
            return Decision(
                allowed=False, limit=0, remaining=0, reset_after_seconds=limit.window_seconds
            )

        now = self._clock()
        cutoff = now - limit.window_seconds

        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit.requests:
                reset_after = hits[0] - cutoff
                return Decision(
                    allowed=False,
                    limit=limit.requests,
                    remaining=0,
                    reset_after_seconds=max(0.0, reset_after),
                )

            hits.append(now)
            return Decision(
                allowed=True,
                limit=limit.requests,
                remaining=limit.requests - len(hits),
                reset_after_seconds=limit.window_seconds,
            )

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


@dataclass(frozen=True, slots=True)
class LimitPolicy:
    """The limits in force, one per class of request."""

    verify: RateLimit = RateLimit(requests=30, window_seconds=60)
    upload: RateLimit = RateLimit(requests=6, window_seconds=60)
    default: RateLimit = RateLimit(requests=120, window_seconds=60)

    def for_path(self, path: str) -> RateLimit:
        if path.startswith("/v1/verify/file"):
            return self.upload
        if path.startswith("/v1/verify"):
            return self.verify
        return self.default


def caller_key(*, api_key: str | None, device_id: str | None, client_host: str | None) -> str:
    """Identify the caller, most specific first.

    An API key identifies a tenant, a device identifier a consumer install, and the
    address is the last resort. Falling back to the address alone would put an entire
    shared network behind one allowance, so it is only used when nothing better was
    supplied.
    """
    if api_key:
        return f"key:{api_key}"
    if device_id:
        return f"device:{device_id}"
    return f"addr:{client_host or 'unknown'}"
