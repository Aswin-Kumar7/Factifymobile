"""Live web-search evidence — the open-web path (M28+).

Every other resolver works over sources proposed elsewhere: the pre-ingested corpus, a
fact-check record, a URL the user handed us. This one is the deliberate exception the
base Protocol names — it reaches the open web to find pages bearing on a claim no local
source covers. It does so through a **search API** (Tavily or Exa), not a crawler of its
own, so there is no impersonation, no bot-detection evasion, and no scraping a site that
did not offer an endpoint.

What it does **not** change is how a verdict is reached. The search API only *finds*
candidate pages. The same passage reasoner that reads the corpus reads these, and a
citation still requires a verbatim quote located in the returned text: the model reads
and quotes, it does not decide. A page the reasoner cannot quote produces no evidence,
exactly as everywhere else. This is the one line that separates Facify from a
search-and-summarise tool — those let a confident model write the answer from the same
pages; here the answer is the citations, and the model is only a reader.

Tier D, corroboration: a page found by search is corroboration-grade, never decisive on
its own. Several independent origins saying the same thing is what makes it count — the
corroboration rule doing its job, and precisely the discipline a summariser skips.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import EvidenceKind, Method, Tier
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    insufficient,
    locate_excerpt,
)
from app.sources.reasoning import REASONER_VERSION, PassageReasoner, split_passages

logger = logging.getLogger("facify.sources.websearch")

NAME = "web_search"
VERSION = "2026.09.1"
PROVIDER = "web_search"

# Enough results for corroboration across independent origins, few enough that reading
# them all fits the per-request budget — each is a metered reasoning call.
_MAX_RESULTS = 5


class WebSearchResolver:
    """Finds open-web pages for a claim and reads them for support or contradiction."""

    name = NAME
    version = VERSION
    # Empty, like the corpus: this resolver does not restrict itself to a domain
    # allowlist. It reaches the web through a search provider, and the reasoner gates
    # every citation regardless of where the page came from.
    allowed_domains: frozenset[str] = frozenset()

    tier = Tier.D
    kind = EvidenceKind.CORROBORATION
    method = Method.SEARCH_SNIPPET

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        reasoner: PassageReasoner | None,
        provider: str,
        endpoint: str,
        api_key: str,
        max_results: int = _MAX_RESULTS,
    ) -> None:
        self._fetcher = fetcher
        self._reasoner = reasoner
        self._provider = provider
        self._endpoint = endpoint
        self._api_key = api_key
        self._max_results = max_results
        # url -> the provider's result row, kept from the search call so snapshot and
        # relate need no second fetch — the search API already returned the content.
        self._pages: dict[str, dict[str, Any]] = {}

    @property
    def reads_sources(self) -> bool:
        """Whether this resolver may spend model calls reading pages."""
        return self._reasoner is not None

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        rows = await self._search(claim.text)

        shortlist: list[SourceCandidate] = []
        for row in rows:
            url = row.get("url")
            if not url or not (row.get("content") or "").strip():
                continue
            self._pages[url] = row
            shortlist.append(
                SourceCandidate(
                    url=url,
                    publisher=row.get("publisher"),
                    title=row.get("title"),
                    published_at=row.get("published_at"),
                    proposed_by=f"web_search:{self._provider}",
                    prior_score=float(row.get("score") or 0.0),
                )
            )

        event(
            logger,
            "web-search candidates",
            module="sources.websearch",
            outcome="ok",
            provider=PROVIDER,
            candidates=len(shortlist),
        )
        return shortlist[: self._max_results]

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        """Build the snapshot from what the search API returned.

        No second fetch: the provider already returned the page's content, and reading
        that is what the reasoner judges. The content hash is over that text, so a
        citation points at the exact bytes that were read.
        """
        page = self._pages.get(candidate.url)
        if page is None:
            return None
        text = (page.get("content") or "").strip()
        if not text:
            return None

        return SourceSnapshot(
            id=f"web:{hashlib.sha256(candidate.url.encode()).hexdigest()[:16]}",
            url=candidate.url,
            final_url=candidate.url,
            content_hash=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
            fetched_at=datetime.now(UTC),
            text=text,
            title=page.get("title"),
            publisher=page.get("publisher"),
            published_at=page.get("published_at"),
        )

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Read the page and say what it does to the claim — the reasoner, verbatim.

        The same reading path the corpus uses: the model judges whole passages and
        returns a relation with a verbatim quote, the quote is located in the text it
        came from, and a quote that cannot be located discards the judgement. There is
        no lexical fallback here — a web page reached this far only because a reasoner
        was configured, and a fabricated lexical match from an arbitrary web result is
        exactly the noise this path must not add.
        """
        if self._reasoner is None:
            return insufficient(NAME, VERSION, "no reasoner is configured for web search")

        passages = split_passages(snapshot.text)
        if not passages:
            return insufficient(NAME, VERSION, "the page returned no readable passages")

        outcome = await self._reasoner.judge(claim.text, passages)
        if not outcome.succeeded:
            return insufficient(NAME, VERSION, f"reasoning unavailable: {outcome.reason}")

        best = outcome.best()
        if best is None:
            return insufficient(
                NAME, VERSION, f"read {outcome.passages_read} passages; none addresses this claim"
            )

        _, anchor = locate_excerpt(snapshot.text, best.quote)
        if not anchor:
            return insufficient(
                NAME, VERSION, "the quoted passage could not be located in the returned text"
            )

        return SourceRelation(
            relation=best.relation,
            validator=f"{NAME}+reasoner",
            validator_version=f"{VERSION}/{REASONER_VERSION}",
            excerpt=best.quote,
            anchor=anchor,
            metric=f"passage_entailment: {best.reason}"[:200],
            value=best.relevance,
            threshold=0.0,
        )

    # ---------------------------------------------------------------- providers

    async def _search(self, query: str) -> list[dict[str, Any]]:
        """Normalised results from whichever provider is configured.

        Each row is ``{url, title, content, published_at, publisher, score}``. A
        transport or parse failure yields no rows — a search that could not run is an
        absence of evidence, never an error that fails the whole verification.
        """
        try:
            if self._provider == "exa":
                return await self._search_exa(query)
            return await self._search_tavily(query)
        except Exception:
            logger.debug("web search failed; returning no candidates", exc_info=True)
            return []

    async def _search_tavily(self, query: str) -> list[dict[str, Any]]:
        result = await self._fetcher.post_json(
            self._endpoint,
            {
                "query": query,
                "max_results": self._max_results,
                "search_depth": "basic",
                "include_raw_content": False,
            },
            provider=PROVIDER,
            headers={"authorization": f"Bearer {self._api_key}"},
        )
        if not isinstance(result, FetchResult):
            return []
        data = json.loads(result.text)
        return [
            {
                "url": row.get("url"),
                "title": row.get("title"),
                "content": row.get("content") or "",
                "published_at": _parse_date(row.get("published_date")),
                "publisher": _publisher_of(row.get("url")),
                "score": row.get("score"),
            }
            for row in data.get("results", [])
        ]

    async def _search_exa(self, query: str) -> list[dict[str, Any]]:
        result = await self._fetcher.post_json(
            self._endpoint,
            {
                "query": query,
                "numResults": self._max_results,
                "contents": {"text": {"maxCharacters": 1200}},
            },
            provider=PROVIDER,
            headers={"x-api-key": self._api_key},
        )
        if not isinstance(result, FetchResult):
            return []
        data = json.loads(result.text)
        return [
            {
                "url": row.get("url"),
                "title": row.get("title"),
                "content": row.get("text") or "",
                "published_at": _parse_date(row.get("publishedDate")),
                "publisher": _publisher_of(row.get("url")),
                "score": row.get("score"),
            }
            for row in data.get("results", [])
        ]


def _publisher_of(url: str | None) -> str | None:
    """The site as a publisher name — the registrable host, minus a leading www."""
    if not url:
        return None
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
