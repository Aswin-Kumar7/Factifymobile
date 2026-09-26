"""M13 and M14 against the real database.

The gates live here: re-submitting identical content performs zero external calls,
and setting every cap to zero produces a complete, honest run.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.cache.keys import CacheKeyParts
from app.cache.service import CacheService
from app.config import ProviderSettings
from app.governor.governor import Governor, Grant, ProviderUnavailable, Skip, SkipReason
from app.observability.metrics import metrics
from tests.conftest import requires_database

pytestmark = [pytest.mark.db, requires_database]


def _parts(**overrides: Any) -> CacheKeyParts:
    base: dict[str, Any] = {
        "content_hash": "sha256:demo",
        "rule_version": "2026.08.1",
        "extractor_version": "1",
        "corpus_version": "1",
        "policy_profile": "default",
        "language": "en",
    }
    base.update(overrides)
    return CacheKeyParts(**base)


def _providers(**caps: int) -> dict[str, ProviderSettings]:
    return {
        # The emergency stop: since 2026-09-26 the only daily limit that refuses.
        name: ProviderSettings(
            enabled=True, api_key="test-key", daily_hard_cap=cap, per_minute_cap=0
        )
        for name, cap in caps.items()
    }


class TestVerdictCache:
    async def test_a_stored_verdict_comes_back(self, conn: Any) -> None:
        cache = CacheService(conn)
        await cache.put_verdict(_parts(), {"overall_action": "DO_NOT_SHARE"})

        cached = await cache.get_verdict(_parts())

        assert cached is not None
        assert cached.payload["overall_action"] == "DO_NOT_SHARE"

    async def test_a_cached_verdict_always_carries_its_retrieval_time(self, conn: Any) -> None:
        """A result shown without saying when it was established is a claim about the
        present made from evidence about the past."""
        cache = CacheService(conn)
        await cache.put_verdict(_parts(), {"overall_action": "SAFE_TO_SHARE"})

        cached = await cache.get_verdict(_parts())

        assert cached is not None
        assert cached.retrieved_at is not None
        assert cached.age.total_seconds() >= 0

    async def test_a_rule_version_bump_does_not_serve_the_old_verdict(self, conn: Any) -> None:
        """The gate: a cache must never outlive the rules that produced its contents."""
        cache = CacheService(conn)
        await cache.put_verdict(_parts(rule_version="2026.08.1"), {"action": "old"})

        assert await cache.get_verdict(_parts(rule_version="2026.09.1")) is None

    async def test_a_corpus_change_does_not_serve_a_stale_corroboration(self, conn: Any) -> None:
        cache = CacheService(conn)
        await cache.put_verdict(_parts(corpus_version="1"), {"action": "old"})

        assert await cache.get_verdict(_parts(corpus_version="2")) is None

    async def test_an_abstention_is_marked_negative(self, conn: Any) -> None:
        cache = CacheService(conn)
        await cache.put_verdict(_parts(), {"action": "SEND_TO_REVIEW"}, is_negative=True)

        cached = await cache.get_verdict(_parts())

        assert cached is not None
        assert cached.is_negative


class TestExtractionCache:
    async def test_re_extracting_the_same_document_is_a_hit(self, conn: Any) -> None:
        """This is what makes the Day 13 evaluation affordable to re-run."""
        cache = CacheService(conn)
        await cache.put_extraction(
            content_hash="sha256:doc", extractor_version="1", payload={"claims": [1, 2]}
        )

        payload = await cache.get_extraction(content_hash="sha256:doc", extractor_version="1")

        assert payload == {"claims": [1, 2]}

    async def test_an_expired_row_is_renewed_when_rewritten(self, conn: Any) -> None:
        """A rewrite used to replace the payload but keep the old expiry, so a row that
        had expired once stayed expired forever and every repeat re-ran extraction."""
        from datetime import UTC, datetime, timedelta

        from app.db.repositories import CacheRepository

        await CacheRepository(conn).put_extraction(
            content_hash="sha256:renewed",
            extractor_version="1",
            payload={"claims": ["old"]},
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        cache = CacheService(conn)
        assert (
            await cache.get_extraction(content_hash="sha256:renewed", extractor_version="1") is None
        )

        # The production write path: the service sets a fresh expiry on every put.
        await cache.put_extraction(
            content_hash="sha256:renewed", extractor_version="1", payload={"claims": ["new"]}
        )

        payload = await cache.get_extraction(content_hash="sha256:renewed", extractor_version="1")
        assert payload == {"claims": ["new"]}

    async def test_a_new_extractor_version_misses(self, conn: Any) -> None:
        cache = CacheService(conn)
        await cache.put_extraction(
            content_hash="sha256:doc", extractor_version="1", payload={"claims": []}
        )

        assert await cache.get_extraction(content_hash="sha256:doc", extractor_version="2") is None

    async def test_url_text_round_trips(self, conn: Any) -> None:
        cache = CacheService(conn)
        await cache.put_url_text(
            canonical_url="https://a.example/x",
            extractor_version="1",
            text="article body",
            final_url="https://a.example/x",
        )

        text = await cache.get_url_text(canonical_url="https://a.example/x", extractor_version="1")

        assert text == "article body"


class TestZeroExternalCallsOnRepeat:
    async def test_resubmitting_identical_content_spends_no_provider_budget(
        self, conn: Any
    ) -> None:
        """**The M13 gate**, measured rather than asserted.

        A pipeline that probes the cache first must not touch the governor at all on
        a hit — so the budget counter is the instrument.
        """
        cache = CacheService(conn)
        governor = Governor(conn, _providers(vision=10))
        calls = 0

        async def verify(parts: CacheKeyParts) -> dict[str, Any]:
            nonlocal calls
            cached = await cache.get_verdict(parts)
            if cached is not None:
                return cached.payload

            outcome = await governor.try_acquire("vision")
            if isinstance(outcome, Grant):
                calls += 1
            result = {"overall_action": "MISLEADING_CONTEXT"}
            await cache.put_verdict(parts, result)
            return result

        first = await verify(_parts())
        second = await verify(_parts())
        third = await verify(_parts())

        assert first == second == third
        assert calls == 1, "a cache hit must not reach the governor"

        usage = await governor.usage("vision")
        assert usage["used"] == 1


class TestGovernorBudget:
    async def test_calls_are_permitted_up_to_the_cap(self, conn: Any) -> None:
        governor = Governor(conn, _providers(vision=3))

        outcomes = [await governor.try_acquire("vision") for _ in range(3)]

        assert all(isinstance(o, Grant) for o in outcomes)

    async def test_the_call_past_the_cap_is_skipped_with_a_reason(self, conn: Any) -> None:
        governor = Governor(conn, _providers(vision=2))

        for _ in range(2):
            await governor.try_acquire("vision")
        outcome = await governor.try_acquire("vision")

        assert isinstance(outcome, Skip)
        assert outcome.reason is SkipReason.CAPACITY_LIMITED
        assert outcome.note == "vision: capacity limited"

    async def test_exhaustion_does_not_retry_past_the_cap(self, conn: Any) -> None:
        governor = Governor(conn, _providers(vision=1))

        await governor.try_acquire("vision")
        for _ in range(5):
            await governor.try_acquire("vision")

        usage = await governor.usage("vision")
        assert usage["used"] == 1

    async def test_a_disabled_provider_is_skipped_not_called(self, conn: Any) -> None:
        governor = Governor(conn, {"vision": ProviderSettings(enabled=False)})

        outcome = await governor.try_acquire("vision")

        assert isinstance(outcome, Skip)
        assert outcome.reason is SkipReason.DISABLED

    async def test_a_daily_alarm_never_refuses(self, conn: Any) -> None:
        """The daily cap is a spend alarm: crossing it logs, and calls continue."""
        providers = {"vision": ProviderSettings(enabled=True, api_key="k", daily_cap=1)}
        governor = Governor(conn, providers)

        outcomes = [await governor.try_acquire("vision") for _ in range(3)]

        assert all(isinstance(o, Grant) for o in outcomes)

    async def test_an_unknown_provider_is_skipped(self, conn: Any) -> None:
        governor = Governor(conn, {})

        outcome = await governor.try_acquire("never_configured")

        assert isinstance(outcome, Skip)

    async def test_the_burst_ceiling_gives_up_only_after_waiting(self, conn: Any) -> None:
        """A burst waits for room in the window; it is refused only when none comes
        within the allowed wait (kept short here so the test does not sleep)."""
        providers = {
            "llm": ProviderSettings(enabled=True, api_key="k", daily_cap=1000, per_minute_cap=2)
        }
        governor = Governor(conn, providers, pace_max_wait=0.05)

        first = await governor.try_acquire("llm")
        second = await governor.try_acquire("llm")
        third = await governor.try_acquire("llm")

        assert isinstance(first, Grant)
        assert isinstance(second, Grant)
        assert isinstance(third, Skip)
        assert third.reason is SkipReason.RATE_LIMITED

    async def test_acquire_raises_for_callers_that_cannot_proceed(self, conn: Any) -> None:
        governor = Governor(conn, _providers(vision=1))
        await governor.acquire("vision")

        with pytest.raises(ProviderUnavailable, match="capacity limited"):
            await governor.acquire("vision")

    async def test_the_call_wrapper_records_success(self, conn: Any) -> None:
        metrics.reset()
        governor = Governor(conn, _providers(vision=5))

        async with governor.call("vision"):
            pass

        assert metrics.snapshot()["vision"]["successes"] == 1

    async def test_the_call_wrapper_records_failure_and_reraises(self, conn: Any) -> None:
        metrics.reset()
        governor = Governor(conn, _providers(vision=5))

        with pytest.raises(RuntimeError):
            async with governor.call("vision"):
                raise RuntimeError("provider exploded")

        assert metrics.snapshot()["vision"]["failures"] == 1


class TestEveryCapAtZero:
    async def test_a_complete_honest_run_with_nothing_enabled(self, conn: Any) -> None:
        """**The M14 gate.**

        Every provider capped at zero. The run completes, nothing is called, and
        every skip carries a reason the response can quote.
        """
        metrics.reset()
        governor = Governor(conn, _providers(llm=0, factcheck=0, vision=0, archive=0))

        outcomes = [
            await governor.try_acquire(name) for name in ("llm", "factcheck", "vision", "archive")
        ]

        assert all(isinstance(o, Skip) for o in outcomes)
        assert len(governor.skips) == 4

        notes = governor.capacity_notes()
        assert notes == (
            "llm: capacity limited",
            "factcheck: capacity limited",
            "vision: capacity limited",
            "archive: capacity limited",
        )

        # Skips are not failures: the honest degradation path must not read as an
        # outage in the Day 13 provider-failure report.
        snapshot = metrics.snapshot()
        for name in ("llm", "factcheck", "vision", "archive"):
            assert snapshot[name]["skips"] == 1
            assert snapshot[name]["calls"] == 0
            assert snapshot[name]["failure_rate"] == 0.0

    async def test_usage_reports_zero_spend(self, conn: Any) -> None:
        governor = Governor(conn, _providers(vision=0))

        await governor.try_acquire("vision")

        assert await governor.usage("vision") == {"used": 0, "cap": 0}


class TestFailsClosed:
    async def test_an_unreachable_budget_store_prevents_the_call(self, conn: Any) -> None:
        """If we cannot account for a call, we do not make it.

        An unaccounted call is exactly the one that overruns a free tier.
        """
        governor = Governor(conn, _providers(vision=10))

        async def broken(**kwargs: Any) -> bool:
            raise RuntimeError("database unreachable")

        governor._budget.try_consume = broken  # type: ignore[method-assign]

        outcome = await governor.try_acquire("vision")

        assert isinstance(outcome, Skip)
        assert outcome.reason is SkipReason.GOVERNOR_UNAVAILABLE


class TestCacheMetrics:
    async def test_hit_rate_is_measurable_from_the_first_request(self, conn: Any) -> None:
        """A stated day-one investor metric, so it cannot be instrumented later."""
        metrics.reset()
        cache = CacheService(conn)

        await cache.get_verdict(_parts())  # miss
        await cache.put_verdict(_parts(), {"action": "x"})
        await cache.get_verdict(_parts())  # hit

        report = metrics.cache_snapshot()["verdict"]
        assert report == {"hits": 1, "misses": 1, "hit_rate": 0.5}
