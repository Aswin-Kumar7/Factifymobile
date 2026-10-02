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

import asyncio
import hashlib
import json
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

from app.domain.claim import Claim
from app.domain.enums import EvidenceKind, Method, Relation, Tier
from app.domain.evidence import OUT_OF_CONTEXT, SHARED_REVIEW
from app.embeddings.image import cosine
from app.embeddings.text import TextEmbedder
from app.governor.governor import Governor, ProviderUnavailable, Skip, SkipReason
from app.observability.logging import event
from app.security.fetcher import FetchFailure, FetchResult, SecureFetcher
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    insufficient,
    keyword_overlap,
)
from app.sources.reasoning import PassageReasoner

logger = logging.getLogger("factify.factcheck")

NAME = "factcheck"
VERSION = "2026.10.03.1"
PROVIDER = "factcheck"

# A fact-check must be about *this* claim before its rating means anything. Below
# this, the publisher adjudicated something else that happens to share vocabulary,
# and citing it would attribute a verdict its author never gave.
#
# This is the *lexical* gate, kept only as the fallback when no embedder is available.
# It is too strict for real matching on its own: a fact-checker writes "Coronavirus is
# a result of 5G" where the claim says "5G networks cause the coronavirus" — the same
# assertion, 0.20 word overlap. The primary gate is semantic (see `_SEMANTIC_GATE`).
MIN_CLAIM_OVERLAP = 0.55

# The semantic gate: cosine between the claim and the adjudicated claim, in the shared
# embedding space. High enough that a paraphrase of the same claim passes and a
# different claim about the same subject ("Bill Gates funds vaccines" vs "Bill Gates
# created the virus") does not. Tuned against real fact-check pairs.
_SEMANTIC_GATE = 0.62

# Above this, the adjudication is plainly about the same claim and is taken as it
# stands. Between the gate and here it is only a *candidate*, and the reader confirms.
#
# Measured cosines, this embedder, real pairs. Same claim: microchips 0.90, 5G 0.86,
# bleach 0.75, cow urine 0.69. Different claim, same subject: "Chandrayaan sent footage
# of Earth" against "Chandrayaan landed near the south pole" 0.63, "Bill Gates makes
# $200bn from vaccines" against "Bill Gates created the virus" 0.59. The bands overlap —
# 0.69 is a real match and 0.63 is not — so no single threshold separates them, because
# an embedding carries the subject far more than the predicate. A number cannot tell
# "landed on the Moon" from "sent footage of Earth"; reading them can.
# Raised from 0.82 after a live false positive. Snopes rated False the claim that
# "Trump's October 2025 ceasefire deal was the *exact deal* brokered by Biden", and
# that rating landed on the true statement "Israel and Hamas agreed a ceasefire in
# January 2025" — same subject, same vocabulary, different claim, and a similarity
# above 0.82, so the read that would have caught it was skipped as unnecessary. At
# 0.95 only a near-verbatim restatement skips the read, which is the case the shortcut
# was for: the same rumour reposted in the same words.
_CONFIDENT_MATCH = 0.95

# A loose lexical prefilter for the candidate shortlist only — wide enough that a
# paraphrase reaches the semantic gate in `relate`, which is where relevance is
# actually decided. API results are already ranked by the provider and skip this.
_CANDIDATE_PREFILTER = 0.15

# A record of ours this close to the claim is taken as the fact-check of it, and the
# API is not asked. Below this, the API is asked as well: sharing a few words - "Govt",
# "5000", "women" - is a different fake about the same subject, not this claim, and
# four such records once stopped the API being asked for "Rs 5000 a month to every
# woman" at all (2026-09-27). Half the claim's significant words is the bar.
_LOCAL_MATCH = 0.5

# A stored fact-check this close in meaning to the claim is shortlisted even when it
# shares few of its words: "Centre giving laptops to all students" and "free laptop
# scheme for every student" are one fake, and word overlap alone can miss it - more so
# across languages. Shortlisting only: whether it is about this claim is still decided
# in `relate`, by the stricter `_SEMANTIC_GATE` and the reader. Retrieve, then verify,
# as the strongest systems at SemEval-2025's multilingual fact-checked-claim retrieval
# task did.
_SEMANTIC_CANDIDATE = 0.55

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
    "असत्य",
    "गुमराह",
    # The other ten languages' words for false, fake and misleading, as their
    # fact-checkers write them in a rating: only the English and Hindi ones were
    # read, and a Tamil or Bengali site's rating in its own script was ignored.
    "মিথ্যা",
    "অসত্য",
    "ভুয়ো",
    "ভুয়া",
    "বিভ্রান্তিকর",
    "खोटा",
    "खोटी",
    "खोटे",
    "दिशाभूल",
    "తప్పు",
    "నకిలీ",
    "అబద్ధం",
    "தவறு",
    "தவறான",
    "போலி",
    "பொய்",
    "ખોટું",
    "ખોટો",
    "ખોટી",
    "નકલી",
    "ભ્રામક",
    "ಸುಳ್ಳು",
    "ನಕಲಿ",
    "ತಪ್ಪು",
    "ମିଥ୍ୟା",
    "ଭ୍ରାମକ",
    "തെറ്റ്",
    "വ്യാജം",
    "ਝੂਠ",
    "ਫਰਜ਼ੀ",
    "ਗਲਤ",
    "جھوٹ",
    "غلط",
    "جعلی",
    "گمراہ کن",
}

_TRUE_RATINGS = {"true", "correct", "accurate", "verified", "mostly true", "सही", "सच"}

# Ratings that say the claim's words, picture or video are genuine and shown out of
# context: neither true nor false, and never support. Newschecker's "Did Benjamin
# Netanyahu Say 'America Deserved 9/11'? No, Clipped Video Goes Viral" carried its
# rating in "clipped", which nothing read, and the clip it debunked came back TRUE
# (2026-10-02). Read only when no false or true rating is named: a headline that says
# both "clipped" and "fake" is a debunk of a fake.
#
# Not "old video": in a headline it as often debunks an event that never happened
# ("old video shared as a dam burst in ...") as it misdates one that did, and which
# is for the reader of the page to say. "Needs context" is left out too: some
# fact-checkers give it while they are still checking.
_CONTEXT_RATINGS = {
    "missing context",
    "out of context",
    "lacks context",
    "clipped",
    "cropped",
}


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
        # Before the true ratings: "out of context" is no rating of true.
        if any(token in normalised for token in _CONTEXT_RATINGS):
            return Relation.CONTEXTUALIZES
        if any(token in normalised for token in _TRUE_RATINGS):
            return Relation.SUPPORTS
        return None


@dataclass(frozen=True, slots=True)
class SharedReview:
    """The rating on a fact-check the person shared, read from the page's own markup."""

    record: FactCheckRecord
    # On the IFCN or EFCSN list of verified fact-checkers now, not only formerly.
    certified: bool


# The id of the claim a shared fact-check examines, as a claim of the case.
SHARED_CLAIM_ID = "cl_reviewed"

# When the person shared a fact-check: its rating of the claim it examines, for this
# check (set in `app/api/verify.py`). Someone who shares a BOOM check of a viral video
# is asking whether the video is what the post said, and BOOM has answered that; each
# finding in the article, checked on its own, mostly came back Unconfirmed
# (2026-09-28). The claim is answered by the fact-check's rating, and other
# fact-checkers' ratings of the same claim are asked for beside it.
current_shared_review: ContextVar[SharedReview | None] = ContextVar(
    "current_shared_review", default=None
)


def shared_review_for(claim: Claim) -> SharedReview | None:
    """The shared fact-check's rating, when this claim is the one it examines."""
    shared = current_shared_review.get()
    return shared if shared is not None and claim.id == SHARED_CLAIM_ID else None


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

    # A headline that names no rating of true or false, and says the material was
    # clipped: "No, Clipped Video Goes Viral". Never one that says it was tampered
    # with as well - a morphed and cropped picture is no genuine one.
    if _TAMPERED.search(lowered) is None:
        for rating in sorted(_CONTEXT_RATINGS, key=len, reverse=True):
            if _mentions(lowered, rating):
                return rating

    return None


_TAMPERED = re.compile(
    r"\b(?:morphed|doctored|photoshopped|deep ?fake|ai[- ]generated|digitally|edited|"
    r"manipulated|fabricated|altered)\b"
)


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
        governor: Governor | Any | None = None,
        api_available: bool = False,
        fetcher: SecureFetcher | None = None,
        endpoint: str = "",
        api_key: str = "",
        embedder: TextEmbedder | None = None,
        reasoner: PassageReasoner | None = None,
        keeper: Any | None = None,
    ) -> None:
        self._records = records
        self._governor = governor
        # Keeps each fact-check the API points at (app/knowledge/factchecks.py), so
        # the next check of the claim finds it here and never asks the API.
        self._keeper = keeper
        # Judges whether an adjudication is about *this* claim by meaning rather than
        # shared words. Without it, relevance falls back to lexical overlap, which
        # rejects most real paraphrased fact-checks.
        self._embedder = embedder
        # Reads a borderline adjudication to confirm it is about this claim. Optional:
        # without it the embedding gate decides alone, which is looser, not stricter.
        self._reasoner = reasoner
        # The API path is live only when it has everywhere to go: a fetcher, an
        # endpoint and a key. Missing any of them, it stays on the local records.
        self._api_available = api_available and bool(fetcher and endpoint and api_key)
        self._fetcher = fetcher
        self._endpoint = endpoint
        self._api_key = api_key
        # Adjudications fetched live this run, keyed by their URL, so `snapshot` and
        # `relate` can find a record the API produced without persisting it first.
        self._api_cache: dict[str, FactCheckRecord] = {}
        # Each stored fact-check's claim, embedded once (`_by_meaning`).
        self._vectors: dict[str, tuple[float, ...]] = {}

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        """Shortlist adjudications that might be about this claim.

        The local records are searched first and unconditionally. They cost nothing,
        and a hit here means the external call never needs to happen — which is the
        cache-before-provider rule applied to the cheapest evidence class.

        The claim a shared fact-check examines has that fact-check first, and the API
        is asked even so: what other fact-checkers rated the same claim is the
        cross-check on the one the person shared.
        """
        shared = shared_review_for(claim)
        if shared is None:
            return await self._candidates(claim)
        record = shared.record
        first = SourceCandidate(
            url=record.url,
            publisher=record.publisher,
            title=record.claim_text,
            published_at=record.published_at,
            proposed_by="shared_fact_check",
            prior_score=1.0,
        )
        try:
            others = await self._candidates(claim, cross_check=True)
        except ProviderUnavailable as unavailable:
            # The shared check still answers; only the cross-check is missing.
            event(
                logger,
                "shared fact-check not cross-checked",
                module="sources.factcheck",
                outcome="skipped",
                failure_reason=unavailable.reason.value,
            )
            others = []
        return [first, *(c for c in others if c.url != record.url)][:5]

    async def _candidates(
        self, claim: Claim, *, cross_check: bool = False
    ) -> list[SourceCandidate]:
        shortlist = [
            SourceCandidate(
                url=record.url,
                publisher=record.publisher,
                title=record.claim_text,
                published_at=record.published_at,
                proposed_by="local_factcheck_corpus",
                prior_score=_overlap(claim, record.claim_text),
            )
            for record in self._records
        ]
        close = await self._by_meaning(claim)
        shortlist = [
            c
            for c in shortlist
            if c.prior_score >= _CANDIDATE_PREFILTER or close.get(c.url, 0.0) >= _SEMANTIC_CANDIDATE
        ]
        shortlist.sort(key=lambda c: -max(c.prior_score, close.get(c.url, 0.0)))

        # A close match of our own answers without the API. By shared words only: a
        # match by meaning is shortlisted, never trusted enough to skip the API.
        if not cross_check and shortlist and shortlist[0].prior_score >= _LOCAL_MATCH:
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
                    local_candidates=len(shortlist),
                )
                # Our own weaker matches are still read; they were found without it.
                if shortlist:
                    return shortlist[:5]
                # Raised, not returned empty. "We could not ask" and "nobody has
                # checked this" are different answers, and returning [] made them
                # identical: the run counted as complete, so an abstention caused by
                # an exhausted daily budget was written to the cache and served for
                # thirty days as though it were the finding.
                raise ProviderUnavailable(PROVIDER, outcome.reason)

            fetched = await self._query_api(claim)
            api_shortlist = [
                SourceCandidate(
                    url=record.url,
                    publisher=record.publisher,
                    title=record.claim_text,
                    published_at=record.published_at,
                    proposed_by="factcheck_api",
                    prior_score=_overlap(claim, record.claim_text),
                )
                for record in fetched
            ]
            # No lexical prefilter here: the provider already ranked these by
            # relevance to the query, and the semantic gate in `relate` is what decides
            # whether each is about this claim. Our own weaker matches join them, one
            # copy of each page.
            seen = {candidate.url for candidate in api_shortlist}
            merged = api_shortlist + [c for c in shortlist if c.url not in seen]
            merged.sort(key=lambda candidate: -candidate.prior_score)
            event(
                logger,
                "fact-check candidates from API",
                module="sources.factcheck",
                outcome="ok",
                provider=PROVIDER,
                candidates=len(api_shortlist),
                local_candidates=len(shortlist),
                api_consulted=True,
            )
            return merged[:5]

        return shortlist[:5]

    async def _query_api(self, claim: Claim) -> list[FactCheckRecord]:
        """Query the Google Fact Check Tools API and map its ClaimReviews to records.

        Language is deliberately not constrained: a Hindi claim is often adjudicated in
        English and vice versa, and the overlap gate filters relevance afterwards. A
        failed request raises `ProviderUnavailable`: the check is reported as skipped
        rather than as "no fact-check exists", and the result is not cached.
        """
        records = await self._query_one(claim.text)
        # And in English, for a claim made in another language: a Tamil forward's
        # fact-check is as likely to be in English. The English query failing is not
        # the check failing - the claim's own words were asked.
        if claim.english_text and claim.english_text.casefold() != claim.text.casefold():
            try:
                seen = {record.url for record in records}
                records += [
                    record
                    for record in await self._query_one(claim.english_text)
                    if record.url not in seen
                ]
            except ProviderUnavailable:
                logger.warning("fact-check API: the English query failed; own words kept")
        for record in records:
            self._api_cache[record.url] = record
        if self._keeper is not None and records:
            self._keeper.remember([record.url for record in records])
        return records

    async def _query_one(self, text: str) -> list[FactCheckRecord]:
        """One query to the API; raises `ProviderUnavailable` when it did not answer."""
        assert self._fetcher is not None
        query = urlencode({"query": text[:300], "pageSize": 10, "key": self._api_key})
        result = await self._fetcher.fetch(f"{self._endpoint}?{query}", provider=PROVIDER)
        # Once more when the connection itself failed: a dropped connection is not an
        # answer, and failing on it skips the fact-checks for the whole check
        # (seen 2026-09-28, RemoteProtocolError on the first try).
        if isinstance(result, FetchFailure) and result.kind == "transport":
            result = await self._fetcher.fetch(f"{self._endpoint}?{query}", provider=PROVIDER)
        # A request that failed is not an answer. It used to return no records, which
        # reads exactly like "nobody has fact-checked this": a revoked key, a 429 or
        # an outage produced a complete-looking run, and a complete run is cached.
        # Raised instead, the pipeline records the check as skipped and the result
        # is never cached. An empty list is kept for what it means: no fact-checks.
        if not isinstance(result, FetchResult) or not 200 <= result.status_code < 300:
            raise ProviderUnavailable(PROVIDER, SkipReason.PROVIDER_ERROR)

        try:
            payload = json.loads(result.text)
        except json.JSONDecodeError as error:
            raise ProviderUnavailable(PROVIDER, SkipReason.PROVIDER_ERROR) from error
        if not isinstance(payload, dict) or "error" in payload:
            raise ProviderUnavailable(PROVIDER, SkipReason.PROVIDER_ERROR)

        return [
            record
            for entry in payload.get("claims", [])
            if (record := self._to_record(entry)) is not None
        ]

    async def published_ratings(self, url: str) -> list[FactCheckRecord]:
        """A fact-checker's own ratings on one of its pages, from the fact-check index.

        For a shared fact-check that will not serve us its page: bangla.boomlive.in
        answers our honestly named fetcher with 403, and the text a reader service
        returns in its place carries no ClaimReview markup (2026-09-28). The
        fact-checker publishes the same ratings to the index, where its recent reviews
        are listed by site and this page's are picked out by address. One call; empty
        when the index cannot be asked or does not list the page.
        """
        host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
        if not host or not self._api_available or self._governor is None:
            return []
        if isinstance(await self._governor.try_acquire(PROVIDER), Skip):
            return []
        assert self._fetcher is not None
        query = urlencode(
            {
                "reviewPublisherSiteFilter": host,
                # The recent ones: unfiltered, the index lists a site's reviews by its
                # own ranking, and last week's page was not among BOOM Bangla's 100.
                "maxAgeDays": _SITE_REVIEW_DAYS,
                "pageSize": _SITE_REVIEWS,
                "key": self._api_key,
            }
        )
        result = await self._fetcher.fetch(f"{self._endpoint}?{query}", provider=PROVIDER)
        if not isinstance(result, FetchResult) or not 200 <= result.status_code < 300:
            return []
        try:
            payload = json.loads(result.text)
        except json.JSONDecodeError:
            return []
        entries = payload.get("claims", []) if isinstance(payload, dict) else []
        found: list[FactCheckRecord] = []
        for entry in entries:
            text = " ".join(str(entry.get("text") or "").split())
            for review in entry.get("claimReview") or []:
                if not text or _address(str(review.get("url") or "")) != _address(url):
                    continue
                publisher = review.get("publisher") or {}
                found.append(
                    FactCheckRecord(
                        claim_text=text,
                        normalized_text=text.lower(),
                        url=url,
                        rating=review.get("textualRating") or None,
                        publisher=publisher.get("name") or publisher.get("site") or None,
                        published_at=_parse_review_date(review.get("reviewDate")),
                        retrieved_at=datetime.now(UTC),
                    )
                )
        event(
            logger,
            "shared fact-check looked up in the index",
            module="sources.factcheck",
            outcome="ok" if found else "empty",
            provider=PROVIDER,
            listed=len(entries),
            found=len(found),
        )
        return found

    def add_records(self, records: list[FactCheckRecord]) -> None:
        """Fact-checks kept since boot, searched from the next check on."""
        known = {(r.url, r.normalized_text) for r in self._records}
        self._records = self._records + [
            r for r in records if (r.url, r.normalized_text) not in known
        ]

    def replace_records(self, records: list[FactCheckRecord]) -> None:
        """Every fact-check held, after an ingestion run added some."""
        self._records = list(records)

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
        """A record by URL: the shared fact-check's, the ingested corpus's, or one of
        this run's API results."""
        shared = current_shared_review.get()
        if shared is not None and shared.record.url == url:
            return shared.record
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
            # Of the page and the claim it rates. The claim's opening words were the
            # hash, and the evidence id takes its first sixteen characters: BOOM's and
            # PIB's checks of "Govt to pay Rs 5000 a month..." shared one id, and the
            # second fact-checker agreeing was dropped as a duplicate of the first.
            content_hash="sha256:"
            + hashlib.sha256(f"{record.url} {record.normalized_text}".encode()).hexdigest(),
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

        # The shared page's own rating of the claim its markup names: this claim, by
        # construction, so there is nothing to match.
        shared = shared_review_for(claim)
        if shared is not None and shared.record.url == record.url:
            verdict = record.verdict
            if verdict is None:
                return insufficient(
                    NAME, VERSION, f"rating {record.rating!r} is not one we interpret"
                )
            return SourceRelation(
                relation=verdict,
                validator=NAME,
                validator_version=VERSION,
                excerpt=f"{record.publisher or 'A fact-checker'} rated this {record.rating}: "
                f"{record.claim_text[:200]}",
                anchor={"char_start": 0, "char_end": min(len(record.claim_text), 200)},
                metric=SHARED_REVIEW,
                value=1.0,
                threshold=_CONFIDENT_MATCH,
            )

        score, metric, threshold = await self._relevance(claim, record.claim_text)
        if score < threshold:
            return insufficient(
                NAME, VERSION, f"adjudicates a different claim ({metric} {score:.2f})"
            )

        # A marginal match is read before it is believed. This caught a real error: an
        # AFP check of "Chandrayaan 3 sent footage of Earth" scored 0.63 against the
        # true claim "Chandrayaan 3 landed near the south pole", and its False rating
        # turned a true statement into DO_NOT_SHARE. One rating wrongly attributed is
        # the worst output this system has, so the borderline band pays for a read.
        if score < _CONFIDENT_MATCH and not await self._addresses(claim, record):
            return insufficient(
                NAME, VERSION, f"adjudicates a different claim on the same subject ({score:.2f})"
            )

        verdict = record.verdict
        if verdict is None:
            return insufficient(NAME, VERSION, f"rating {record.rating!r} is not one we interpret")

        if verdict is Relation.CONTEXTUALIZES:
            # Genuine, and shown out of context: marked so the source check and the
            # rules can tell it from other context (`rule.out_of_context`).
            metric = f"{OUT_OF_CONTEXT}: rated {record.rating!r} ({metric})"

        return SourceRelation(
            relation=verdict,
            validator=NAME,
            validator_version=VERSION,
            excerpt=f"{record.publisher or 'A fact-checker'} rated this {record.rating}: "
            f"{record.claim_text[:200]}",
            anchor={"char_start": 0, "char_end": min(len(record.claim_text), 200)},
            metric=metric,
            value=round(score, 4),
            threshold=threshold,
        )

    async def _addresses(self, claim: Claim, record: FactCheckRecord) -> bool:
        """Whether this adjudication is about *this* claim, read rather than scored.

        The question is equivalence, and it is put as one: would this check's verdict
        be a verdict on our claim? Asked instead through the passage reader — "does
        this adjudicated claim support ours?" — the answer came back yes for a Snopes
        check of whether Trump's ceasefire deal was "the exact deal" Biden brokered,
        because a claim about *whose* deal it was takes for granted that a deal
        happened, and so supports the claim that one did. That entailment carried a
        False rating onto a true statement. Support is not sameness, so it is no
        longer what is asked.

        Without a reader configured this returns True: the embedding gate is then the
        only judge available, and refusing everything would silently disable the
        strongest evidence class rather than degrade it.
        """
        if self._reasoner is None:
            return True

        verdict = await self._reasoner.same_claim(claim.reading_text, record.claim_text)
        # `None` is "could not ask", not "no". Falling back to the score alone keeps a
        # brief provider outage from dropping every published adjudication.
        return verdict is not False

    async def _by_meaning(self, claim: Claim) -> dict[str, float]:
        """Each stored fact-check's closeness in meaning to the claim, by its URL.

        The stored claims are embedded once and kept; the claim, in its self-contained
        English when it has one, once per check. Empty without an embedder.
        """
        if self._embedder is None or not self._records:
            return {}
        try:
            missing = [r for r in self._records if r.url not in self._vectors]
            if missing:
                result = await asyncio.to_thread(
                    self._embedder.embed, [r.claim_text for r in missing], language=None
                )
                for record, vector in zip(missing, result.vectors, strict=False):
                    self._vectors[record.url] = vector
            asked = await asyncio.to_thread(
                self._embedder.embed, [claim.search_text], language=None
            )
        except Exception:
            logger.debug("stored fact-checks not matched by meaning")
            return {}
        if not asked.vectors:
            return {}
        target = asked.vectors[0]
        return {url: cosine(target, vector) for url, vector in self._vectors.items()}

    async def _relevance(self, claim: Claim, adjudicated: str) -> tuple[float, str, float]:
        """How well an adjudicated claim matches this one — semantic, or lexical.

        Returns (score, metric, threshold). The semantic path embeds both claims and
        compares them by meaning, so "Coronavirus is a result of 5G" matches "5G
        networks cause the coronavirus" that lexical overlap scores at 0.20. Lexical
        overlap remains the fallback when no embedder is configured, and its stricter
        threshold reflects that it cannot see a paraphrase.
        """
        if self._embedder is not None:
            try:
                result = await asyncio.to_thread(
                    self._embedder.embed,
                    [claim.matching_text, adjudicated],
                    language="en" if claim.matching_text is not claim.text else claim.language,
                )
                if len(result.vectors) == 2:
                    similarity = cosine(result.vectors[0], result.vectors[1])
                    return similarity, "claim_similarity", _SEMANTIC_GATE
            except Exception:
                # A representation failure falls through to the lexical gate rather
                # than rejecting the claim outright.
                logger.debug("semantic relevance unavailable; falling back to overlap")

        return _overlap(claim, adjudicated), "claim_overlap", MIN_CLAIM_OVERLAP


# A fact-checker's recent reviews listed to find one page among: a few days of a
# busy site's output.
_SITE_REVIEWS = 100
_SITE_REVIEW_DAYS = 90


def _address(url: str) -> str:
    """A page's address without its scheme, "www.", query or trailing slash."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").casefold().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"


def _overlap(claim: Claim, reviewed: str) -> float:
    """Word overlap with a fact-check's claim, in the claim's words or its English."""
    own = keyword_overlap(claim.text, reviewed)
    if not claim.english_text:
        return own
    return max(own, keyword_overlap(claim.english_text, reviewed))
