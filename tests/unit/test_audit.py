"""M46 and M48 — the audit manifest, its report, and the offline demo path.

The tests that matter here are about what the report is allowed to *say*. A harness
that computes correct numbers and publishes them at a sample size that cannot
support them is the same failure as a confident wrong verdict, one level up.
"""

from __future__ import annotations

import pytest

from app.audit.harness import AuditReport, ItemResult
from app.audit.manifest import (
    MIN_GENUINE_ITEMS,
    Category,
    Expectation,
    Manifest,
    ManifestItem,
)
from app.audit.prewarm import DEMO_SET, DemoItem, RehearsalResult, rehearsal_report
from app.domain.enums import ClaimStatus

pytestmark = pytest.mark.unit


def _item(
    index: int = 0,
    category: Category = Category.GENUINE,
    expectation: Expectation = Expectation.ABSTAIN,
) -> ManifestItem:
    return ManifestItem(
        id=f"{category.value}-{index:03d}",
        category=category,
        expectation=expectation,
        text=f"claim {index}",
        url=f"https://example.org/{index}",
    )


def _result(
    item: ManifestItem,
    observed: str = Expectation.ABSTAIN.value,
    evidence: int = 0,
    **kwargs: object,
) -> ItemResult:
    return ItemResult(
        item=item,
        observed=observed,
        elapsed_ms=100,
        evidence_count=evidence,
        **kwargs,  # type: ignore[arg-type]
    )


def _report(results: list[ItemResult]) -> AuditReport:
    return AuditReport(
        started_at="2026-08-20T00:00:00+00:00",
        finished_at="2026-08-20T00:10:00+00:00",
        corpus_version="test",
        results=results,
    )


class TestTheGenuineContentFloor:
    """The gate. Below it, the false-positive rate is not a number worth printing."""

    def test_a_manifest_under_the_floor_reports_why(self) -> None:
        manifest = Manifest(items=[_item(i) for i in range(10)])

        assert not manifest.meets_genuine_floor
        shortfall = manifest.shortfall()
        assert shortfall is not None
        assert "10 genuine-content items" in shortfall
        assert str(MIN_GENUINE_ITEMS) in shortfall

    def test_a_manifest_at_the_floor_passes(self) -> None:
        manifest = Manifest(items=[_item(i) for i in range(MIN_GENUINE_ITEMS)])

        assert manifest.meets_genuine_floor
        assert manifest.shortfall() is None

    def test_only_genuine_items_count_toward_the_floor(self) -> None:
        """Padding with fact-checked items would not make a false-positive rate
        measurable — the rate is about genuine content specifically."""
        manifest = Manifest(
            items=[_item(i, Category.FACT_CHECKED, Expectation.CONTRADICTED) for i in range(50)]
        )

        assert manifest.genuine_count == 0
        assert not manifest.meets_genuine_floor

    def test_the_rate_is_withheld_below_the_floor(self) -> None:
        """`None` rather than a number, so a caller cannot print it by accident."""
        report = _report([_result(_item(i)) for i in range(10)])

        assert report.false_positive_rate() is None

    def test_the_rate_is_published_at_the_floor(self) -> None:
        report = _report([_result(_item(i)) for i in range(MIN_GENUINE_ITEMS)])

        rate = report.false_positive_rate()
        assert rate is not None
        value, sample = rate
        assert value == 0.0
        assert sample == MIN_GENUINE_ITEMS

    def test_the_rendered_report_refuses_to_print_a_rate_it_cannot_support(self) -> None:
        rendered = _report([_result(_item(i)) for i in range(8)]).render()

        assert "not reportable" in rendered
        assert "a count, deliberately not a rate" in rendered

        # Scoped to the false-positive section: other rates on the page (provider
        # failure, abstention) legitimately print percentages, and asserting that
        # no "0.0%" appears anywhere tested the wrong thing.
        section = rendered.split("### False-positive rate")[1].split("## Observations")[0]
        assert "%" not in section
        assert "8" in section


class TestWhatCountsAsAFailure:
    def test_a_decisive_status_on_genuine_content_is_a_false_positive(self) -> None:
        """The failure that matters most: telling someone a true article is false."""
        result = _result(_item(0), ClaimStatus.CONTRADICTED.value, evidence=1)

        assert result.is_false_positive

    def test_abstaining_on_genuine_content_is_not_a_false_positive(self) -> None:
        """A miss, not a false alarm. Counted separately because they are different
        failures with different costs."""
        result = _result(_item(0), Expectation.ABSTAIN.value)

        assert not result.is_false_positive
        assert result.abstained

    def test_a_decisive_status_with_no_citation_is_flagged(self) -> None:
        result = _result(
            _item(0, Category.FACT_CHECKED, Expectation.CONTRADICTED),
            ClaimStatus.CONTRADICTED.value,
            evidence=0,
        )

        assert result.is_uncited_decisive

    def test_a_cited_decisive_status_is_not_flagged(self) -> None:
        result = _result(
            _item(0, Category.FACT_CHECKED, Expectation.CONTRADICTED),
            ClaimStatus.CONTRADICTED.value,
            evidence=2,
        )

        assert not result.is_uncited_decisive
        assert result.matched


class TestReportingRules:
    def test_every_rate_carries_its_denominator(self) -> None:
        """96% over 25 items and over 2,500 are different claims."""
        results = [_result(_item(i)) for i in range(MIN_GENUINE_ITEMS)]
        results.append(
            _result(
                _item(0, Category.FACT_CHECKED, Expectation.CONTRADICTED),
                ClaimStatus.CONTRADICTED.value,
                evidence=1,
            )
        )
        rendered = _report(results).render()

        assert "n=" in rendered
        assert "1/1" in rendered  # precision as a fraction, not a bare percentage

    def test_abstention_is_reported_as_an_observation_not_a_result(self) -> None:
        """A falling abstention rate means the system stopped refusing."""
        rendered = _report([_result(_item(i)) for i in range(5)]).render()

        assert "## Observations" in rendered
        assert "stopped refusing" in rendered
        observations = rendered.split("## Observations")[1]
        assert "Abstention rate" in observations

    def test_a_changed_source_is_named_rather_than_repaired(self) -> None:
        results = [_result(_item(0)), _result(_item(1), source_changed=True)]
        rendered = _report(results).render()

        assert "Sources that changed since collection" in rendered
        assert "none was repaired with substitute evidence" in rendered
        assert "genuine-001" in rendered

    def test_a_clean_run_says_every_source_still_matches(self) -> None:
        rendered = _report([_result(_item(0))]).render()

        assert "Every source still matches the hash recorded at collection" in rendered

    def test_uncited_decisive_results_are_called_a_build_break(self) -> None:
        results = [
            _result(
                _item(0, Category.FACT_CHECKED, Expectation.CONTRADICTED),
                ClaimStatus.CONTRADICTED.value,
                evidence=0,
            )
        ]
        rendered = _report(results).render()

        assert "this is a build break" in rendered

    def test_latency_is_reported_per_category(self) -> None:
        results = [
            _result(_item(0)),
            _result(_item(1, Category.ADVERSARIAL)),
        ]
        rendered = _report(results).render()

        assert "## Latency" in rendered
        assert "genuine" in rendered
        assert "adversarial" in rendered


class TestManifestRoundTrip:
    def test_a_manifest_survives_save_and_load(self, tmp_path: object) -> None:
        from pathlib import Path

        path = Path(str(tmp_path)) / "manifest.json"
        original = Manifest(
            items=[
                _item(0),
                _item(1, Category.FACT_CHECKED, Expectation.CONTRADICTED),
            ],
            collected_at="2026-08-20T00:00:00+00:00",
            corpus_version="test",
        )
        original.save(path)

        loaded = Manifest.load(path)

        assert len(loaded.items) == 2
        assert loaded.items[1].category is Category.FACT_CHECKED
        assert loaded.items[1].expectation is Expectation.CONTRADICTED
        assert loaded.collected_at == original.collected_at

    def test_category_gaps_are_reported(self) -> None:
        from app.audit.harness import category_gaps

        gaps = category_gaps(Manifest(items=[_item(0)]))

        # Everything except `genuine` is missing, and the report should be able to
        # say so rather than implying the manifest covers every path.
        assert Category.RECYCLED_MEDIA.value in gaps
        assert Category.GENUINE.value not in gaps


class TestOfflineRehearsal:
    """M48: the demo runs with the network gone, and says results are cached."""

    def test_a_fully_served_rehearsal_passes(self) -> None:
        results = [
            RehearsalResult(item=item, served=True, shows_timestamp=True, age_seconds=600)
            for item in DEMO_SET
        ]

        rendered = rehearsal_report(results)
        assert "**PASS**" in rendered
        assert f"{len(DEMO_SET)}/{len(DEMO_SET)}" in rendered

    def test_an_unserved_item_fails_the_rehearsal(self) -> None:
        results = [
            RehearsalResult(item=DEMO_SET[0], served=True, shows_timestamp=True),
            RehearsalResult(item=DEMO_SET[1], served=False, reason="no cached verdict"),
        ]

        rendered = rehearsal_report(results)
        assert "**FAIL**" in rendered
        assert "would fail live on venue wifi" in rendered

    def test_serving_without_a_timestamp_is_a_build_break(self) -> None:
        """A cached result presented as fresh is a claim about the present made
        from evidence about the past."""
        results = [RehearsalResult(item=DEMO_SET[0], served=True, shows_timestamp=False)]

        rendered = rehearsal_report(results)
        assert "**FAIL**" in rendered
        assert "presented as fresh" in rendered

    def test_the_demo_set_includes_an_abstention(self) -> None:
        """A demo of only successes is a demo chosen to succeed."""
        assert any("abstain" in item.id for item in DEMO_SET)

    def test_the_demo_set_includes_an_injection_attempt(self) -> None:
        assert any("injection" in item.id for item in DEMO_SET)

    def test_every_demo_item_states_what_it_exercises(self) -> None:
        assert all(item.beat for item in DEMO_SET)

    def test_a_demo_item_needs_something_to_verify(self) -> None:
        assert DemoItem(id="x", text="a claim").source == "a claim"
        assert DemoItem(id="x").source == ""


class TestABrokenRunPublishesNoRate:
    """Found the hard way: a quota-exhausted run reported 0.0% false positives
    over 45 genuine items while 98% of them never reached a provider.

    Every failed item abstained, and an abstention is not a false positive, so the
    arithmetic produced a clean bill of health issued by an outage. The sample
    floor did not catch it — the sample was fine, the run was not.
    """

    @staticmethod
    def _results(*, failed: int, total: int = MIN_GENUINE_ITEMS) -> list[ItemResult]:
        results = []
        for i in range(total):
            results.append(
                _result(
                    _item(i),
                    provider_failures=("extraction: provider returned 429",) if i < failed else (),
                )
            )
        return results

    def test_a_mostly_failed_run_withholds_the_rate(self) -> None:
        report = _report(self._results(failed=MIN_GENUINE_ITEMS - 2))

        assert not report.ran_cleanly
        assert report.false_positive_rate() is None

    def test_a_clean_run_publishes_it(self) -> None:
        report = _report(self._results(failed=0))

        assert report.ran_cleanly
        assert report.false_positive_rate() is not None

    def test_a_few_failures_are_tolerated(self) -> None:
        """Providers fail occasionally; that is not the same as an outage."""
        report = _report(self._results(failed=2))

        assert report.ran_cleanly
        assert report.false_positive_rate() is not None

    def test_the_report_names_the_outage_rather_than_the_sample_size(self) -> None:
        rendered = _report(self._results(failed=MIN_GENUINE_ITEMS - 1)).render()

        assert "not reportable" in rendered
        assert "measured an outage, not the system" in rendered
        # The sample was fine, so it must not blame the floor.
        assert "floor is" not in rendered

    def test_the_sample_floor_still_reports_its_own_reason(self) -> None:
        rendered = _report([_result(_item(i)) for i in range(6)]).render()

        assert "floor is" in rendered
        assert "measured an outage" not in rendered
