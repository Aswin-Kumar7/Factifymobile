"""Fact-check retrieval (M27).

The strongest and cheapest evidence class: someone has already adjudicated this
claim, published a rating, and put their name on it. One hit here settles a claim
that would otherwise need corroboration across several origins.

Two sources feed it, and the second is what makes the gate achievable:

  1. The external fact-check API, when credentials and quota allow.
  2. **Records already retrieved live and persisted**, including the fact-checkers'
     own RSS feeds, which the knowledge plane already ingests. Alt News, BOOM,
     Factly, Vishvas and Newschecker publish their verdicts with claim text, rating
     and URL — that is ClaimReview-shaped data arriving over a channel that needs no
     key.

The second path is not a degraded mode. It is why a fact-checked claim still resolves
with a citation, publisher and rating when the API is unavailable, which is exactly
what happens on a free tier at the wrong moment.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from app.domain.claim import Claim
from app.domain.enums import EvidenceKind, Method, Relation, Tier
from app.governor.governor import Governor, Skip
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    insufficient,
    keyword_overlap,
)

logger = logging.getLogger("facify.factcheck")

NAME = "factcheck"
VERSION = "2026.08.1"
PROVIDER = "factcheck"

# A fact-check must be about *this* claim before its rating means anything. Below
# this, the publisher adjudicated something else that happens to share vocabulary,
# and citing it would attribute a verdict its author never gave.
MIN_CLAIM_OVERLAP = 0.55

# Ratings that constitute a contradiction. Deliberately explicit rather than
# "anything that isn't true": fact-checkers use a wide vocabulary and a rating we do
# not recognise must not be guessed at.
_FALSE_RATINGS = {
    "false",
    "fake",
    "incorrect",
    "misleading",
    "misattributed",
    "fabricated",
    "altered",
    "manipulated",
    "no evidence",
    "unsubstantiated",
    "hoax",
    "partly false",
    "partially false",
    "mostly false",
    "pants on fire",
    "झूठ",
    "फर्जी",
    "भ्रामक",
    "गलत",
}

_TRUE_RATINGS = {"true", "correct", "accurate", "verified", "mostly true", "सही", "सच"}


@dataclass(frozen=True, slots=True)
class FactCheckRecord:
    """One published adjudication."""

    claim_text: str
    normalized_text: str
    url: str
    rating: str | None
    publisher: str | None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None

    @property
    def verdict(self) -> Relation | None:
        """What this rating means for the claim, or None if unrecognised.

        An unrecognised rating produces nothing rather than a guess. A publisher's
        idiosyncratic label is not ours to interpret.
        """
        if not self.rating:
            return None

        normalised = self.rating.strip().lower()
        if any(token in normalised for token in _FALSE_RATINGS):
            return Relation.CONTRADICTS
        if any(token in normalised for token in _TRUE_RATINGS):
            return Relation.SUPPORTS
        return None


def _parse_review_date(value: object) -> datetime | None:
    """A ClaimReview's reviewDate (ISO-8601) as an aware datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_rating_from_title(title: str) -> str | None:
    """Read a verdict out of a fact-checker's headline.

    Indian fact-checkers write verdicts into their titles — "Fact Check: This video
    is NOT from Delhi", "फैक्ट चेक: यह दावा फर्जी है". Their RSS carries no
    ClaimReview markup, so the headline is where the rating actually lives.
    """
    lowered = title.lower()

    for rating in sorted(_FALSE_RATINGS | _TRUE_RATINGS, key=len, reverse=True):
        if _mentions(lowered, rating):
            return rating

    return None


def _mentions(text: str, rating: str) -> bool:
    """Whether a rating appears as its own word.

    ASCII ratings use word boundaries, so "false" does not fire inside a longer
    word. `\\b` is not meaningful around Devanagari — the neighbouring characters are
    themselves word characters — so those match as substrings instead.
    """
    if rating.isascii():
        return re.search(rf"\b{re.escape(rating)}\b", text) is not None
    return rating in text


class FactCheckResolver:
    """Resolves a claim against published adjudications."""

    name = NAME
    version = VERSION
    allowed_domains: frozenset[str] = frozenset()

    # A published adjudication. Tier C is the only tier a fact-checker's rating
    # can produce, and it is decisive on its own because someone put their name on it.
    tier = Tier.C
    kind = EvidenceKind.FACT_CHECK
    method = Method.CLAIM_REVIEW

    def __init__(
        self,
        *,
        records: list[FactCheckRecord],
        governor: Governor | None = None,
        api_available: bool = False,
        fetcher: SecureFetcher | None = None,
        endpoint: str = "",
        api_key: str = "",
    ) -> None:
        self._records = records
        self._governor = governor
        # The API path is live only when it has everywhere to go: a fetcher, an
        # endpoint and a key. Missing any of them, it stays on the local records.
        self._api_available = api_available and bool(fetcher and endpoint and api_key)
        self._fetcher = fetcher
        self._endpoint = endpoint
        self._api_key = api_key
        # Adjudications fetched live this run, keyed by their URL, so `snapshot` and
        # `relate` can find a record the API produced without persisting it first.
        self._api_cache: dict[str, FactCheckRecord] = {}

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        """Shortlist adjudications that might be about this claim.

        The local records are searched first and unconditionally. They cost nothing,
        and a hit here means the external call never needs to happen — which is the
        cache-before-provider rule applied to the cheapest evidence class.
        """
        shortlist = [
            SourceCandidate(
                url=record.url,
                publisher=record.publisher,
                title=record.claim_text,
                published_at=record.published_at,
                proposed_by="local_factcheck_corpus",
                prior_score=keyword_overlap(claim.text, record.claim_text),
            )
            for record in self._records
        ]
        shortlist = [c for c in shortlist if c.prior_score >= MIN_CLAIM_OVERLAP]
        shortlist.sort(key=lambda candidate: -candidate.prior_score)

        if shortlist:
            event(
                logger,
                "fact-check candidates from local corpus",
                module="sources.factcheck",
                outcome="ok",
                candidates=len(shortlist),
                api_consulted=False,
            )
            return shortlist[:5]

        if self._governor is not None and self._api_available:
            outcome = await self._governor.try_acquire(PROVIDER)
            if isinstance(outcome, Skip):
                event(
                    logger,
                    "fact-check API not consulted",
                    module="sources.factcheck",
                    outcome="skipped",
                    provider=PROVIDER,
                    failure_reason=outcome.reason.value,
                )
                return []

            fetched = await self._query_api(claim)
            api_shortlist = [
                SourceCandidate(
                    url=record.url,
                    publisher=record.publisher,
                    title=record.claim_text,
                    published_at=record.published_at,
                    proposed_by="factcheck_api",
                    prior_score=keyword_overlap(claim.text, record.claim_text),
                )
                for record in fetched
            ]
            api_shortlist = [c for c in api_shortlist if c.prior_score >= MIN_CLAIM_OVERLAP]
            api_shortlist.sort(key=lambda candidate: -candidate.prior_score)
            event(
                logger,
                "fact-check candidates from API",
                module="sources.factcheck",
                outcome="ok",
                provider=PROVIDER,
                candidates=len(api_shortlist),
                api_consulted=True,
            )
            return api_shortlist[:5]

        return []

    async def _query_api(self, claim: Claim) -> list[FactCheckRecord]:
        """Query the Google Fact Check Tools API and map its ClaimReviews to records.

        Language is deliberately not constrained: a Hindi claim is often adjudicated in
        English and vice versa, and the overlap gate filters relevance afterwards. A
        transport or parse failure yields no records rather than an exception — a
        missing fact-check is an absence of evidence, never an outage of the request.
        """
        assert self._fetcher is not None
        query = urlencode({"query": claim.text[:300], "pageSize": 10, "key": self._api_key})
        result = await self._fetcher.fetch(f"{self._endpoint}?{query}", provider=PROVIDER)
        if not isinstance(result, FetchResult):
            return []

        try:
            payload = json.loads(result.text)
        except json.JSONDecodeError:
            return []

        records = [
            record
            for entry in payload.get("claims", [])
            if (record := self._to_record(entry)) is not None
        ]
        for record in records:
            self._api_cache[record.url] = record
        return records

    @staticmethod
    def _to_record(entry: dict[str, Any]) -> FactCheckRecord | None:
        """One API claim + its first ClaimReview → a record, or None if unusable."""
        claim_text = str(entry.get("text") or "").strip()
        reviews = entry.get("claimReview") or []
        if not claim_text or not reviews:
            return None

        review = reviews[0]
        url = str(review.get("url") or "").strip()
        if not url:
            return None

        publisher = review.get("publisher") or {}
        return FactCheckRecord(
            claim_text=claim_text,
            normalized_text=claim_text.lower(),
            url=url,
            rating=(review.get("textualRating") or None),
            publisher=(publisher.get("name") or publisher.get("site") or None),
            published_at=_parse_review_date(review.get("reviewDate")),
            retrieved_at=datetime.now(UTC),
        )

    def _record_for(self, url: str) -> FactCheckRecord | None:
        """A record by URL, from either the ingested corpus or this run's API results."""
        return next((r for r in self._records if r.url == url), None) or self._api_cache.get(url)

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        """Fact-check records are already snapshotted at retrieval.

        The record was captured live with its timestamp when it was ingested, so
        there is a real fetch behind the citation even though this call does not
        make one.
        """
        record = self._record_for(candidate.url)
        if record is None:
            return None

        return SourceSnapshot(
            id=f"fc:{record.url}",
            url=record.url,
            final_url=record.url,
            content_hash=f"claim:{record.normalized_text[:64]}",
            fetched_at=record.retrieved_at or datetime.now(UTC),
            text=record.claim_text,
            title=record.claim_text,
            publisher=record.publisher,
            published_at=record.published_at,
        )

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Decide what this adjudication says about the claim."""
        record = self._record_for(snapshot.url)
        if record is None:
            return insufficient(NAME, VERSION, "record no longer available")

        overlap = keyword_overlap(claim.text, record.claim_text)
        if overlap < MIN_CLAIM_OVERLAP:
            return insufficient(
                NAME, VERSION, f"adjudicates a different claim (overlap {overlap:.2f})"
            )

        verdict = record.verdict
        if verdict is None:
            return insufficient(NAME, VERSION, f"rating {record.rating!r} is not one we interpret")

        return SourceRelation(
            relation=verdict,
            validator=NAME,
            validator_version=VERSION,
            excerpt=f"{record.publisher or 'A fact-checker'} rated this {record.rating}: "
            f"{record.claim_text[:200]}",
            anchor={"char_start": 0, "char_end": min(len(record.claim_text), 200)},
            metric="claim_overlap",
            value=round(overlap, 4),
            threshold=MIN_CLAIM_OVERLAP,
        )
