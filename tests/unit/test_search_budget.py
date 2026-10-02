"""What a web search spends, and what it reads for it (work package E, phase 1).

Held here: every search query asks the budget for itself, so the caps count the
credits the provider bills; a second round reads pages the first did not; a page read
early in a background check is still in hand for its last claim; and waiting for the
budget is not counted against the twelve seconds an extract call is given.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.governor.governor import ProviderUnavailable, Skip, SkipReason
from app.knowledge.memory import RememberedPage
from app.orchestration.pipeline import BACKGROUND_CEILING_SECONDS
from app.security.fetcher import FetchResult
from app.sources import websearch
from app.sources.base import current_check, current_follow_up
from app.sources.credibility import SourceCredibility
from app.sources.verification import page_key
from app.sources.websearch import WebSearchResolver
from tests.unit.factories import claim

pytestmark = pytest.mark.unit

_CREDIBLE = SourceCredibility(
    frozenset({"thehindu.com", "ndtv.com", "reuters.com", "bbc.co.uk", "indiatoday.in"})
)


class _Governor:
    """Allows the first [allow] acquisitions (all of them when None), counting each;
    each one first waits [waits] seconds, as pacing under the per-minute ceiling does."""

    def __init__(self, allow: int | None = None, *, waits: float = 0.0) -> None:
        self.allow = allow
        self.waits = waits
        self.asked = 0

    async def try_acquire(self, provider: str) -> object:
        self.asked += 1
        if self.waits:
            await asyncio.sleep(self.waits)
        if self.allow is not None and self.asked > self.allow:
            return Skip(provider=provider, reason=SkipReason.CAPACITY_LIMITED)
        return object()


class _Memory:
    """Pages this claim was cited against before."""

    def __init__(self, *urls: str) -> None:
        self.urls = urls
        self.asked = 0

    async def pages(self, normalized_text: str, *, text: str = "") -> list[RememberedPage]:
        self.asked += 1
        return [RememberedPage(url=url, publisher=None, title="Earlier") for url in self.urls]


def _resolver(
    *, governor: Any = None, memory: Any = None, fetcher: Any = None
) -> WebSearchResolver:
    return WebSearchResolver(
        fetcher=fetcher,
        reasoner=None,
        provider="tavily",
        endpoint="https://api.tavily.example/search",
        api_key="k",
        credibility=_CREDIBLE,
        governor=governor,
        memory=memory,
    )


def _rows(*urls: str) -> list[dict[str, Any]]:
    return [{"url": url, "title": "A report", "content": "A snippet."} for url in urls]


def _claim(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "text": "The government will give every woman Rs 5,000 a month.",
        "normalized_text": "government every woman rs 5000 month",
        "search_phrases": ("Rs 5000 women scheme", "monthly payment for women India"),
    }
    fields.update(overrides)
    return claim(**fields)


def _searching(resolver: WebSearchResolver, answers: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Replaces the provider call; returns the queries sent, in order."""
    sent: list[str] = []

    async def _search(query: str, *, domains: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        sent.append(query)
        return answers.get(query, answers.get("*", []))

    resolver._search = _search  # type: ignore[method-assign]
    return sent


class TestEveryQueryIsMetered:
    """One acquisition per claim paid for the four or five queries the provider billed."""

    async def test_each_query_sent_asks_the_budget_once(self) -> None:
        governor = _Governor()
        resolver = _resolver(governor=governor)
        sent = _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})

        await resolver.candidates(_claim())

        # The claim, its two phrases and the fact-check query.
        assert len(sent) == 4
        assert governor.asked == len(sent)

    async def test_a_health_claim_pays_for_its_extra_query(self) -> None:
        governor = _Governor()
        resolver = _resolver(governor=governor)
        sent = _searching(resolver, {"*": _rows("https://www.ndtv.com/a")})

        await resolver.candidates(_claim(text="Turmeric milk cures diabetes.", search_phrases=()))

        assert any(query.endswith(" evidence") for query in sent)
        assert governor.asked == len(sent)

    async def test_a_query_past_the_budget_is_not_sent(self) -> None:
        governor = _Governor(allow=2)
        resolver = _resolver(governor=governor)
        sent = _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})

        found = await resolver.candidates(_claim())

        assert len(sent) == 2
        # What the paid queries found is still read.
        assert [candidate.url for candidate in found] == ["https://www.thehindu.com/a"]

    async def test_no_budget_at_all_is_a_search_not_asked(self) -> None:
        """Not "found nothing": the run is marked incomplete and is not cached."""
        resolver = _resolver(governor=_Governor(allow=0))
        sent = _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})

        with pytest.raises(ProviderUnavailable) as raised:
            await resolver.candidates(_claim())

        assert raised.value.reason is SkipReason.CAPACITY_LIMITED
        assert sent == []

    async def test_a_second_round_pays_for_each_of_its_queries(self) -> None:
        governor = _Governor()
        resolver = _resolver(governor=governor)
        sent = _searching(resolver, {"*": _rows("https://www.reuters.com/b")})

        token = current_follow_up.set(("women Rs 5000 scheme PIB", "Rs 5000 women fact check"))
        try:
            await resolver.candidates(_claim())
        finally:
            current_follow_up.reset(token)

        assert sent == ["women Rs 5000 scheme PIB", "Rs 5000 women fact check"]
        assert governor.asked == 2

    async def test_without_a_governor_every_query_is_sent(self) -> None:
        resolver = _resolver()
        sent = _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})

        await resolver.candidates(_claim())

        assert len(sent) == 4


class TestASecondRoundReadsNewPages:
    """The second round's four read slots went to pages the first had already read."""

    async def test_pages_judged_for_the_claim_and_remembered_pages_are_left_out(self) -> None:
        memory = _Memory("https://www.bbc.co.uk/earlier")
        resolver = _resolver(memory=memory)
        _searching(
            resolver,
            {"*": _rows("https://www.thehindu.com/a", "https://www.ndtv.com/b")},
        )
        target = _claim()
        check = current_check.set("case-1")
        try:
            first = await resolver.candidates(target)
            _searching(
                resolver,
                {
                    "*": _rows(
                        # The same pages, one written another way.
                        "http://thehindu.com/a/",
                        "https://www.ndtv.com/b",
                        "https://www.bbc.co.uk/earlier",
                        "https://www.reuters.com/new",
                    )
                },
            )
            token = current_follow_up.set(("a sharper query",))
            try:
                second = await resolver.candidates(target)
            finally:
                current_follow_up.reset(token)
        finally:
            current_check.reset(check)

        assert {candidate.url for candidate in first} == {
            "https://www.bbc.co.uk/earlier",
            "https://www.thehindu.com/a",
            "https://www.ndtv.com/b",
        }
        assert [candidate.url for candidate in second] == ["https://www.reuters.com/new"]
        # Memory is asked once, in the first round only.
        assert memory.asked == 1

    async def test_another_claim_may_still_read_the_same_page(self) -> None:
        """The judgement is per claim: what a page says of one says nothing of another."""
        resolver = _resolver()
        _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})
        check = current_check.set("case-2")
        try:
            await resolver.candidates(_claim(claim_id="cl_1"))
            token = current_follow_up.set(("a sharper query",))
            try:
                other = await resolver.candidates(_claim(claim_id="cl_2"))
            finally:
                current_follow_up.reset(token)
        finally:
            current_check.reset(check)

        assert [candidate.url for candidate in other] == ["https://www.thehindu.com/a"]

    async def test_another_check_may_still_read_the_same_page(self) -> None:
        resolver = _resolver()
        _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})
        check = current_check.set("case-2a")
        try:
            await resolver.candidates(_claim())
        finally:
            current_check.reset(check)

        check = current_check.set("case-2b")
        token = current_follow_up.set(("a sharper query",))
        try:
            again = await resolver.candidates(_claim())
        finally:
            current_follow_up.reset(token)
            current_check.reset(check)

        assert [candidate.url for candidate in again] == ["https://www.thehindu.com/a"]

    async def test_a_first_round_is_never_narrowed(self) -> None:
        """Only a second round leaves pages out; a later first round reads them all."""
        resolver = _resolver()
        _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})
        check = current_check.set("case-3")
        try:
            await resolver.candidates(_claim())
            again = await resolver.candidates(_claim())
        finally:
            current_check.reset(check)

        assert [candidate.url for candidate in again] == ["https://www.thehindu.com/a"]

    async def test_the_end_of_a_check_forgets_what_it_judged(self) -> None:
        resolver = _resolver()
        _searching(resolver, {"*": _rows("https://www.thehindu.com/a")})
        check = current_check.set("case-4")
        try:
            await resolver.candidates(_claim())
            assert resolver._judged["cl_1"] == {page_key("https://www.thehindu.com/a")}
        finally:
            current_check.reset(check)

        resolver.end_check("case-4")

        assert "case-4" not in resolver._judged_by_check


ARTICLE = (
    "The state government said on Monday that the monthly payment would reach every "
    "eligible woman head of family from the first of next month, and that the list of "
    "beneficiaries would be published by each district collector before then.\n"
) * 4


def _page(url: str, text: str, kind: str = "text/html") -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        content_type=kind,
        body=text.encode(),
        byte_count=len(text),
        fetched_at=datetime.now(UTC),
    )


class _Fetcher:
    """Our own fetch answers [html] (or refuses when None); the extract call answers
    [vendor] after [extract_takes] seconds."""

    def __init__(self, html: str | None, *, vendor: str = "", extract_takes: float = 0.0) -> None:
        self.html = html
        self.vendor = vendor
        self.extract_takes = extract_takes
        self.fetched = 0
        self.extracted = 0

    async def fetch(self, url: str, **_: object) -> object:
        self.fetched += 1
        if self.html is None:
            return SimpleNamespace(reason="blocked")
        return _page(url, self.html)

    async def post_json(self, url: str, body: object, **_: object) -> object:
        self.extracted += 1
        if self.extract_takes:
            await asyncio.sleep(self.extract_takes)
        payload = json.dumps({"results": [{"raw_content": self.vendor}]})
        return _page(url, payload, "application/json")


class TestAReadLastsTheCheck:
    """Ninety seconds was shorter than one background check: a page read for its
    first claims was fetched again for its last."""

    def test_the_memory_outlasts_the_longest_check(self) -> None:
        assert websearch._READ_TTL_SECONDS >= BACKGROUND_CEILING_SECONDS

    async def test_a_page_read_minutes_ago_in_the_same_check_is_not_fetched_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = [1000.0]
        monkeypatch.setattr(websearch, "monotonic", lambda: now[0])
        fetcher = _Fetcher(f"<html><body><article><p>{ARTICLE}</p></article></body></html>")
        resolver = _resolver(fetcher=fetcher)
        check = current_check.set("case-5")
        try:
            first = await resolver._read("https://www.thehindu.com/a")
            now[0] += 300.0
            again = await resolver._read("https://www.thehindu.com/a")
        finally:
            current_check.reset(check)

        assert first == again
        assert first[1] == "web.fetched"
        assert fetcher.fetched == 1

    async def test_but_not_past_its_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        now = [1000.0]
        monkeypatch.setattr(websearch, "monotonic", lambda: now[0])
        fetcher = _Fetcher(f"<html><body><article><p>{ARTICLE}</p></article></body></html>")
        resolver = _resolver(fetcher=fetcher)
        check = current_check.set("case-6")
        try:
            await resolver._read("https://www.thehindu.com/a")
            now[0] += websearch._READ_TTL_SECONDS + 1
            await resolver._read("https://www.thehindu.com/a")
        finally:
            current_check.reset(check)

        assert fetcher.fetched == 2

    async def test_nor_into_another_check(self) -> None:
        fetcher = _Fetcher(f"<html><body><article><p>{ARTICLE}</p></article></body></html>")
        resolver = _resolver(fetcher=fetcher)
        check = current_check.set("case-6a")
        try:
            await resolver._read("https://www.thehindu.com/a")
        finally:
            current_check.reset(check)
        resolver.end_check("case-6a")

        check = current_check.set("case-6b")
        try:
            await resolver._read("https://www.thehindu.com/a")
        finally:
            current_check.reset(check)

        assert fetcher.fetched == 2


class TestWaitingForTheBudgetIsNotTheExtractsTime:
    """The wait for room under the per-minute ceiling ran inside the twelve-second
    timeout, and the page went unread with its credit counted."""

    async def test_a_long_wait_for_the_budget_still_reads_the_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(websearch, "_EXTRACT_TIMEOUT_SECONDS", 0.1)
        governor = _Governor(waits=0.3)
        fetcher = _Fetcher(None, vendor=ARTICLE)
        resolver = _resolver(governor=governor, fetcher=fetcher)

        check = current_check.set("case-7")
        try:
            body, route, _ = await resolver._read("https://www.reuters.com/world/x")
        finally:
            current_check.reset(check)

        assert route == "web.tavily_extract"
        assert body.startswith("The state government said")
        assert governor.asked == 1

    async def test_the_call_itself_is_still_cut_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(websearch, "_EXTRACT_TIMEOUT_SECONDS", 0.1)
        governor = _Governor()
        fetcher = _Fetcher(None, vendor=ARTICLE, extract_takes=1.0)
        resolver = _resolver(governor=governor, fetcher=fetcher)

        check = current_check.set("case-8")
        try:
            body, route, _ = await resolver._read("https://www.reuters.com/world/y")
        finally:
            current_check.reset(check)

        assert (body, route) == ("", "")
        assert governor.asked == 1

    async def test_past_the_budget_no_extract_is_made(self) -> None:
        governor = _Governor(allow=0)
        fetcher = _Fetcher(None, vendor=ARTICLE)
        resolver = _resolver(governor=governor, fetcher=fetcher)

        check = current_check.set("case-9")
        try:
            body, _, _ = await resolver._read("https://www.reuters.com/world/z")
        finally:
            current_check.reset(check)

        assert body == ""
        assert fetcher.extracted == 0

    async def test_the_extract_other_readers_call_is_still_metered(self) -> None:
        """The link reader and the source reader call `_vendor_extract` directly."""
        governor = _Governor()
        fetcher = _Fetcher(None, vendor=ARTICLE)
        resolver = _resolver(governor=governor, fetcher=fetcher)

        body = await resolver._vendor_extract("https://www.reuters.com/world/w")

        assert body.startswith("The state government said")
        assert (governor.asked, fetcher.extracted) == (1, 1)

    async def test_without_an_extract_endpoint_nothing_is_metered(self) -> None:
        governor = _Governor()
        fetcher = _Fetcher(None, vendor=ARTICLE)
        resolver = WebSearchResolver(
            fetcher=fetcher,  # type: ignore[arg-type]
            reasoner=None,
            provider="exa",
            endpoint="https://api.exa.example/search",
            api_key="k",
            credibility=_CREDIBLE,
            governor=governor,
        )

        check = current_check.set("case-10")
        try:
            body, _, _ = await resolver._read("https://www.reuters.com/world/v")
        finally:
            current_check.reset(check)

        assert body == ""
        assert (governor.asked, fetcher.extracted) == (0, 0)
