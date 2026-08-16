"""The M26 gate: at least one multi-outlet origin cluster in the live corpus.

    FACIFY_TEST_DATABASE_URL=... uv run pytest -m live

This is deliberately a live test. The gate asks whether real Indian outlets, on a
real afternoon, actually produce the syndication that origin clustering exists to
collapse. A fixture cannot answer that — it would only prove the code does what the
fixture was written to elicit.

If this fails, either the MinHash threshold is mistuned or the feed mix is too
narrow. Both are cheap to fix now and expensive to discover during evaluation with
nothing to demonstrate.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from app.db.repositories import CorpusRepository, SourceRepository
from app.knowledge.clustering import OriginClusterer
from app.knowledge.ingest import IngestionWorker
from app.knowledge.registry import FeedRegistry, load_registry
from app.security.fetcher import SecureFetcher
from tests.conftest import requires_database

pytestmark = [
    pytest.mark.live,
    requires_database,
    pytest.mark.skipif(
        os.environ.get("FACIFY_TEST_DATABASE_URL") is None,
        reason="live ingestion needs a database to write the corpus into",
    ),
]


@pytest.mark.anyio
async def test_live_feeds_produce_a_multi_outlet_origin_cluster(conn: Any) -> None:
    """Ingest real feeds and look for a wire story carried by two or more outlets."""
    from app.db.repositories import FeedRepository

    definitions = load_registry()
    registry = FeedRegistry(FeedRepository(conn))
    await registry.sync(definitions)

    fetcher = SecureFetcher(timeout_seconds=25.0, max_bytes=8 * 1024 * 1024)
    clusterer = OriginClusterer()
    worker = IngestionWorker(
        fetcher=fetcher,
        registry=registry,
        corpus=CorpusRepository(conn),
        sources=SourceRepository(conn),
        clusterer=clusterer,
    )

    by_url = {definition.url: definition for definition in definitions}

    # Enough ticks to reach every declared feed: one tick is a bounded batch of five,
    # and syndication only shows up once enough outlets have been read. The wire
    # carriers are what produce it, and they are spread through the registry.
    total = 0
    hydrated = 0
    ticks = len(definitions) // 5 + 2
    for _ in range(ticks):
        result = await worker.tick(by_url, limit=5)
        total += result.items_new
        hydrated += result.items_hydrated
        if not result.feeds_attempted:
            break

    await fetcher.aclose()

    assert total > 0, "no items ingested at all; check network and feed reachability"

    # Checked before the gate itself, because an un-hydrated run would fail the gate
    # for a reason that has nothing to do with the feed mix or the threshold, and the
    # error message should say which of those actually happened.
    assert hydrated > 0, (
        f"ingested {total} items but hydrated none with article bodies. Origin "
        "clustering over feed excerpts cannot detect syndication — each CMS truncates "
        "at a different length — so the gate below would fail for the wrong reason."
    )

    multi = clusterer.multi_outlet_clusters()

    assert multi, (
        f"ingested {total} items ({hydrated} hydrated) across "
        f"{len(clusterer.clusters)} clusters but found no multi-outlet cluster. "
        "Either the MinHash threshold is mistuned or the feed mix carries too little "
        "syndication."
    )
