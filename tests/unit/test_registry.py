"""M24 and M25 — registry, trigger authentication, backoff and feed parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.knowledge.ingest import parse_feed
from app.knowledge.registry import (
    BACKOFF_CEILING_SECONDS,
    authenticate_trigger,
    backoff_for,
    failures_behind,
    load_registry,
    window_start,
)

pytestmark = pytest.mark.unit


# Declared as text and encoded: a bytes literal cannot carry Devanagari, and the
# Hindi item is the point of the fixture.
_RSS_TEXT = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Example Feed</title>
<item>
  <title>Government announces relief scheme for farmers</title>
  <link>https://example.org/story-one?utm_source=rss&amp;utm_medium=feed</link>
  <description>&lt;p&gt;New Delhi, Aug 16 (PTI) The government on Friday announced
    a relief scheme with an outlay of five hundred crore rupees.&lt;/p&gt;</description>
  <pubDate>Fri, 16 Aug 2026 09:00:00 +0000</pubDate>
</item>
<item>
  <title>सरकार ने राहत योजना की घोषणा की</title>
  <link>https://example.org/story-two</link>
  <description>नई दिल्ली, 16 अगस्त सरकार ने शुक्रवार को राहत योजना की घोषणा की।</description>
  <pubDate>Fri, 16 Aug 2026 10:00:00 +0000</pubDate>
</item>
</channel></rss>
"""

RSS = _RSS_TEXT.encode("utf-8")


class TestRegistryFile:
    def test_the_registry_loads(self) -> None:
        assert len(load_registry()) >= 20

    def test_every_entry_has_a_publisher_and_class(self) -> None:
        for definition in load_registry():
            assert definition.publisher
            assert definition.source_class in {"factchecker", "news", "official"}

    def test_urls_are_unique(self) -> None:
        urls = [definition.url for definition in load_registry()]

        assert len(set(urls)) == len(urls)

    def test_wire_carrying_outlets_are_deliberately_included(self) -> None:
        """Origin clustering needs real duplicates to collapse.

        Subscribing to outlets that reprint the same wire is a feed-selection
        decision, not synthetic data, and the M26 gate depends on it.
        """
        news = [d for d in load_registry() if d.source_class == "news"]

        assert len(news) >= 15, "too few news outlets for syndication to appear"

    def test_fact_checkers_are_present_and_marked(self) -> None:
        """Only these can produce Tier C evidence; news is corroboration material."""
        checkers = [d for d in load_registry() if d.is_factchecker]

        assert len(checkers) >= 4

    def test_only_official_bodies_may_settle_an_attribution(self) -> None:
        for definition in load_registry():
            if definition.allowed_for_primary_check:
                assert definition.source_class == "official"

    def test_domains_are_derived_not_declared(self) -> None:
        registry = {d.publisher: d.domain for d in load_registry()}

        assert registry["Alt News"] == "www.altnews.in"


class TestTriggerAuthentication:
    def test_a_matching_secret_authenticates(self) -> None:
        assert authenticate_trigger("shared-secret", "shared-secret")

    def test_a_wrong_secret_is_refused(self) -> None:
        assert not authenticate_trigger("wrong", "shared-secret")

    def test_a_missing_supplied_secret_is_refused(self) -> None:
        assert not authenticate_trigger(None, "shared-secret")

    def test_an_unconfigured_deployment_cannot_be_triggered_by_anyone(self) -> None:
        """Denying rather than allowing: the endpoint is reachable from the internet."""
        assert not authenticate_trigger("anything", None)
        assert not authenticate_trigger(None, None)
        assert not authenticate_trigger("", "")


class TestBackoff:
    def test_no_failures_means_no_delay(self) -> None:
        assert backoff_for(0) == 0

    def test_delay_doubles_with_each_failure(self) -> None:
        assert backoff_for(2) == backoff_for(1) * 2
        assert backoff_for(3) == backoff_for(1) * 4

    def test_delay_is_capped(self) -> None:
        """A dead feed must not occupy a slot every tick, nor wait forever."""
        assert backoff_for(50) == BACKOFF_CEILING_SECONDS

    def test_a_feed_failing_again_backs_off_further(self) -> None:
        """The feed row keeps only its backoff; the next failure must double it."""
        assert failures_behind(0) == 0
        for failures in (1, 2, 3):
            assert failures_behind(backoff_for(failures)) == failures
        assert backoff_for(failures_behind(backoff_for(2)) + 1) == backoff_for(3)
        ceiling = failures_behind(BACKOFF_CEILING_SECONDS)
        assert backoff_for(ceiling + 1) == BACKOFF_CEILING_SECONDS


class TestSchedulingWindow:
    def test_triggers_seconds_apart_resolve_to_one_window(self) -> None:
        """This is what makes the idempotency lock work."""
        first = window_start(datetime(2026, 8, 16, 12, 3, 10, tzinfo=UTC))
        second = window_start(datetime(2026, 8, 16, 12, 3, 55, tzinfo=UTC))

        assert first == second

    def test_windows_advance(self) -> None:
        first = window_start(datetime(2026, 8, 16, 12, 3, tzinfo=UTC))
        later = window_start(datetime(2026, 8, 16, 12, 31, tzinfo=UTC))

        assert later > first

    def test_the_window_is_truncated_to_the_interval(self) -> None:
        window = window_start(datetime(2026, 8, 16, 12, 47, 33, tzinfo=UTC), minutes=15)

        assert window.minute == 45
        assert window.second == 0


class TestFeedParsing:
    def test_items_are_read(self) -> None:
        items = parse_feed(RSS, publisher="Example")

        assert len(items) == 2
        assert items[0].title.startswith("Government announces")

    def test_tracking_parameters_are_stripped_from_item_links(self) -> None:
        items = parse_feed(RSS, publisher="Example")

        assert "utm_source" not in items[0].canonical_url

    def test_markup_is_removed_from_summaries(self) -> None:
        items = parse_feed(RSS, publisher="Example")

        assert "<p>" not in items[0].excerpt
        assert "five hundred crore" in items[0].excerpt

    def test_publication_dates_are_parsed(self) -> None:
        items = parse_feed(RSS, publisher="Example")

        assert items[0].published_at is not None
        assert items[0].published_at.year == 2026

    def test_language_is_detected_per_item(self) -> None:
        items = parse_feed(RSS, publisher="Example")

        assert items[0].language == "en"
        assert items[1].language == "hi"

    def test_content_hash_is_over_content_not_url(self) -> None:
        """The same story republished at a new URL is recognised as already seen."""
        first = parse_feed(RSS, publisher="Example")[0]
        moved = parse_feed(RSS.replace(b"story-one", b"story-one-v2"), publisher="Example")[0]

        assert first.canonical_url != moved.canonical_url
        assert first.content_hash == moved.content_hash

    def test_a_malformed_feed_yields_nothing_rather_than_raising(self) -> None:
        """A feed we refuse to parse is a publisher we silently stop hearing from,
        so parsing is lenient — but garbage still produces no items, not bad ones."""
        assert parse_feed(b"<html><body>not a feed</body></html>", publisher="X") == ()

    def test_entries_without_a_link_or_title_are_skipped(self) -> None:
        partial = b"""<?xml version="1.0"?><rss version="2.0"><channel>
        <item><title>No link here</title></item>
        <item><link>https://example.org/no-title</link></item>
        </channel></rss>"""

        assert parse_feed(partial, publisher="X") == ()
