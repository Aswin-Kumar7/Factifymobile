"""Three places the service mistook a failure for an answer (2026-09-27 audit).

Held here: a fact-check lookup that failed is "could not check", never "nobody has
fact-checked this" - so it is skipped and not cached; the search provider's extract
and listing calls ask the budget like the search does; and a passage the reader
rates as barely relevant cannot decide a verdict.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain import EvidenceKind, MatchBasis, MatchQuality, Method, Tier
from app.domain.evidence import READING_RELEVANCE_THRESHOLD, derive_match_quality
from app.governor.governor import ProviderUnavailable, Skip, SkipReason
from app.security.fetcher import FetchFailure, FetchResult
from app.sources.factcheck import FactCheckResolver
from app.sources.websearch import WebSearchResolver
from tests.unit.factories import claim, evidence


def _result(status: int, body: str) -> FetchResult:
    now = datetime.now(UTC)
    return FetchResult(
        url="https://factchecktools.example/v1alpha1/claims:search",
        final_url="https://factchecktools.example/v1alpha1/claims:search",
        status_code=status,
        content_type="application/json",
        body=body.encode(),
        byte_count=len(body),
        fetched_at=now,
    )


class _Fetcher:
    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.posted: list[str] = []

    async def fetch(self, url: str, **_: object) -> object:
        return self.answer

    async def post_json(self, url: str, payload: object, **_: object) -> object:
        self.posted.append(url)
        return self.answer


class _Governor:
    def __init__(self, allow: bool) -> None:
        self.allow = allow

    async def try_acquire(self, provider: str) -> object:
        return (
            object() if self.allow else Skip(provider=provider, reason=SkipReason.CAPACITY_LIMITED)
        )


def _factcheck(answer: object) -> FactCheckResolver:
    return FactCheckResolver(
        records=[],
        governor=_Governor(allow=True),
        api_available=True,
        fetcher=_Fetcher(answer),  # type: ignore[arg-type]
        endpoint="https://factchecktools.example/v1alpha1/claims:search",
        api_key="k",
    )


class TestAFactCheckLookupThatFailed:
    @pytest.mark.parametrize(
        "answer",
        [
            _result(403, '{"error": {"code": 403, "message": "API key not valid"}}'),
            _result(429, '{"error": {"code": 429}}'),
            _result(200, "<html>not json</html>"),
            _result(200, '{"error": {"code": 500}}'),
            FetchFailure(url="https://x", reason="timeout", kind="timeout"),
        ],
    )
    async def test_is_skipped_not_taken_for_no_fact_checks(self, answer: object) -> None:
        with pytest.raises(ProviderUnavailable) as raised:
            await _factcheck(answer).candidates(claim(text="Rs 500 notes are being withdrawn"))
        assert raised.value.reason is SkipReason.PROVIDER_ERROR

    async def test_an_empty_answer_still_means_no_fact_checks(self) -> None:
        resolver = _factcheck(_result(200, "{}"))
        assert await resolver.candidates(claim(text="Rs 500 notes are being withdrawn")) == []


class TestTheSearchProvidersOtherCalls:
    def _resolver(self, allow: bool) -> tuple[WebSearchResolver, _Fetcher]:
        fetcher = _Fetcher(_result(200, '{"results": []}'))
        resolver = WebSearchResolver(
            fetcher=fetcher,  # type: ignore[arg-type]
            reasoner=None,
            provider="tavily",
            endpoint="https://api.tavily.example/search",
            api_key="k",
            governor=_Governor(allow=allow),
        )
        return resolver, fetcher

    async def test_extract_and_listing_ask_the_budget_first(self) -> None:
        resolver, fetcher = self._resolver(allow=False)
        assert await resolver._vendor_extract("https://www.thehindu.com/a/b") == ""
        assert await resolver.listing("https://www.thehindu.com/news/some-story") is None
        assert fetcher.posted == []

    async def test_within_the_budget_they_are_made(self) -> None:
        resolver, fetcher = self._resolver(allow=True)
        await resolver._vendor_extract("https://www.thehindu.com/a/b")
        await resolver.listing("https://www.thehindu.com/news/some-story")
        assert len(fetcher.posted) == 2


class TestABarelyRelevantPassage:
    @pytest.mark.parametrize(
        ("relevance", "quality"),
        [
            (0.1, MatchQuality.WEAK),
            (0.45, MatchQuality.WEAK),
            (0.6, MatchQuality.MODERATE),
            (0.8, MatchQuality.STRONG),
        ],
    )
    def test_is_weak_below_half(self, relevance: float, quality: MatchQuality) -> None:
        basis = MatchBasis(
            metric="passage_entailment: r", value=relevance, threshold=READING_RELEVANCE_THRESHOLD
        )
        assert derive_match_quality(basis) is quality

    def test_and_cannot_decide(self) -> None:
        item = evidence(
            kind=EvidenceKind.CORROBORATION,
            tier=Tier.D,
            method=Method.PASSAGE_ENTAILMENT,
            basis=MatchBasis(
                metric="passage_entailment: r", value=0.2, threshold=READING_RELEVANCE_THRESHOLD
            ),
        )
        assert item.is_decisive_capable is False
