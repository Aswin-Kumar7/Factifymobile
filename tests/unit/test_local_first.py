"""Our own records first; the paid services only when they do not answer (step 1).

Held here: a fact-checker's verdict is read from its page's ClaimReview markup in the
shapes publishers actually use; each fact-check the API points at is kept from the
fact-checker's own page and joins the local records at once; the news is collected on
a schedule that starts, stops, and re-reads the fact-checks only when a batch brought
something new; and `/internal/ingest-tick` runs a batch rather than only saying so.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.extraction.claimreview import read_claim_reviews
from app.knowledge.factchecks import FactCheckKeeper
from app.knowledge.ingest import TickResult
from app.knowledge.schedule import IngestionSchedule
from app.security.fetcher import FetchResult


def _page(*blocks: object) -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>' for block in blocks
    )
    return f"<html><head>{scripts}</head><body>Fact check</body></html>"


PIB = {
    "@context": "https://schema.org",
    "@type": "ClaimReview",
    "url": "https://pib.gov.in/factcheck/5000",
    "claimReviewed": "Govt is paying Rs 5,000 a month to every woman",
    "datePublished": "2026-09-24",
    "author": {"@type": "Organization", "name": "PIB Fact Check"},
    "reviewRating": {"@type": "Rating", "alternateName": "Fake", "ratingValue": 1},
}


class TestClaimReview:
    def test_a_plain_claim_review(self) -> None:
        [review] = read_claim_reviews(_page(PIB))
        assert review.claim_reviewed == "Govt is paying Rs 5,000 a month to every woman"
        assert review.rating == "Fake"
        assert review.publisher == "PIB Fact Check"
        assert review.published_at is not None and review.published_at.year == 2026

    def test_inside_a_graph_or_a_list_and_with_other_markup(self) -> None:
        article = {"@type": "NewsArticle", "headline": "Fact check"}
        graph = {"@context": "https://schema.org", "@graph": [article, PIB]}
        assert len(read_claim_reviews(_page(graph))) == 1
        assert len(read_claim_reviews(_page([article, PIB]))) == 1

    def test_broken_or_absent_markup_is_nothing(self) -> None:
        broken = '<script type="application/ld+json">{not json</script>'
        assert read_claim_reviews(broken) == []
        assert read_claim_reviews("<html><body>No markup</body></html>") == []
        assert read_claim_reviews(_page({"@type": "ClaimReview", "reviewRating": {}})) == []


class _Fetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    async def fetch(self, url: str, **_: object) -> object:
        self.asked.append(url)
        body = self.pages.get(url, "<html></html>").encode()
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
        )


class _Connection:
    def __init__(self, written: list[dict[str, Any]]) -> None:
        self.written = written

    async def execute(self, _sql: str, params: tuple[Any, ...] = ()) -> Any:
        self.written.append({"params": params})

        class _Cursor:
            async def fetchone(self) -> dict[str, Any]:
                return {"id": str(uuid4())}

        return _Cursor()


class _Database:
    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    def connection(self) -> Any:
        database = self

        class _Context:
            async def __aenter__(self) -> _Connection:
                return _Connection(database.written)

            async def __aexit__(self, *_: object) -> None:
                return None

        return _Context()


class TestKeepingFactChecks:
    async def test_each_page_the_api_points_at_is_kept_and_joins_the_records(self) -> None:
        database = _Database()
        fetcher = _Fetcher({"https://pib.gov.in/factcheck/5000": _page(PIB)})
        joined: list[Any] = []
        keeper = FactCheckKeeper(database=database, fetcher=fetcher, on_kept=joined.extend)

        kept = await keeper.keep(["https://pib.gov.in/factcheck/5000", "https://no-markup.in/x"])

        assert kept == 1
        assert len(database.written) == 1
        [record] = joined
        assert record.rating == "Fake"
        assert record.url == "https://pib.gov.in/factcheck/5000"

    async def test_a_page_is_fetched_once(self) -> None:
        fetcher = _Fetcher({"https://pib.gov.in/factcheck/5000": _page(PIB)})
        keeper = FactCheckKeeper(database=_Database(), fetcher=fetcher)
        keeper.remember(["https://pib.gov.in/factcheck/5000"])
        keeper.remember(["https://pib.gov.in/factcheck/5000"])
        await asyncio.sleep(0.05)
        assert fetcher.asked == ["https://pib.gov.in/factcheck/5000"]


class TestTheSchedule:
    def _schedule(
        self, monkeypatch: pytest.MonkeyPatch, result: TickResult
    ) -> tuple[IngestionSchedule, list[int]]:
        reloaded: list[int] = []

        async def fake_tick(self: object, *_: object, **__: object) -> TickResult:
            return result

        class _Registry:
            def __init__(self, *_: object) -> None: ...

            async def sync(self, *_: object) -> int:
                return 0

        monkeypatch.setattr("app.knowledge.schedule.IngestionWorker.tick", fake_tick)
        monkeypatch.setattr("app.knowledge.schedule.FeedRegistry", _Registry)

        async def after() -> None:
            reloaded.append(1)

        schedule = IngestionSchedule(
            database=_Database(),
            fetcher=None,
            interval_seconds=0,
            after_tick=after,
            definitions=(),
        )
        return schedule, reloaded

    async def test_fact_checks_are_reread_only_when_something_came_in(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        quiet, reloaded = self._schedule(monkeypatch, TickResult(feeds_attempted=3))
        await quiet.tick()
        assert reloaded == []

        busy, reloaded = self._schedule(monkeypatch, TickResult(feeds_attempted=3, items_new=12))
        await busy.tick()
        assert reloaded == [1]

    async def test_at_zero_it_does_not_run_in_the_background(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        schedule, _ = self._schedule(monkeypatch, TickResult())
        schedule.start()
        assert schedule._task is None
        await schedule.stop()


def test_the_tick_endpoint_runs_a_batch() -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    class _Ingestion:
        ran = 0

        async def tick(self) -> TickResult:
            _Ingestion.ran += 1
            return TickResult(feeds_attempted=3, items_new=7, factchecks_kept=2)

    settings = Settings(_env_file=None, ingest_trigger_secret="s3cret")  # type: ignore[call-arg]
    client = TestClient(create_app(settings))
    client.app.state.ingestion = _Ingestion()  # type: ignore[attr-defined]

    refused = client.post("/internal/ingest-tick")
    assert refused.status_code == 404
    done = client.post("/internal/ingest-tick", headers={"x-factify-trigger": "s3cret"})
    assert done.status_code == 202
    assert done.json() == {"status": "done", "feeds": "3", "items_new": "7", "factchecks_kept": "2"}
    assert _Ingestion.ran == 1
