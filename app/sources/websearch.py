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

What a page *is* depends on who published it (`classify`). A page on a verified
fact-checker is a published adjudication — Tier C, the same class the fact-check API
returns, reached by another route — and one of them settles a claim. Everything else is
a credible publisher's reporting: Tier D corroboration, which decides only when several
independent publishers agree. That is the corroboration rule doing its job, and
precisely the discipline a search-and-summarise tool skips.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import ClaimType, EvidenceKind, Method, Tier
from app.extraction.web import extract
from app.governor.governor import ProviderUnavailable, Skip
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    insufficient,
    locate_excerpt,
)
from app.sources.credibility import SourceCredibility
from app.sources.reasoning import REASONER_VERSION, PassageReasoner, split_passages

logger = logging.getLogger("facify.sources.websearch")

NAME = "web_search"
VERSION = "2026.09.3"
PROVIDER = "web_search"

# How many credible sources to read. Each is a metered model call, and corroboration
# needs two independent origins — three reads leaves one spare for a page the reasoner
# finds irrelevant, without paying for five.
_MAX_RESULTS = 3

# Below this, what came back is a consent wall, a paywall stub or a block page rather
# than an article, and the vendor's extraction is worth trying. Above it, our own fetch
# already produced more text than the vendor's extract returns for the same page.
_MIN_ARTICLE_CHARS = 600

# How many results to *request* from the provider. Wider than what is read, because the
# credibility gate drops most open-web results — a query where four of five hits are
# blogs would otherwise leave a single credible source, too few to corroborate.
_SEARCH_COUNT = 10


class WebSearchResolver:
    """Finds open-web pages for a claim and reads them for support or contradiction."""

    name = NAME
    version = VERSION
    # Empty, like the corpus: this resolver does not restrict itself to a domain
    # allowlist. It reaches the web through a search provider, and the reasoner gates
    # every citation regardless of where the page came from.
    allowed_domains: frozenset[str] = frozenset()

    # Defaults for a page from a credible publisher that is not a fact-checker;
    # `classify` below says what any particular source produced.
    tier = Tier.D
    kind = EvidenceKind.CORROBORATION
    method = Method.PASSAGE_ENTAILMENT

    # The costliest producer in the pipeline — a search-API call plus a model read per
    # page — so the orchestrator consults it only for a claim the corpus and published
    # fact-checks have not already decided, and only for the most important claims.
    fallback = True

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        reasoner: PassageReasoner | None,
        provider: str,
        endpoint: str,
        api_key: str,
        credibility: SourceCredibility | None = None,
        governor: Any | None = None,
        max_results: int = _MAX_RESULTS,
    ) -> None:
        self._governor = governor
        self._fetcher = fetcher
        self._reasoner = reasoner
        self._provider = provider
        self._endpoint = endpoint
        self._api_key = api_key
        # Only credible publishers are read and cited from the open web. Junk is
        # dropped here, before it costs a reasoning call or contradicts a real source.
        self._credibility = credibility or SourceCredibility(frozenset())
        self._max_results = max_results
        # url -> the provider's result row, kept from the search call so snapshot and
        # relate need no second fetch — the search API already returned the content.
        self._pages: dict[str, dict[str, Any]] = {}

    @property
    def reads_sources(self) -> bool:
        """Whether this resolver may spend model calls reading pages."""
        return self._reasoner is not None

    def classify(self, snapshot: SourceSnapshot) -> tuple[Tier, EvidenceKind, Method]:
        """What class of finding a page from this publisher is.

        A page on a verified fact-checker is a published adjudication — the same thing
        the fact-check API returns, reached by another route — so it is Tier C, and
        one of them settles a claim. Everything else is a credible publisher's
        reporting that bears on the claim: Tier D corroboration.

        Both are `PASSAGE_ENTAILMENT` rather than `SEARCH_SNIPPET`: the page was
        fetched, read and quoted verbatim. A snippet nobody opened is what that other
        method names, and it is excluded from deciding anything for good reason.
        """
        source = snapshot.final_url or snapshot.url
        if self._credibility.is_fact_checker(source):
            return Tier.C, EvidenceKind.FACT_CHECK, Method.CLAIM_REVIEW
        return Tier.D, EvidenceKind.CORROBORATION, Method.PASSAGE_ENTAILMENT

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        # A media provenance claim is not searchable text, and must never be treated as
        # though it were.
        #
        # Its wording is ours, not a publisher's — "This image has been published
        # before, at a date and by a publisher that can be cited" — so searching it
        # retrieves pages *about how to cite images*. Live: an uploaded scam screenshot
        # came back SAFE_TO_SHARE, corroborated by two university library citation
        # guides and an NCBI print record, none of which had ever seen the image.
        #
        # Whether this image was published before is a question for reverse-image
        # search and C2PA provenance, which is what the media resolvers answer. A text
        # index cannot answer it, and must not appear to.
        if claim.claim_type is ClaimType.MEDIA:
            return []

        # Through the governor, like every other metered provider. This resolver was
        # written without one and spent a paid search quota that the configured caps
        # only appeared to protect: `FACIFY_WEBSEARCH__DAILY_CAP` was read into the
        # governor's provider table and never consulted, so nothing enforced it.
        #
        # Raised rather than returned empty, because the pipeline distinguishes "no
        # results" from "not asked": the second marks the run incomplete, and an
        # incomplete run is not written to the cache.
        if self._governor is not None:
            outcome = await self._governor.try_acquire(PROVIDER)
            if isinstance(outcome, Skip):
                event(
                    logger,
                    "web search not consulted",
                    module="sources.websearch",
                    outcome="skipped",
                    provider=PROVIDER,
                    failure_reason=outcome.reason.value,
                )
                raise ProviderUnavailable(PROVIDER, outcome.reason)

        rows = await self._search(claim.text)

        shortlist: list[SourceCandidate] = []
        dropped = 0
        dropped_hosts: list[str] = []
        for row in rows:
            url = row.get("url")
            if not url or not (row.get("content") or "").strip():
                continue
            # The credibility gate. An open-web page is read and cited only if its
            # publisher is one we would cite — otherwise a conspiracy blog's "SUPPORTS"
            # counts equally against a fact-checker's "CONTRADICTS", and the verdict
            # engine, seeing conflict, abstains. Dropping it here is source selection,
            # not a claim about the claim, and it never reaches the reasoner.
            if not self._credibility.is_credible(url):
                dropped += 1
                dropped_hosts.append(urlsplit(url).hostname or "")
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
            dropped_not_credible=dropped,
            # Named, not just counted. A count cannot tell a conspiracy blog the gate
            # was built to stop from a medical authority the allowlist is missing,
            # and those need opposite responses.
            dropped_hosts=sorted(set(dropped_hosts)),
        )
        return shortlist[: self._max_results]

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        """Read the page — ours first, the vendor's second, the snippet last.

        This used to say "no second fetch: the provider already returned the page's
        content". What it returned was a **search snippet**. Measured across every
        reader-based verdict this system had ever produced, the median cited quote was
        **209 characters** — a fragment with no surrounding text, which is what the
        reader was asked to judge a claim against. Both classes of misreading this
        module has been patched for are what a competent reader does with a fragment.

        So the ladder, cheapest and best first:

        1. **Fetch it ourselves.** Free, and richer than the vendor's extraction when it
           works — 9,841 characters against 6,597 on the same Wikipedia page. Measured
           over twenty credible hosts, fourteen answer us directly.
        2. **The search vendor's extract endpoint**, for the ones that do not. Five of
           those twenty refuse us at the edge, and they include Reuters, AP, NDTV and
           PIB — the sources we most want. The vendor holds that relationship and we
           pay them for it; that is the licensed route, and it is why the alternative
           (presenting ourselves as a browser to get past a block) is not on this
           ladder at all.
        3. **The snippet**, which is what we had before, and is better than nothing.
        4. Nothing, and the claim abstains — which for a page nobody can read is the
           honest answer rather than a gap to engineer around.

        Which rung produced the text is recorded in `extraction_route`, so a snippet is
        never presented as though it were an article.
        """
        page = self._pages.get(candidate.url)
        if page is None:
            return None

        text, route, final_url = await self._read(candidate.url)
        if not text:
            text = (page.get("content") or "").strip()
            route, final_url = "web.snippet", candidate.url
        if not text:
            return None

        return SourceSnapshot(
            id=f"web:{hashlib.sha256(candidate.url.encode()).hexdigest()[:16]}",
            url=candidate.url,
            final_url=final_url or candidate.url,
            content_hash=f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
            fetched_at=datetime.now(UTC),
            text=text,
            title=page.get("title"),
            publisher=page.get("publisher"),
            published_at=page.get("published_at"),
            extraction_route=route,
        )

    async def _read(self, url: str) -> tuple[str, str, str]:
        """Rungs one and two of the ladder. Returns (text, route, final_url)."""
        try:
            fetched = await self._fetcher.fetch(url, provider=PROVIDER)
        except Exception:  # a page we cannot read is ordinary, not exceptional
            fetched = None

        if isinstance(fetched, FetchResult):
            article = extract(fetched.text, url=url)
            body = (article.body or "").strip()
            if len(body) >= _MIN_ARTICLE_CHARS:
                self._read_event("web.fetched", url, len(body))
                return body, "web.fetched", fetched.final_url or url

        body = await self._vendor_extract(url)
        if body:
            route = f"web.{self._provider}_extract"
            self._read_event(route, url, len(body))
            return body, route, url

        self._read_event("web.unreadable", url, 0)
        return "", "", url

    def _read_event(self, route: str, url: str, chars: int) -> None:
        """Which rung read this page, and how much it yielded.

        Logged because a ladder whose rungs are invisible cannot be tuned or trusted:
        the share of pages falling through to the vendor is what the extract spend
        tracks, and a sudden rise in `web.unreadable` is a publisher change, not a
        change in the claims.
        """
        event(
            logger,
            "source read",
            module="sources.websearch",
            outcome="ok" if chars else "degraded",
            provider=PROVIDER,
            route=route,
            chars=chars,
            host=urlsplit(url).hostname or "",
            # The whole URL when nothing was read, the host otherwise. A PIB page
            # came back unreadable while pib.gov.in served 70 KB of HTML to a direct
            # request moments later — so the host alone said the publisher was fine
            # and left no way to find the page that was not.
            url=url if not chars else None,
        )

    async def _vendor_extract(self, url: str) -> str:
        """Ask the search provider for the text of one page we could not read.

        Only for the minority that refuse us, so the cost is a fraction of a request
        rather than one per source. Exa returns page text with its search results
        already, so there is nothing to ask for.
        """
        if self._provider != "tavily" or not self._api_key:
            return ""

        result = await self._fetcher.post_json(
            "https://api.tavily.com/extract",
            {"urls": [url], "extract_depth": "basic"},
            provider=PROVIDER,
            headers={"authorization": f"Bearer {self._api_key}"},
        )
        if not isinstance(result, FetchResult):
            return ""
        try:
            payload = json.loads(result.text)
        except json.JSONDecodeError:
            return ""
        for row in payload.get("results", []):
            body = (row.get("raw_content") or "").strip()
            if body:
                return body
        return ""

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

        outcome = await self._reasoner.judge(
            claim.text, passages, title=snapshot.title, language=claim.language
        )
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
                "max_results": _SEARCH_COUNT,
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
                "numResults": _SEARCH_COUNT,
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
