"""Audit harness and report (M46).

Runs the whole manifest through the real pipeline and regenerates the report as a
document. Every run is stamped and records the corpus it ran against, so two runs
are comparable and a judge can be shown exactly what was retrieved and when.

The reporting rules are as load-bearing as the measurement:

  - **The false-positive rate is withheld below the genuine-content floor**, with the
    sample size and the reason printed in its place. A rate computed from eight items
    is a number that looks like evidence and is not.
  - **Every rate carries its denominator.** "96% precision" over 25 items and over
    2,500 are different claims, and only one of them is reportable.
  - **Abstention is listed under observations, not results.** It has no target,
    because a falling abstention rate means the system stopped refusing.
  - **A source that changed since collection is a failure, not a silent pass.** The
    item abstains and the run says so.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.audit.manifest import MIN_GENUINE_ITEMS, Expectation, Manifest, ManifestItem
from app.domain.enums import ClaimStatus


@dataclass(slots=True)
class ItemResult:
    """What one manifest item actually produced."""

    item: ManifestItem
    observed: str
    elapsed_ms: int
    evidence_count: int = 0
    citation_urls: tuple[str, ...] = ()
    provider_failures: tuple[str, ...] = ()
    source_changed: bool = False
    error: str | None = None

    @property
    def abstained(self) -> bool:
        return self.observed == Expectation.ABSTAIN.value

    @property
    def matched(self) -> bool:
        """Whether the observed outcome is what a correct system should produce."""
        return self.observed == self.item.expectation.value

    @property
    def is_false_positive(self) -> bool:
        """A decisive claim about genuine content.

        The failure that matters most: telling someone a true article is false. An
        abstention on genuine content is a miss, not a false positive, and the two
        are counted separately.
        """
        return self.item.is_genuine and self.observed in {
            ClaimStatus.CONTRADICTED.value,
            ClaimStatus.MISLEADING_CONTEXT.value,
        }

    @property
    def is_uncited_decisive(self) -> bool:
        """A decisive status with no citation. Must always be zero."""
        return (
            self.observed
            in {
                ClaimStatus.SUPPORTED.value,
                ClaimStatus.CONTRADICTED.value,
                ClaimStatus.MISLEADING_CONTEXT.value,
            }
            and self.evidence_count == 0
        )


@dataclass(slots=True)
class AuditReport:
    """The numbers, and what may be said about them."""

    started_at: str
    finished_at: str
    corpus_version: str
    results: list[ItemResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def genuine(self) -> list[ItemResult]:
        return [r for r in self.results if r.item.is_genuine]

    @property
    def decisive(self) -> list[ItemResult]:
        return [r for r in self.results if not r.abstained and r.error is None]

    def precision(self, status: ClaimStatus) -> tuple[int, int]:
        """Correct / claimed, for one decisive status.

        Returned as a pair so the caller must render the denominator. A bare
        percentage from a handful of items is the thing this whole module exists to
        avoid publishing.
        """
        claimed = [r for r in self.results if r.observed == status.value]
        correct = [r for r in claimed if r.matched]
        return len(correct), len(claimed)

    @property
    def false_positive_count(self) -> int:
        return sum(1 for r in self.genuine if r.is_false_positive)

    # Above this share of items failing to reach a provider, the run did not
    # measure the system. It measured an outage.
    MAX_PROVIDER_FAILURE = 0.20

    def false_positive_rate(self) -> tuple[float, int] | None:
        """Rate and sample size, or `None` when it cannot be supported.

        Returning `None` rather than a number is the point: a caller cannot print
        a rate the run does not justify.

        Two ways it can be unsupportable, and the second was found the hard way. A
        quota-exhausted run reported "0.0% false positives (n=45)" while 98% of
        items never reached the provider at all — every one of them abstained
        because nothing ran, and abstention is not a false positive. That is a
        clean bill of health issued by an outage, which is the exact failure this
        module exists to prevent.
        """
        sample = len(self.genuine)
        if sample < MIN_GENUINE_ITEMS:
            return None

        failure_rate, _ = self.provider_failure_rate
        if failure_rate > self.MAX_PROVIDER_FAILURE:
            return None

        return self.false_positive_count / sample, sample

    @property
    def citation_coverage(self) -> tuple[int, int]:
        """Decisive results carrying at least one citation. Must be n/n."""
        cited = sum(1 for r in self.decisive if r.evidence_count > 0)
        return cited, len(self.decisive)

    @property
    def abstention_rate(self) -> tuple[float, int]:
        if not self.results:
            return 0.0, 0
        return sum(1 for r in self.results if r.abstained) / len(self.results), len(self.results)

    def latency_by_category(self) -> dict[str, tuple[int, int]]:
        """Median and worst latency per category, in milliseconds."""
        buckets: dict[str, list[int]] = {}
        for r in self.results:
            buckets.setdefault(r.item.category.value, []).append(r.elapsed_ms)
        return {
            name: (int(statistics.median(values)), max(values))
            for name, values in sorted(buckets.items())
        }

    @property
    def provider_failure_rate(self) -> tuple[float, int]:
        failed = sum(1 for r in self.results if r.provider_failures)
        return (failed / len(self.results) if self.results else 0.0), len(self.results)

    @property
    def changed_sources(self) -> list[ItemResult]:
        return [r for r in self.results if r.source_changed]

    @property
    def uncited_decisive(self) -> list[ItemResult]:
        return [r for r in self.results if r.is_uncited_decisive]

    def render(self) -> str:
        """The report, as a document regenerated by the harness."""
        lines: list[str] = [
            "# Factify audit report",
            "",
            f"Run started {self.started_at}, finished {self.finished_at}.",
            f"Corpus version `{self.corpus_version}`.",
            "",
            "Generated by `app/audit/harness.py` over the whole manifest. Not a demo",
            "subset — a demo is chosen to succeed, and these numbers are meant to",
            "describe the system instead.",
            "",
            "## Coverage",
            "",
            "| Category | Items |",
            "|---|---:|",
        ]

        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.item.category.value] = counts.get(r.item.category.value, 0) + 1
        for name, count in sorted(counts.items()):
            lines.append(f"| {name} | {count} |")
        lines += [f"| **total** | **{self.total}** |", ""]

        lines += ["## Results", ""]

        for status in (ClaimStatus.CONTRADICTED, ClaimStatus.MISLEADING_CONTEXT):
            correct, claimed = self.precision(status)
            if claimed:
                lines.append(
                    f"- Precision on `{status.value}`: **{correct}/{claimed}** "
                    f"({correct / claimed:.0%})"
                )
            else:
                lines.append(f"- Precision on `{status.value}`: no results claimed this status")

        cited, total_decisive = self.citation_coverage
        lines.append(
            f"- Citation coverage on decisive results: **{cited}/{total_decisive}**"
            + ("" if cited == total_decisive else "  ← MUST BE COMPLETE")
        )

        uncited = self.uncited_decisive
        lines.append(
            f"- Decisive results with no citation: **{len(uncited)}**"
            + (" — this is a build break" if uncited else " (the invariant holds)")
        )

        rate = self.false_positive_rate()
        failure_rate, failure_n = self.provider_failure_rate

        if rate is None:
            lines += ["", "### False-positive rate: **not reportable**", ""]

            if len(self.genuine) < MIN_GENUINE_ITEMS:
                lines += [
                    f"Genuine-content items in this run: **{len(self.genuine)}**, floor "
                    f"is **{MIN_GENUINE_ITEMS}**.",
                    "",
                    "Below the floor a single failure moves the observed rate by more",
                    "than the target itself, so no figure is published.",
                ]
            else:
                lines += [
                    f"**{failure_rate:.0%}** of items ({failure_n} total) failed to reach",
                    "a provider, above the "
                    f"{self.MAX_PROVIDER_FAILURE:.0%} ceiling for a meaningful run.",
                    "",
                    "This run measured an outage, not the system. Items that never ran",
                    "abstained, and an abstention is not a false positive — so the",
                    "arithmetic would have produced a flattering figure from a broken",
                    "run. Re-run when providers are reachable.",
                ]

            lines += [
                "",
                f"The raw count is **{self.false_positive_count}** false positives out of",
                f"**{len(self.genuine)}** genuine items — a count, deliberately not a rate.",
            ]
        else:
            value, sample = rate
            lines += [
                "",
                f"- False-positive rate on genuine content: **{value:.1%}** "
                f"(n={sample}, {self.false_positive_count} failures)",
            ]

        abstention, sample = self.abstention_rate
        failure_rate, failure_sample = self.provider_failure_rate

        lines += [
            "",
            "## Observations",
            "",
            "Reported without targets. A falling abstention rate means the system has",
            "stopped refusing, which is the opposite of the design intent — so it is",
            "listed here rather than among the results.",
            "",
            f"- Abstention rate: **{abstention:.1%}** (n={sample})",
            f"- Provider failure rate: **{failure_rate:.1%}** (n={failure_sample})",
            "",
            "## Latency",
            "",
            "| Category | Median | Worst |",
            "|---|---:|---:|",
        ]
        for name, (median, worst) in self.latency_by_category().items():
            lines.append(f"| {name} | {median} ms | {worst} ms |")

        changed = self.changed_sources
        lines += ["", "## Sources that changed since collection", ""]
        if changed:
            lines.append(
                f"{len(changed)} item(s) no longer match the content hash recorded at"
                " collection. Each is recorded as a failure and abstains; none was"
                " repaired with substitute evidence."
            )
            for r in changed:
                lines.append(f"- `{r.item.id}` — {r.item.url or r.item.media_url}")
        else:
            lines.append("None. Every source still matches the hash recorded at collection.")

        errors = [r for r in self.results if r.error]
        if errors:
            lines += ["", "## Items that could not run", ""]
            for r in errors:
                lines.append(f"- `{r.item.id}`: {r.error}")

        lines += [
            "",
            "---",
            "",
            "Regenerate with `python -m app.audit.run`. Every rate above carries its",
            "denominator; any figure quoted without one did not come from this report.",
            "",
        ]
        return "\n".join(lines)


class AuditHarness:
    """Runs the manifest. Records what happened, repairs nothing."""

    def __init__(
        self,
        *,
        verify: object,
        corpus_version: str = "unknown",
        pace_seconds: float = 0.0,
    ) -> None:
        # `verify` is any async callable taking a ManifestItem and returning an
        # ItemResult. Injected rather than constructed so the harness can run
        # against the live pipeline or against replayed snapshots unchanged.
        self._verify = verify
        self._corpus_version = corpus_version

        # Pacing lives here, BETWEEN items and outside the timed region. The first
        # implementation put it inside the provider call, so every reported latency
        # came back as exactly the throttle interval — a 12-second median that
        # measured the rate limiter rather than the pipeline.
        self._pace = pace_seconds

    async def run(self, manifest: Manifest) -> AuditReport:
        started = datetime.now(UTC).isoformat()
        results: list[ItemResult] = []

        for index, item in enumerate(manifest.items):
            if index and self._pace:
                await asyncio.sleep(self._pace)

            began = time.perf_counter()
            try:
                result = await self._verify(item)  # type: ignore[operator]
            except Exception as error:
                result = ItemResult(
                    item=item,
                    observed=Expectation.ABSTAIN.value,
                    elapsed_ms=int((time.perf_counter() - began) * 1000),
                    error=f"{type(error).__name__}: {error}",
                )
            results.append(result)

        return AuditReport(
            started_at=started,
            finished_at=datetime.now(UTC).isoformat(),
            corpus_version=self._corpus_version,
            results=results,
        )
