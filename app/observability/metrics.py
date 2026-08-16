"""Per-provider counters (M04).

Calls, successes, failures, skips and latency percentiles per provider. These feed
two things the plan asks for by name: the Day 13 provider-failure-rate report, and
the governor's view of what is actually happening to its budgets.

In-process and reset on restart. That is sufficient for a single-container demo and
for the audit run; it is deliberately not a metrics backend, because one more piece
of infrastructure is one more thing to be down during judging.
"""

from __future__ import annotations

from bisect import insort
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class ProviderStats:
    """Outcomes for one provider.

    Skips are counted separately from failures. A provider skipped because its
    budget was exhausted did not fail — conflating the two would make the honest
    degradation path look like an outage.
    """

    calls: int = 0
    successes: int = 0
    failures: int = 0
    skips: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    _latencies_ms: list[float] = field(default_factory=list, repr=False)

    @property
    def failure_rate(self) -> float:
        return self.failures / self.calls if self.calls else 0.0

    def percentile(self, fraction: float) -> float | None:
        """Latency at the given fraction, or None if nothing has been recorded."""
        if not self._latencies_ms:
            return None
        index = min(int(fraction * len(self._latencies_ms)), len(self._latencies_ms) - 1)
        return self._latencies_ms[index]

    @property
    def median_ms(self) -> float | None:
        return self.percentile(0.50)

    @property
    def p95_ms(self) -> float | None:
        return self.percentile(0.95)


class ProviderMetrics:
    """Thread-safe registry of provider outcomes."""

    def __init__(self) -> None:
        self._stats: dict[str, ProviderStats] = {}
        self._lock = Lock()

    def _stats_for(self, provider: str) -> ProviderStats:
        return self._stats.setdefault(provider, ProviderStats())

    def record_success(self, provider: str, latency_ms: float) -> None:
        with self._lock:
            stats = self._stats_for(provider)
            stats.calls += 1
            stats.successes += 1
            insort(stats._latencies_ms, latency_ms)

    def record_failure(self, provider: str, latency_ms: float | None = None) -> None:
        with self._lock:
            stats = self._stats_for(provider)
            stats.calls += 1
            stats.failures += 1
            if latency_ms is not None:
                insort(stats._latencies_ms, latency_ms)

    def record_skip(self, provider: str, reason: str) -> None:
        """A provider that was never called, and the reason it was not.

        Reasons are a small closed set in practice — capacity limited, disabled,
        timeout — and they are what the response quotes when it says what was not
        checked.
        """
        with self._lock:
            stats = self._stats_for(provider)
            stats.skips += 1
            stats.skip_reasons[reason] = stats.skip_reasons.get(reason, 0) + 1

    def snapshot(self) -> dict[str, dict[str, object]]:
        """A serialisable view for the ops endpoint and the audit report."""
        with self._lock:
            return {
                provider: {
                    "calls": stats.calls,
                    "successes": stats.successes,
                    "failures": stats.failures,
                    "skips": stats.skips,
                    "skip_reasons": dict(stats.skip_reasons),
                    "failure_rate": round(stats.failure_rate, 4),
                    "median_ms": stats.median_ms,
                    "p95_ms": stats.p95_ms,
                }
                for provider, stats in self._stats.items()
            }

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()


metrics = ProviderMetrics()
