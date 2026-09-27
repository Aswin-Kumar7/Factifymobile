"""The source reader (v5, 4.2): a cited passage in its article.

Held here: the quoted paragraph comes back with one neighbour either side and never
the whole article; a page that will not open, or no longer carries the quote, still
gives the quote and says why the rest is missing; page text is cleaned before it is
shown; and a source reopened is served without fetching the page again.
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from PIL import Image

from app.api.schemas import (
    ClaimResponse,
    EvidenceResponse,
    MatchBasisResponse,
    SourceAnchorResponse,
    StrengthResponse,
    VerifyResponse,
)
from app.security.fetcher import FetchFailure, FetchResult
from app.sources.reader import read_source

pytestmark = pytest.mark.unit

QUOTE = "The ministry said no such scheme has been announced."
URL = "https://www.thehindu.com/news/national/fact-check-scheme/article1.ece"


def _article(paragraphs: list[str], *, image: bool = True) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    picture = (
        "<meta property='og:image' content='https://www.thehindu.com/lead.jpg'>" if image else ""
    )
    return (
        "<html><head><title>No cash scheme for women, ministry says</title>"
        "<meta property='article:published_time' content='2026-09-24T08:00:00Z'>"
        f"{picture}</head><body><article><h1>No cash scheme for women, ministry says</h1>"
        f"{body}</article></body></html>"
    )


def _paragraph(n: int) -> str:
    return (
        f"Paragraph {n} of the report describes the viral message in some detail, with "
        "the claims it makes and the link it asks people to follow before it is removed."
    )


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1200, 800), (30, 90, 160)).save(out, "JPEG")
    return out.getvalue()


def _result(body: bytes, content_type: str, url: str = URL) -> FetchResult:
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        content_type=content_type,
        body=body,
        byte_count=len(body),
        fetched_at=datetime.now(UTC),
    )


class _Web:
    def __init__(self, html: str | None) -> None:
        self.html = html
        self.asked: list[str] = []

    async def fetch(self, url: str, *, provider: str = "web") -> FetchResult | FetchFailure:
        self.asked.append(url)
        if url.endswith(".jpg"):
            return _result(_jpeg(), "image/jpeg", url)
        if self.html is None:
            return FetchFailure(url=url, reason="request timed out", kind="timeout")
        return _result(self.html.encode(), "text/html")


def _read(web: _Web) -> Any:
    return asyncio.run(read_source(web, url=URL, quote=QUOTE, publisher="The Hindu"))


class TestTheReader:
    def test_the_quote_comes_back_with_its_neighbours_and_no_more(self) -> None:
        paragraphs = [_paragraph(n) for n in range(1, 9)]
        paragraphs[4] = (
            f"Asked about the message, officials were clear. {QUOTE} They urged caution."
        )
        view = _read(_Web(_article(paragraphs)))

        assert view.complete
        assert len(view.paragraphs) == 3  # the quote's paragraph and one either side
        assert view.paragraphs[1] == paragraphs[4]
        assert view.quote_paragraph == 1
        held = view.paragraphs[1][view.quote_start : view.quote_end]
        assert held.lower() == QUOTE.lower()
        assert view.headline == "No cash scheme for women, ministry says"
        assert view.read_minutes is not None and view.read_minutes >= 1
        assert view.image is not None  # the lead picture, shrunk for our own serving

    def test_a_page_that_will_not_open_still_gives_the_quote(self) -> None:
        view = _read(_Web(None))

        assert not view.complete
        assert view.paragraphs == (QUOTE,)
        assert view.limitations == ("the page could not be opened now",)

    def test_a_page_that_no_longer_carries_the_quote_says_so(self) -> None:
        view = _read(_Web(_article([_paragraph(n) for n in range(1, 4)])))

        assert not view.complete
        assert view.paragraphs == (QUOTE,)
        assert view.headline == "No cash scheme for women, ministry says"
        assert "no longer on the page" in view.limitations[0]

    def test_page_text_is_cleaned_before_it_is_shown(self) -> None:
        hidden = "Officials​ said: " + QUOTE
        view = _read(_Web(_article([_paragraph(1), hidden, _paragraph(3)])))

        assert "​" not in "".join(view.paragraphs)


# ---------------------------------------------------------------- the endpoint


def _stored(case_id: str) -> VerifyResponse:
    evidence = EvidenceResponse(
        id="4d7c1f6e-stored",
        tier="C",
        kind="fact_check",
        direction="contradicts",
        method="claim_review",
        finding="The ministry denied it.",
        citation_url=URL,
        snapshot_id="snap",
        source_excerpt=QUOTE,
        source_anchor=SourceAnchorResponse(paragraph_index=4),
        match_basis=MatchBasisResponse(metric="claim_similarity", value=0.86, threshold=0.62),
        match_quality="STRONG",
        publisher="The Hindu",
        credibility="HIGH",
    )
    claim = ClaimResponse(
        id="cl_1",
        text="Rs 5,000 a month for every woman.",
        claim_type="EVENT",
        status="CONTRADICTED",
        severity="HIGH",
        importance="HEADLINE",
        reason="r",
        rule_id="r",
        rule_version="v",
        strength=StrengthResponse(score=0.9, band="STRONG", version="v"),
        evidence=(evidence,),
        confidence=88,
    )
    return VerifyResponse(
        case_id=case_id,
        action="DO_NOT_SHARE",
        action_reason="r",
        rule_version="v",
        claims=(claim,),
        retrieved_at=datetime.now(UTC),
    )


class _Cases:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id

    async def get(self, case_id: Any) -> VerifyResponse | None:
        return _stored(self.case_id) if str(case_id) == self.case_id else None


class TestTheEndpoint:
    def _client(self, web: _Web) -> tuple[Any, str]:
        from fastapi.testclient import TestClient

        from app.main import create_app

        client = TestClient(create_app())
        case_id = str(uuid4())
        client.app.state.case_reader = _Cases(case_id)
        client.app.state.url_reader = web
        return client, case_id

    def test_a_cited_source_is_read_and_then_kept(self) -> None:
        paragraphs = [_paragraph(1), f"Officials were clear. {QUOTE}", _paragraph(3)]
        web = _Web(_article(paragraphs, image=False))
        client, case_id = self._client(web)

        first = client.get(f"/v1/cases/{case_id}/sources/4d7c1f6e-stored")
        assert first.status_code == 200
        body = first.json()
        assert body["complete"] is True
        assert body["domain"] == "thehindu.com"
        assert body["direction"] == "contradicts" and body["tier"] == "C"
        assert body["credibility"] == "HIGH"
        assert body["match_basis"]["value"] == 0.86
        assert body["quote"]["paragraph_index"] == 1

        again = client.get(f"/v1/cases/{case_id}/sources/4d7c1f6e-stored")
        assert again.json() == body
        assert web.asked.count(URL) == 1  # reopened without fetching the page again

    def test_a_fresh_results_source_is_found_by_its_page(self) -> None:
        client, case_id = self._client(_Web(_article([f"{QUOTE}"], image=False)))
        found = client.get(f"/v1/cases/{case_id}/sources/ev_fresh_id", params={"url": URL})
        assert found.status_code == 200

    def test_an_unknown_source_or_case_is_not_found(self) -> None:
        client, case_id = self._client(_Web(None))
        assert client.get(f"/v1/cases/{case_id}/sources/nope").status_code == 404
        assert client.get(f"/v1/cases/{uuid4()}/sources/nope").status_code == 404


class TestFallbacks:
    def test_a_page_that_refuses_us_is_read_through_the_licensed_extract(self) -> None:
        asked: list[str] = []

        async def vendor(url: str) -> str:
            asked.append(url)
            return f"# Headline\n\nBefore it.\n\nOfficials were clear. {QUOTE}\n\nAfter it."

        view = asyncio.run(
            read_source(_Web(None), url=URL, quote=QUOTE, publisher="The Hindu", vendor=vendor)
        )

        assert asked == [URL]
        assert view.complete
        assert QUOTE in view.paragraphs[view.quote_paragraph or 0]

    def test_the_stored_headline_is_kept_when_the_page_will_not_open(self) -> None:
        view = asyncio.run(
            read_source(_Web(None), url=URL, quote=QUOTE, headline="No cash scheme, says ministry")
        )
        assert not view.complete
        assert view.headline == "No cash scheme, says ministry"


def test_a_citation_carries_the_pages_own_date_not_our_fetch_time() -> None:
    from datetime import date, timedelta

    from app.orchestration.ledger import _published_on

    fetched = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
    assert _published_on(
        {"source_published_at": datetime(2024, 3, 1, tzinfo=UTC), "observed_at": fetched}
    ) == date(2024, 3, 1)
    # Stored before the fix: the "publication" date is the fetch, and is dropped.
    assert (
        _published_on(
            {"source_published_at": fetched + timedelta(seconds=2), "observed_at": fetched}
        )
        is None
    )
    assert _published_on({"source_published_at": None, "observed_at": fetched}) is None
