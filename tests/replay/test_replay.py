"""M47 — the suite runs against stored bytes, never the network.

The gate is that the full suite passes with networking disabled. These tests assert
the two halves of that: extraction and web parsing work from snapshots, and the
replay layer refuses to reach the network when a snapshot is missing rather than
quietly fetching.
"""

from __future__ import annotations

import socket

import pytest

from app.extraction.web import extract
from app.knowledge.ingest import parse_feed
from app.security.fetcher import FetchResult
from tests.replay import snapshots

pytestmark = pytest.mark.replay


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any outbound connection an immediate, obvious failure.

    Stronger than trusting the code not to fetch: if anything under test reaches
    for the network, the test fails with a message naming the problem rather than
    hanging or silently passing against a live response.

    DNS is the lever rather than `socket.socket`, which was tried first and broke
    every test at setup — asyncio's selector loop builds an internal socketpair on
    Windows, so blocking socket construction blocks the event loop itself. Nothing
    can reach a real host without resolving it, and a loopback socketpair does not
    resolve anything.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test resolved a hostname; CI must run entirely from snapshots")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# JSON-LD, because that is what the extractor reads. An `article:published_time`
# meta tag was tried first and produced no date at all — see the measurement in
# docs/ops-notes.md for how much real-world coverage that costs.
ARTICLE_HTML = b"""<!doctype html>
<html><head>
<title>Relief scheme announced for rain-hit farmers</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"NewsArticle",
 "headline":"Relief scheme announced for rain-hit farmers",
 "datePublished":"2026-03-14T09:30:00+05:30",
 "publisher":{"@type":"Organization","name":"Example Wire"}}
</script>
</head><body><article>
<h1>Relief scheme announced for rain-hit farmers</h1>
<p>New Delhi, Mar 14 (PTI) The government on Friday announced a relief scheme for
farmers affected by unseasonal rainfall, with an outlay of five hundred crore rupees.</p>
<p>Officials said applications would open next month and that district collectors had
been asked to complete verification within thirty days.</p>
</article></body></html>"""

FEED_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Example Wire</title>
<item>
  <title>Relief scheme announced for rain-hit farmers</title>
  <link>https://wire.example/relief-scheme</link>
  <description>The government announced a relief scheme with an outlay of five
  hundred crore rupees.</description>
  <pubDate>Fri, 14 Mar 2026 09:30:00 +0530</pubDate>
</item>
</channel></rss>"""

ARTICLE_URL = "https://wire.example/relief-scheme"
FEED_URL = "https://wire.example/feed"


@pytest.fixture(autouse=True)
def _fixtures_recorded(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Record the fixtures into an isolated snapshot directory.

    Isolated per-run so these tests neither depend on nor disturb snapshots
    captured from real publishers.
    """
    directory = tmp_path_factory.mktemp("snapshots")
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", directory)
    snapshots.save(ARTICLE_URL, status_code=200, body=ARTICLE_HTML)
    snapshots.save(FEED_URL, status_code=200, body=FEED_XML, content_type="application/rss+xml")
    return directory


class TestSnapshotStorage:
    def test_a_snapshot_round_trips_byte_exactly(self) -> None:
        snapshot = snapshots.load(ARTICLE_URL)

        assert snapshot.body == ARTICLE_HTML
        assert snapshot.status_code == 200
        assert snapshot.content_hash.startswith("sha256:")

    def test_the_retrieval_time_is_recorded(self) -> None:
        """A snapshot without one is bytes of unknown age."""
        assert snapshots.load(ARTICLE_URL).fetched_at

    def test_a_missing_snapshot_raises_rather_than_fetching(self) -> None:
        """The whole point. Falling back to the network would make CI
        network-dependent again, silently."""
        with pytest.raises(snapshots.SnapshotMissing, match="must not fetch"):
            snapshots.load("https://never-recorded.example/page")

    def test_recording_is_off_by_default(self) -> None:
        assert not snapshots.recording()


class TestReplayFetcher:
    @pytest.mark.anyio
    async def test_it_serves_a_snapshot_with_no_network(self, no_network: None) -> None:
        fetcher = snapshots.ReplayFetcher()

        result = await fetcher.fetch(ARTICLE_URL)

        assert isinstance(result, FetchResult)
        assert result.status_code == 200
        assert "relief scheme" in result.text.lower()
        assert fetcher.requested == [ARTICLE_URL]

    @pytest.mark.anyio
    async def test_a_provider_post_replays_too(self, no_network: None) -> None:
        """A test that reaches a model provider asserts against a model."""
        fetcher = snapshots.ReplayFetcher()

        result = await fetcher.post_json(ARTICLE_URL, {"contents": []}, provider="llm")

        assert isinstance(result, FetchResult)

    @pytest.mark.anyio
    async def test_an_unrecorded_url_fails_loudly(self, no_network: None) -> None:
        with pytest.raises(snapshots.SnapshotMissing):
            await snapshots.ReplayFetcher().fetch("https://unrecorded.example/x")


class TestPipelineStagesRunOffline:
    """The stages that normally touch the web, driven entirely from snapshots."""

    @pytest.mark.anyio
    async def test_web_extraction_from_a_snapshot(self, no_network: None) -> None:
        result = await snapshots.ReplayFetcher().fetch(ARTICLE_URL)
        assert isinstance(result, FetchResult)

        article = extract(result.text, url=ARTICLE_URL)

        assert "five hundred crore" in article.body
        assert article.published_at is not None
        assert article.published_at.year == 2026

    @pytest.mark.anyio
    async def test_feed_parsing_from_a_snapshot(self, no_network: None) -> None:
        result = await snapshots.ReplayFetcher().fetch(FEED_URL)
        assert isinstance(result, FetchResult)

        items = parse_feed(result.body, publisher="Example Wire")

        assert len(items) == 1
        assert items[0].published_at is not None
        assert "relief scheme" in items[0].title.lower()

    @pytest.mark.anyio
    async def test_the_same_snapshot_gives_the_same_result_twice(self, no_network: None) -> None:
        """Determinism is the reason for all of this: a publisher editing a page
        mid-run must not be able to turn a passing suite red."""
        fetcher = snapshots.ReplayFetcher()

        first = await fetcher.fetch(ARTICLE_URL)
        second = await fetcher.fetch(ARTICLE_URL)
        assert isinstance(first, FetchResult)
        assert isinstance(second, FetchResult)

        assert (
            extract(first.text, url=ARTICLE_URL).body == extract(second.text, url=ARTICLE_URL).body
        )
