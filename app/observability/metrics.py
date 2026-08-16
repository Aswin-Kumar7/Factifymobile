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
        self._cache_hits: dict[str, int] = {}
        self._cache_misses: dict[str, int] = {}
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

    # -- cache accounting -------------------------------------------------------
    #
    # Hit rate is a stated day-one investor metric and the mechanism behind the
    # margin story: it should rise with usage, so it has to be measurable from the
    # first request rather than instrumented later.

    def record_cache_hit(self, surface: str) -> None:
        with self._lock:
            self._cache_hits[surface] = self._cache_hits.get(surface, 0) + 1

    def record_cache_miss(self, surface: str) -> None:
        with self._lock:
            self._cache_misses[surface] = self._cache_misses.get(surface, 0) + 1

    def cache_snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            surfaces = set(self._cache_hits) | set(self._cache_misses)
            report: dict[str, dict[str, float | int]] = {}
            for surface in sorted(surfaces):
                hits = self._cache_hits.get(surface, 0)
                misses = self._cache_misses.get(surface, 0)
                total = hits + misses
                report[surface] = {
                    "hits": hits,
                    "misses": misses,
                    "hit_rate": round(hits / total, 4) if total else 0.0,
                }
            return report

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()
            self._cache_hits.clear()
            self._cache_misses.clear()


metrics = ProviderMetrics()
