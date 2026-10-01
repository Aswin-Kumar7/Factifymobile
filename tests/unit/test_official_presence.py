"""A company's own list of locations, read for a claim that it opened one somewhere.

Held here: only the brand's own site is taken for it; the list is found from a search
result for one location; locations kept as script data are read; a place missing from
a list of at least five contradicts the claim, at no more than 60% confidence, and in
words that say why; a place (or its country) on the list, a page with too few
locations, or a claim about anything else contradicts nothing; and a source that
reports the opening makes it a disagreement, not a verdict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain import ClaimStatus, Direction, EvidenceKind, Tier
from app.security.fetcher import FetchResult
from app.sources.official_presence import (
    OfficialPresenceCheck,
    indexed_locations,
    list_pages,
    locations,
    might_apply,
    official_domain,
)
from app.verdict import decide
from app.verdict.engine import OFFICIAL_ABSENCE_CAP, OFFICIAL_ABSENCE_RULE
from app.verdict.explain import explain
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit

_PARTNERS = (
    '<script>window.__NUXT__={partners:[{slug:"toronto",address:{city:"Toronto, ON",'
    'country:"Canada"}},{slug:"dubai",address:{city:"Dubai",country:"United Arab Emirates"}},'
    '{slug:"singapore",address:{city:"Singapore",country:"Singapore"}},'
    '{slug:"munich",address:{city:"Munich",country:"Germany"}},'
    '{slug:"tokyo",address:{city:"Tokyo",country:"Japan"}}]}</script>'
)

_BUGATTI = "Bugatti opens a new showroom at Chennai, Tamil Nadu, said to be its first in India."


def _page(url: str, markup: str) -> FetchResult:
    body = markup.encode()
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        content_type="text/html",
        body=body,
        byte_count=len(body),
        fetched_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


class _Reasoner:
    def __init__(self, answer: dict[str, Any] | None) -> None:
        self.answer = answer
        self.asked = 0

    async def presence_claim(self, claim_text: str) -> dict[str, Any] | None:
        self.asked += 1
        return self.answer


_INDEXED = [
    {"url": "https://newsroom.bugatti.com/en/press-releases/first-showroom-in-singapore"},
    {"url": "https://www.bugatti.com/en/partners/toronto", "title": "BUGATTI Toronto | BUGATTI"},
    {"url": "https://www.bugatti.com/en/partners/riyadh", "title": "BUGATTI Riyadh | BUGATTI"},
    {"url": "https://www.bugatti.com/en/partners/manhattan", "title": "New York"},
    {"url": "https://www.bugatti.com/en/partners/uae", "title": "BUGATTI Dubai"},
]


class _Web:
    def __init__(
        self, pages: dict[str, str], place_rows: list[dict[str, Any]] | None = None
    ) -> None:
        self.pages = pages
        self.place_rows = place_rows
        self.searched: list[tuple[str, str]] = []

    async def search_site(self, query: str, domain: str) -> list[dict[str, Any]]:
        self.searched.append((query, domain))
        if len(self.searched) > 1:
            return self.place_rows or []
        return _INDEXED

    async def fetch_page(self, url: str) -> FetchResult | None:
        markup = self.pages.get(url)
        return None if markup is None else _page(url, markup)


def _bugatti(**overrides: Any) -> dict[str, Any]:
    return {
        "applies": True,
        "company": "Bugatti",
        "website": "bugatti.com",
        "place": "Chennai",
        "place_names": ["Chennai", "Madras"],
        "country": "India",
        **overrides,
    }


def _check(markup: str, answer: dict[str, Any] | None = None) -> tuple[Any, _Web, _Reasoner]:
    web = _Web({"https://www.bugatti.com/en/partners": markup})
    reasoner = _Reasoner(_bugatti() if answer is None else answer)
    return OfficialPresenceCheck(web=web, reasoner=reasoner), web, reasoner


def test_only_the_brands_own_site_is_taken_for_it() -> None:
    assert official_domain("Bugatti", "bugatti.com") == "bugatti.com"
    assert official_domain("Bugatti", "https://www.bugatti.com/en") == "bugatti.com"
    assert official_domain("Mercedes-Benz", "mercedes-benz.com") == "mercedes-benz.com"
    assert official_domain("Bugatti", "bugattichennai.in") is None
    assert official_domain("Bugatti", "carandbike.com") is None
    assert official_domain("Bugatti", "") is None


def test_the_list_is_found_above_one_location_and_press_releases_are_skipped() -> None:
    rows = [
        {"url": "https://newsroom.bugatti.com/en/press-releases/new-showroom-in-gstaad"},
        {"url": "https://www.bugatti.com/en/partners/toronto"},
        {"url": "https://dealer-site.example/bugatti/partners"},
    ]
    assert list_pages(rows, "bugatti.com") == [
        "https://www.bugatti.com/en/partners",
        "https://www.bugatti.com/en/partners/toronto",
    ]


def test_locations_kept_as_script_data_are_read() -> None:
    found = locations(_PARTNERS)
    assert "Toronto, ON" in found and "Canada" in found and "Tokyo" in found
    assert len(found) >= 5


def test_only_a_claim_about_a_location_is_asked_about() -> None:
    assert might_apply(_BUGATTI)
    assert might_apply("Apple opened its first store in Mumbai")
    assert not might_apply("The government will pay Rs 5,000 a month to every woman")


async def test_a_place_missing_from_the_list_contradicts_the_claim_with_limited_confidence() -> (
    None
):
    check, web, _ = _check(_PARTNERS)
    subject = claim(text=_BUGATTI)
    found = await check.check(subject)

    assert found is not None
    assert web.searched[0][1] == "bugatti.com"
    assert found.direction is Direction.CONTRADICTS
    assert found.citation_url == "https://www.bugatti.com/en/partners"
    assert found.finding == (
        "Bugatti's own website lists its locations, and none is in Chennai or anywhere in India."
    )

    decision = decide(subject, [found])
    assert decision.status is ClaimStatus.CONTRADICTED
    assert decision.rule_id == OFFICIAL_ABSENCE_RULE
    assert decision.confidence is not None and decision.confidence <= OFFICIAL_ABSENCE_CAP

    line = explain(decision.status, [found], decision.supporting_evidence_ids, language="en")
    assert line is not None
    assert line.startswith("Bugatti's own website lists its locations, and none is in Chennai")
    assert "bugatti.com" in line and "less certain" in line


async def test_a_listed_place_or_country_contradicts_nothing() -> None:
    check, _, _ = _check(_PARTNERS + '<a>{city:"Madras"}</a>')
    assert await check.check(claim(text=_BUGATTI)) is None

    check, _, _ = _check(_PARTNERS + '{city:"Mumbai",country:"India"}')
    assert await check.check(claim(text=_BUGATTI)) is None


async def test_a_page_with_too_few_locations_is_not_a_list() -> None:
    check, _, _ = _check('{city:"Toronto",country:"Canada"}')
    # Read as a page it is not a list; the index route then has no place search.
    assert await check.check(claim(text=_BUGATTI)) is None


def _indexed_check(place_rows: list[dict[str, Any]]) -> OfficialPresenceCheck:
    # The list page answers with a bot check, as bugatti.com does.
    web = _Web(
        {"https://www.bugatti.com/en/partners": "<title>Security Checkpoint</title>"}, place_rows
    )
    return OfficialPresenceCheck(web=web, reasoner=_Reasoner(_bugatti()))


def test_the_index_names_the_locations_under_one_list() -> None:
    url, names = indexed_locations(_INDEXED, "bugatti.com", "Bugatti")
    assert url == "https://www.bugatti.com/en/partners"
    assert names == ["Toronto", "Riyadh", "New York", "Dubai"]


async def test_an_unreadable_list_falls_back_to_the_index_and_a_search_for_the_place() -> None:
    home = [{"url": "https://www.bugatti.com", "title": "Official BUGATTI Website", "content": "x"}]
    found = await _indexed_check(home).check(claim(text=_BUGATTI))
    assert found is not None
    assert found.citation_url == "https://www.bugatti.com/en/partners"
    assert found.source_excerpt == "Locations on bugatti.com: Toronto, Riyadh, New York, Dubai"

    chennai = [{"url": "https://www.bugatti.com/en/partners/chennai", "title": "BUGATTI Chennai"}]
    assert await _indexed_check(chennai).check(claim(text=_BUGATTI)) is None

    india = [{"url": "https://newsroom.bugatti.com/x", "content": "Bugatti arrives in India"}]
    assert await _indexed_check(india).check(claim(text=_BUGATTI)) is None

    # A place search that came back empty may not have run: nothing is concluded.
    assert await _indexed_check([]).check(claim(text=_BUGATTI)) is None


async def test_no_official_site_or_another_kind_of_claim_contradicts_nothing() -> None:
    check, web, _ = _check(_PARTNERS, _bugatti(website="bugatti-india.in"))
    assert await check.check(claim(text=_BUGATTI)) is None
    assert web.searched == []

    check, _, reasoner = _check(_PARTNERS)
    assert await check.check(claim(text="Inflation fell to 3% in August")) is None
    assert reasoner.asked == 0


async def test_a_source_reporting_the_opening_makes_it_a_disagreement() -> None:
    check, _, _ = _check(_PARTNERS)
    subject = claim(text=_BUGATTI)
    found = await check.check(subject)
    assert found is not None
    reported = evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.SUPPORTS,
        tier=Tier.D,
        citation_url="https://news.example/bugatti-chennai",
    )
    decision = decide(subject, [found, reported])
    assert decision.status is ClaimStatus.UNVERIFIED
    assert decision.conflicting
