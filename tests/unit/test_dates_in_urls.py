"""A page's publication date, read from the provider or from the page's own address.

The date is what tells an old story from a new one. A Politico page on the White House
state dinner for King Charles (April) was read as contradicting the menu of the one for
Xi Jinping (September); its address carried 2026/04/28 all along.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.sources.base import SourceSnapshot, date_in_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.politico.com/live-updates/2026/04/28/king-charles/menu", date(2026, 4, 28)),
        ("https://www.aljazeera.com/news/2026/9/25/iran-pitches", date(2026, 9, 25)),
        ("https://www.newindianexpress.com/india/2026/Sep/09/pm-modi", date(2026, 9, 9)),
        ("https://www.indiatoday.in/story/first-lady-2873946-2026-02-25", date(2026, 2, 25)),
        ("https://example.com/story_20260925.html", date(2026, 9, 25)),
    ],
)
def test_a_dated_address_gives_its_date(url: str, expected: date) -> None:
    assert date_in_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.thehindu.com/news/national/x/article71502791.ece",
        # A story id that contains "2028" is not a date.
        "https://www.ndtv.com/india-news/after-teens-gangrape-12028529",
        "https://example.com/2026/13/45/not-a-date",
        "https://example.com/2026/09/",
    ],
)
def test_an_undated_address_gives_none(url: str) -> None:
    assert date_in_url(url) is None


def test_the_provider_date_wins_over_the_address() -> None:
    snapshot = SourceSnapshot(
        id="s",
        url="https://example.com/2026/04/28/story",
        final_url="https://example.com/2026/04/28/story",
        content_hash="h",
        fetched_at=datetime(2026, 9, 26, tzinfo=UTC),
        published_at=datetime(2026, 4, 29, 3, 0, tzinfo=UTC),
    )

    assert snapshot.published_on == date(2026, 4, 29)


def test_without_a_provider_date_the_address_is_read() -> None:
    snapshot = SourceSnapshot(
        id="s",
        url="https://example.com/2026/04/28/story",
        final_url="https://example.com/2026/04/28/story",
        content_hash="h",
        fetched_at=datetime(2026, 9, 26, tzinfo=UTC),
    )

    assert snapshot.published_on == date(2026, 4, 28)
