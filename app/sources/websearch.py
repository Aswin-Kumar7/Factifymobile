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
exactly as everywhere else. This is the one line that separates Factify from a
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

import asyncio
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import ClaimType, EvidenceKind, Method, Relation, Tier
from app.domain.evidence import NARROWER_SCOPE, READING_RELEVANCE_THRESHOLD
from app.extraction.web import extract, plain_text
from app.governor.governor import ProviderUnavailable, Skip, SkipReason
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.base import (
    NORMAL,
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    current_check,
    current_depth,
    insufficient,
    locate_excerpt,
)
from app.sources.credibility import SourceCredibility
from app.sources.reasoning import REASONER_VERSION, PassageReasoner, split_passages
from app.sources.verification import page_key

logger = logging.getLogger("factify.sources.websearch")

# The claim itself, two of its own search questions, and one query asking for the
# fact-check. The questions find reporting of true events; the fact-check query finds
# debunks. Swapping one for the other traded true-claim coverage for scam coverage,
# measured on the accuracy suites, so both stay.
_MAX_QUERIES = 4

# How long a fetched page stays reusable. Long enough for one case's claims to share
# it, short enough that it is never a stale answer from an earlier check.
_READ_TTL_SECONDS = 90.0

NAME = "web_search"
VERSION = "2026.09.26.3"
PROVIDER = "web_search"

# How many credible sources to read. Each is a metered model call, and corroboration
# needs two independent origins — three reads leaves one spare for a page the reasoner
# finds irrelevant, without paying for five.
# How many candidates a claim may try. Raised from five because an unreadable page now
# costs a fetch and nothing else — no model call — so reaching further down the list
# buys more readable sources for the same model spend.
_MAX_RESULTS = 6

# Below this, what came back is a consent wall, a paywall stub or a block page rather
# than an article, and the vendor's extraction is worth trying. Above it, our own fetch
# already produced more text than the vendor's extract returns for the same page.
_MIN_ARTICLE_CHARS = 600

# How many results to *request* from the provider. Wider than what is read, because the
# credibility gate drops most open-web results — a query where four of five hits are
# blogs would otherwise leave a single credible source, too few to corroborate.
_SEARCH_COUNT = 10


class _SearchFailed(Exception):
    """One search call that did not return results: the provider refused or failed."""


# A page that presents itself as a fact-check, in its headline or its address.
_FACT_CHECK_WORDS = re.compile(
    r"fact[\s_-]?check|webqoof|\bfake\b|\bhoax|\bviral\b|\bmisleading\b|"
    r"फ़र्ज़ी|फर्जी|फेक|भ्रामक|वायरल|पड़ताल",
    re.IGNORECASE,
)


def _reads_as_a_fact_check(title: str | None, url: str) -> bool:
    return bool(_FACT_CHECK_WORDS.search(f"{title or ''} {url}"))


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
        keeper: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        self._governor = governor
        # The pages this claim was cited against before (app/knowledge/memory.py).
        self._memory = memory
        # Keeps a fact-checker's page this search read (app/knowledge/factchecks.py).
        self._keeper = keeper
        self._fetcher = fetcher
        self._reasoner = reasoner
        self._provider = provider
        self._endpoint = endpoint
        self._api_key = api_key
        # Only credible publishers are read and cited from the open web. Junk is
        # dropped here, before it costs a reasoning call or contradicts a real source.
        self._credibility = credibility or SourceCredibility(frozenset())
        # The code's version and the list's: either changing changes what a check
        # finds, and this is what the verdict cache is keyed on.
        self.version = f"{VERSION}+{self._credibility.fingerprint}"
        self._max_results = max_results
        # url -> the provider's result row, kept from the search call so snapshot and
        # relate need no second fetch — the search API already returned the content.
        # Per check, never shared: a search row or a page read for one person's
        # check is invisible to every other. See `current_check`.
        self._pages_by_check: dict[str, dict[str, dict[str, Any]]] = {}
        # url -> (when it was read, what the ladder returned). See `_read`.
        self._reads_by_check: dict[str, dict[str, tuple[float, tuple[str, str, str]]]] = {}

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

    @property
    def _pages(self) -> dict[str, dict[str, Any]]:
        """This check's search rows."""
        return self._pages_by_check.setdefault(current_check.get(), {})

    @property
    def _reads(self) -> dict[str, tuple[float, tuple[str, str, str]]]:
        """This check's page reads."""
        return self._reads_by_check.setdefault(current_check.get(), {})

    @_reads.setter
    def _reads(self, value: dict[str, tuple[float, tuple[str, str, str]]]) -> None:
        self._reads_by_check[current_check.get()] = value

    def end_check(self, check_id: str) -> None:
        """Forget everything this check searched and read.

        Both stores used to be shared by every check the server ran: pages read for
        one person's check were served to another's for ninety seconds, and search
        rows were never dropped at all, so the dictionary grew for the life of the
        process.
        """
        self._pages_by_check.pop(check_id, None)
        self._reads_by_check.pop(check_id, None)

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
        # only appeared to protect: `FACTIFY_WEBSEARCH__DAILY_CAP` was read into the
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

        rows = await self._queries(claim)

        shortlist: list[SourceCandidate] = []
        dropped = 0
        dropped_hosts: list[str] = []
        seen: set[str] = set()
        for row in rows:
            url = row.get("url")
            if not url or not (row.get("content") or "").strip():
                continue
            # One read per page. Two queries returned www.politifact.com and
            # politifact.com for the same article, and both were read — a model call
            # spent on a page already in hand, merged away afterwards anyway.
            key = page_key(url)
            if key in seen:
                continue
            seen.add(key)
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
        # A deep check reads further down the list; a normal one keeps its own limit.
        depth = current_depth.get()
        limit = self._max_results if depth is NORMAL else depth.pages

        # Which pages get the read slots. Search rank alone gave them to whatever the
        # provider ranked first: on "CJP threatens 'Jantar Mantar 2.0' if CEC Gyanesh
        # Kumar does not resign" — a story PTI, The Hindu and the Times of India all
        # carried that day — two of six slots went to Wikipedia and a Nagaland
        # regional paper while four candidates were never opened. The wires, the
        # national press, broadcasters, official bodies and fact-checkers are read
        # first; search order is kept within each group, and the rest still fill any
        # slot left over.
        shortlist.sort(key=lambda c: 0 if self._credibility.is_prominent(c.url) else 1)
        shortlist = shortlist[:limit]

        # The pages this claim was cited against before are read again, first, beside
        # what search found now - so a source is not lost because today's search did
        # not return it. They add read slots rather than taking search's.
        for remembered in await self._remembered(claim, {page_key(c.url) for c in shortlist}):
            shortlist.insert(0, remembered)
        return shortlist

    async def _remembered(self, claim: Claim, seen: set[str]) -> list[SourceCandidate]:
        if self._memory is None or not claim.normalized_text:
            return []
        found = []
        remembered = await self._memory.pages(claim.normalized_text)
        for page in remembered:
            if page_key(page.url) in seen or not self._credibility.is_credible(page.url):
                continue
            seen.add(page_key(page.url))
            # `snapshot` reads pages it has a row for; a remembered page has no search
            # snippet, and never needs one.
            self._pages[page.url] = {
                "url": page.url,
                "title": page.title,
                "publisher": page.publisher,
            }
            found.append(
                SourceCandidate(
                    url=page.url,
                    publisher=page.publisher,
                    title=page.title,
                    proposed_by="memory",
                    prior_score=1.0,
                )
            )
        if remembered:
            event(
                logger,
                "remembered pages read again",
                module="sources.websearch",
                outcome="ok",
                provider=PROVIDER,
                remembered=len(remembered),
                # The rest were in today's search results already.
                added=len(found),
                hosts=sorted({urlsplit(c.url).hostname or "" for c in found}),
            )
        return found

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
        # A page nobody could read is skipped, not stood in for by its search snippet.
        #
        # The snippet rung was worth having when a context-only source was still
        # cited. It no longer is — a source must take a side to be cited, and a
        # snippet is capped at context because elision strips attribution — so every
        # snippet read cost a model call to produce something that was then thrown
        # away. Measured on one claim: three of five read slots went to science.org's
        # Cloudflare page, The Times' paywall and a PIB URL that refuses us, each read
        # from its snippet and each discarded.
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
        """Rungs one and two of the ladder, with a short memory. Returns (text, route,
        final_url).

        One article's claims retrieve overlapping sources, because they are claims
        about one story. Measured on an Economic Times commentary: seven claims, the
        three eligible ones searched, and fifteen page reads between them — with
        bbc.com fetched three times and Reuters, AFP and Brookings twice each. Every
        one of those was a fresh network round trip for a page already in hand.

        The judgement still runs per claim, and has to: what a passage says about one
        claim says nothing about another. Only the fetch and the extraction are
        shared, which is the part that was pure repetition.

        Deliberately short-lived and small. This resolver lives for the process, so an
        unbounded dictionary here would leak for the life of the service and serve a
        page from an hour ago as though it had just been read. Ninety seconds covers
        one case's claims and nothing else.
        """
        now = monotonic()
        cached = self._reads.get(url)
        if cached is not None and now - cached[0] < _READ_TTL_SECONDS:
            body, route, _ = cached[1]
            self._read_event(route, url, len(body), reused=True)
            return cached[1]

        result = await self._read_uncached(url)

        # Expired entries are dropped on the way past rather than on a timer; the
        # dictionary is small and only grows while a case is in flight.
        self._reads = {
            key: value for key, value in self._reads.items() if now - value[0] < _READ_TTL_SECONDS
        }
        self._reads[url] = (now, result)
        return result

    async def _read_uncached(self, url: str) -> tuple[str, str, str]:
        """The ladder itself."""
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

    def _read_event(self, route: str, url: str, chars: int, *, reused: bool = False) -> None:
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
            # Whether this page was already in hand from another claim of the same
            # case. Counting these is the only way to tell a genuine second source
            # from the same page fetched twice.
            reused=reused,
            url=url,
        )

    async def listing(self, url: str) -> tuple[str | None, str] | None:
        """The search engine's own title and summary for one page, or None.

        The last rung for a link nobody can read and whose page gave us nothing either:
        the headline and description the search index holds for that exact address.
        Found by searching the address's own words within its own site, then matching
        the address — a result for a different page is never used.
        """
        if self._provider != "tavily" or not self._api_key:
            return None
        parts = urlsplit(url)
        words = " ".join(
            w for w in re.split(r"[^A-Za-z0-9]+", parts.path) if len(w) > 2 and not w.isdigit()
        )
        if not parts.hostname or not words:
            return None
        if not await self._metered("listing"):
            return None
        result = await self._fetcher.post_json(
            self._endpoint,
            {
                "query": words[:300],
                "max_results": 5,
                "search_depth": "basic",
                "include_domains": [parts.hostname.removeprefix("www.")],
            },
            provider=PROVIDER,
            headers={"authorization": f"Bearer {self._api_key}"},
        )
        if not isinstance(result, FetchResult):
            return None
        try:
            rows = json.loads(result.text).get("results", [])
        except json.JSONDecodeError:
            return None
        wanted = page_key(url)
        for row in rows:
            content = " ".join(str(row.get("content") or "").split())
            if page_key(str(row.get("url") or "")) == wanted and len(content) >= 60:
                return row.get("title"), content
        return None

    async def _metered(self, call: str) -> bool:
        """Whether the budget allows one more paid call to the search provider.

        The search itself was always metered; the extract and listing calls, which
        spend the same provider's credits, were not - so the daily cap only appeared
        to bound what a day could cost. Past the cap they are skipped: the page stays
        unread, which is how any page we cannot read is treated.
        """
        if self._governor is None:
            return True
        outcome = await self._governor.try_acquire(PROVIDER)
        if isinstance(outcome, Skip):
            event(
                logger,
                "search provider call not made",
                module="sources.websearch",
                outcome="skipped",
                provider=PROVIDER,
                call=call,
                failure_reason=outcome.reason.value,
            )
            return False
        return True

    async def _vendor_extract(self, url: str) -> str:
        """Ask the search provider for the text of one page we could not read.

        Only for the minority that refuse us, so the cost is a fraction of a request
        rather than one per source. Exa returns page text with its search results
        already, so there is nothing to ask for.
        """
        if self._provider != "tavily" or not self._api_key:
            return ""
        if not await self._metered("extract"):
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
            # Markdown, not text: without this every quote from a page read this way
            # failed the verbatim check. See `plain_text`.
            body = plain_text(row.get("raw_content") or "")
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
            claim.reading_text,
            passages,
            title=snapshot.title,
            language=claim.language,
            claim_type=claim.claim_type.value,
            published=snapshot.published_on,
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
            # Logged, because it should not happen: the gate already found this quote.
            # When it did happen, it was two locating rules disagreeing, and it went
            # unnoticed for as long as it was silent.
            event(
                logger,
                "judged quote not located for citation",
                module="sources.websearch",
                outcome="degraded",
                provider=PROVIDER,
                url=snapshot.url,
                quote=best.quote[:160],
                level=logging.WARNING,
            )
            return insufficient(
                NAME, VERSION, "the quoted passage could not be located in the returned text"
            )

        relation = best.relation
        note = ""

        # A snippet cannot decide anything, and this is where that becomes true.
        #
        # `snapshot()` promises in as many words that "a snippet is never presented
        # as though it were an article" — but it only *recorded* the rung, and
        # nothing ever read it back. Live: science.org served us a Cloudflare
        # "Enable JavaScript and cookies to continue" page, the ladder fell to the
        # search snippet, and 123 characters of vendor summary produced a decisive
        # SUPPORTS for "drinking cow urine daily will cure a person of cancer" —
        # off an article headlined "Indian scientists decry 'infuriating' scheme to
        # study benefits of cow dung, urine, and milk".
        #
        # The snippet is why. A vendor summary is elided text, and elision is
        # exactly what strips attribution: the article reports what proponents
        # claim, the snippet states it flat. Rules 2 and 3 turn on who is speaking,
        # and a snippet has thrown that away before the reader ever sees it. So the
        # rung caps the relation rather than the reader trying to recover what is
        # no longer in the text.
        if snapshot.extraction_route == "web.snippet" and relation in (
            Relation.SUPPORTS,
            Relation.CONTRADICTS,
        ):
            relation = Relation.CONTEXTUALIZES
            note = " (from a search snippet; not read as the article)"

        # A fact-check settles a claim on its own, so it has to be a fact-check of
        # *this* claim - the gate the fact-check API's matches already pass.
        #
        # Found by search, fact-checks of a neighbouring claim came straight through.
        # On a BOOM debunk of a deepfake, Newschecker's and NewsMobile's checks that
        # "a reporter questioned the MEA spokesperson about snacking" is false were
        # counted against "he was trolled online over the snacking" - which happened -
        # and turned a correct fact-check MISLEADING. The reader had been told a
        # different claim is a different subject; asked as one narrow question,
        # "would that verdict be a verdict on this claim?", the answer is reliable.
        # The fact-check's headline names what it reviewed. `None` is "could not
        # ask", and keeps the finding, as the API path does.
        #
        # Nor only on fact-checkers' own sites: a newspaper's fact-check column is the
        # same kind of page. Live Hindustan's check that "Rs 5,000 cash on Independence
        # Day" was fake was counted against a forward promising Rs 5,000 a month to
        # every student - a different fake, from before.
        if relation is Relation.CONTRADICTS and (
            self._credibility.is_fact_checker(snapshot.final_url or snapshot.url)
            or _reads_as_a_fact_check(snapshot.title, snapshot.final_url or snapshot.url)
        ):
            reviewed = (snapshot.title or "").strip() or best.quote
            if await self._reasoner.same_claim(claim.reading_text, reviewed) is False:
                relation = Relation.CONTEXTUALIZES
                note = " (a fact-check of a different claim)"

        # A fact-checker's page that spoke to the claim: its ClaimReview is kept,
        # so the next check of it is answered from our own records.
        if (
            self._keeper is not None
            and relation in (Relation.SUPPORTS, Relation.CONTRADICTS)
            and self._credibility.is_fact_checker(snapshot.final_url or snapshot.url)
        ):
            self._keeper.remember([snapshot.final_url or snapshot.url])

        return SourceRelation(
            relation=relation,
            validator=f"{NAME}+reasoner",
            validator_version=f"{VERSION}/{REASONER_VERSION}",
            excerpt=best.quote,
            anchor=anchor,
            # A narrower version of the claim is recorded as such, so the rules can
            # tell it from other context (app/domain/evidence.py, NARROWER_SCOPE).
            metric=(
                f"{NARROWER_SCOPE if best.narrower else 'passage_entailment'}: {best.reason}{note}"
            )[:200],
            value=best.relevance,
            threshold=READING_RELEVANCE_THRESHOLD,
        )

    # ---------------------------------------------------------------- providers

    async def _queries(self, claim: Claim) -> list[dict[str, Any]]:
        """Search the claim, and the questions behind it, and merge what comes back.

        Searching the claim sentence alone retrieves its *topic*. For "Doctors
        confirm that drinking cow urine daily cures cancer" the index returned a
        WSJ video titled "Indian doctors use cow urine as medicine" and an NBC
        report — coverage of the practice, not one word on whether it works. The
        published medical answers exist; nothing asked for them. Meanwhile a reader
        saw the claim marked CONTRADICTED on a page about the Cancer Act 1939,
        because the reader was given whatever the topical search returned.

        Extraction has always produced `search_phrases` for exactly this and nothing
        ever read them — the field was written into the schema, filled by the model
        with no instruction saying what for, and dropped on the way to `Claim`.

        Capped at two extra queries. Each is a metered call, the governor charges
        one acquisition for the resolver rather than per query, and the marginal
        result falls off quickly.
        """

        def _comparable(value: str) -> str:
            return " ".join(value.split()).strip(" .!?।").casefold()

        claim_text = _comparable(claim.text)

        depth = current_depth.get()
        max_queries = _MAX_QUERIES if depth is NORMAL else depth.queries

        queries = [claim.text]
        # Translated as well as in its own words, for a claim not made in English:
        # the English press and the fact-checkers write about Tamil and Bengali
        # forwards too, in English.
        if claim.english_text and _comparable(claim.english_text) != claim_text:
            queries.append(claim.english_text)
        for raw in claim.search_phrases:
            phrase = " ".join(raw.split())
            # A phrase that merely restates the claim buys nothing and costs a call.
            # Compared without trailing punctuation, since the claim is a sentence
            # and a phrase is not: "the sky is green" and "The sky is green." are
            # the same query.
            if len(phrase) < 8 or _comparable(phrase) == claim_text:
                continue
            queries.append(phrase)
            if len(queries) >= max_queries - 1:
                break

        # Last, and always: a debunk is written about the claim, and says so.
        # Searching the claim alone returned the real government scholarship portals
        # for a scholarship scam PIB had called fake, and not one report of the
        # debunk; asking for the fact-check directly is what finds it.
        #
        # In English when the claim is not. A Hindi forward promising Rs 5,000 a month
        # to every student was searched only in Hindi, word for word, and found
        # pension schemes, a scholarship notice and an explainer on WhatsApp groups -
        # never a fact-checker, because PIB Fact Check, BOOM and Factly mostly
        # publish in English. The extractor's English phrase names the same claim.
        english = claim.english_text or next((p for p in queries[1:] if p.isascii()), None)
        subject = claim.text if claim.text.isascii() or not english else english
        queries.append(f"{subject} fact check")

        gathered = await asyncio.gather(
            *(self._search(query) for query in queries), return_exceptions=True
        )

        # Interleaved, not concatenated: one row from each query in turn.
        #
        # Concatenating looks equivalent and is not. Only `_MAX_RESULTS` pages are
        # ever read, so putting the claim query's whole page of results first means
        # the supplementary queries contribute nothing at all — measured, the fan-out
        # lifted 8 candidates to 16 and the three pages actually read did not change.
        # Round-robin gives each query a place at the front, which is the entire
        # point of asking more than one.
        #
        # Provider scores are comparable only within one response, so there is no
        # meaningful cross-query ranking to sort by instead. A URL two queries both
        # return keeps its earliest position, which is a mild vote for agreement.
        merged: dict[str, dict[str, Any]] = {}
        results = [r for r in gathered if not isinstance(r, BaseException)]

        # Every query failed: the search did not run, and that is not the same answer
        # as a search that found nothing. Returning no rows here reported a Tavily
        # plan limit (HTTP 432 on every query) as "no reliable source addresses this
        # claim", and the run looked complete, so that non-answer was cached for six
        # hours. Raised, the pipeline records the check as skipped instead: the reader
        # is told it could not be checked, and nothing is cached.
        if not results:
            event(
                logger,
                "web search failed",
                module="sources.websearch",
                outcome="error",
                provider=PROVIDER,
                queries=len(queries),
                failure_reason=type(gathered[0]).__name__ if gathered else "no queries",
                level=logging.WARNING,
            )
            raise ProviderUnavailable(PROVIDER, SkipReason.PROVIDER_ERROR)
        for rank in range(max((len(r) for r in results), default=0)):
            for result in results:
                if rank >= len(result):
                    continue
                row = result[rank]
                url = row.get("url")
                if isinstance(url, str) and url not in merged:
                    merged[url] = row

        event(
            logger,
            "web search fanned out",
            module="sources.websearch",
            outcome="ok",
            provider=PROVIDER,
            queries=len(queries),
            rows=len(merged),
        )
        return list(merged.values())

    async def _search(self, query: str) -> list[dict[str, Any]]:
        """Normalised results from whichever provider is configured.

        Each row is ``{url, title, content, published_at, publisher, score}``. A
        transport, provider or parse failure raises: one failed query is absorbed by
        `_queries`, which still has the others, and only all of them failing makes
        the search a skipped check rather than an empty one.
        """
        if self._provider == "exa":
            return await self._search_exa(query)
        return await self._search_tavily(query)

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
            raise _SearchFailed(result.reason)
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
            raise _SearchFailed(result.reason)
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
