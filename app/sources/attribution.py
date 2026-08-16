"""Attribution and quote checks (M29).

The two deterministic killers. Fabricated articles borrow authority they do not
have — *"as reported by Reuters"*, *"according to an RBI circular"*, *"a NASA study
found"* — because an invented claim with a real institution's name attached travels
much further than one without.

The check is almost embarrassingly simple: fetch the source that was cited and look
for the statement attributed to it. It costs one fetch and it dismantles a large
share of fabricated news on its own.

**One boundary matters and is easy to get wrong.** Finding nothing at the cited
source proves the *attribution* is false. It does not prove the underlying claim is
false — the fact might be true and merely miscredited. The relation returned says
"this source does not carry this", and the reason text says exactly that, because
overstating it would turn a narrow, certain finding into a broad, unsupported one.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import Relation
from app.extraction.web import extract
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher
from app.sources.base import (
    SourceCandidate,
    SourceRelation,
    SourceSnapshot,
    insufficient,
    keyword_overlap,
    locate_excerpt,
)

logger = logging.getLogger("facify.attribution")

ATTRIBUTION_NAME = "attribution"
QUOTE_NAME = "quote"
VERSION = "2026.08.1"

# How much of the claim must appear at the cited source before we accept that the
# source carries it. Set low deliberately: the question is whether the source says
# anything like this, and a strict threshold would manufacture false negatives
# against sources that reported the fact in their own words.
CARRIES_THRESHOLD = 0.6

# Below this, the source plainly does not carry the claim. Between the two the
# answer is genuinely unclear and produces INSUFFICIENT rather than a finding.
ABSENT_THRESHOLD = 0.25

# Attribution phrasings, in the forms Indian copy actually uses.
# Case-insensitive on the phrasing, because a sentence commonly begins with it —
# "According to Reuters" would otherwise never match. The institution name itself
# must still be capitalised, hence the scoped `(?-i:...)`: without it, IGNORECASE
# would let any lowercase word become a "cited source".
_ATTRIBUTION = re.compile(
    r"\b(?:according to|as reported by|reported by|cited by|said by|"
    r"in an? (?:statement|circular|report|study|notice|order) (?:by|from)|"
    r"(?:a|an)\s+\w+\s+(?:study|report|circular|statement)\s+(?:found|said|states))"
    r"\s+(?:the\s+)?((?-i:[A-Z])[\w&.\- ]{2,40})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CitedSource:
    """An authority a claim invokes, and the words that invoke it."""

    name: str
    phrase: str
    position: int


def find_cited_sources(text: str) -> tuple[CitedSource, ...]:
    """Extract the authorities a claim leans on.

    Deliberately conservative. A missed attribution costs one unrun check; a
    hallucinated one would send us to fetch a source the article never mentioned and
    then report that it "does not carry the claim" — a fabricated finding about a
    fabricated citation.
    """
    found: list[CitedSource] = []

    for match in _ATTRIBUTION.finditer(text):
        name = (match.group(1) or "").strip(" .,:;")
        if len(name) < 3:
            continue
        found.append(CitedSource(name=name, phrase=match.group(0).strip(), position=match.start()))

    return tuple(found)


class AttributionResolver:
    """Checks whether a cited source carries what was attributed to it."""

    name = ATTRIBUTION_NAME
    version = VERSION

    def __init__(
        self, *, fetcher: SecureFetcher, allowed_domains: frozenset[str] | None = None
    ) -> None:
        self._fetcher = fetcher
        # Empty means "only URLs the article itself cited". This resolver never
        # searches for a source; it follows one the document already named.
        self.allowed_domains = allowed_domains or frozenset()

    async def candidates(
        self, claim: Claim, *, outbound_links: tuple[str, ...] = ()
    ) -> list[SourceCandidate]:
        """The links the article itself offered as its authority.

        Only outbound links from the document are followed. Searching for a source
        that matches the named institution would let us pick the page that best
        supports our own conclusion, which is the opposite of checking.
        """
        cited = find_cited_sources(claim.text)
        if not cited:
            return []

        return [
            SourceCandidate(
                url=link,
                publisher=urlsplit(link).netloc,
                proposed_by=f"cited_in_document:{cited[0].name}",
            )
            for link in outbound_links
            if self._permitted(link)
        ][:5]

    def _permitted(self, url: str) -> bool:
        if not self.allowed_domains:
            return True
        domain = urlsplit(url).netloc.lower()
        return any(
            domain == allowed or domain.endswith(f".{allowed}") for allowed in self.allowed_domains
        )

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        response = await self._fetcher.fetch(candidate.url, provider="attribution")
        if not isinstance(response, FetchResult):
            event(
                logger,
                "cited source unreachable",
                module="sources.attribution",
                outcome="error",
                failure_reason=response.reason,
                level=logging.WARNING,
            )
            return None

        article = extract(response.text, url=candidate.url)

        return SourceSnapshot(
            id=f"snap:{response.final_url}",
            url=candidate.url,
            final_url=response.final_url,
            content_hash=f"sha256:{hash(response.body) & 0xFFFFFFFF:08x}",
            fetched_at=response.fetched_at,
            text=article.body or response.text,
            title=article.title,
            publisher=article.publisher or candidate.publisher,
            published_at=article.published_at,
            http_status=response.status_code,
        )

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Does the cited source carry this statement?"""
        overlap = keyword_overlap(claim.text, snapshot.text)

        if overlap >= CARRIES_THRESHOLD:
            excerpt, anchor = self._best_excerpt(claim.text, snapshot.text)
            if not excerpt:
                return insufficient(
                    ATTRIBUTION_NAME, VERSION, "source appears to carry it but no span matched"
                )
            return SourceRelation(
                relation=Relation.SUPPORTS,
                validator=ATTRIBUTION_NAME,
                validator_version=VERSION,
                excerpt=excerpt,
                anchor=anchor,
                metric="claim_presence",
                value=round(overlap, 4),
                threshold=CARRIES_THRESHOLD,
            )

        if overlap <= ABSENT_THRESHOLD:
            # Citable negative evidence, and often the single most decisive finding
            # available. The wording is narrow on purpose.
            return SourceRelation(
                relation=Relation.CONTRADICTS,
                validator=ATTRIBUTION_NAME,
                validator_version=VERSION,
                excerpt=(
                    f"The cited source at {snapshot.domain} does not carry this "
                    f"statement. Retrieved {snapshot.fetched_at:%Y-%m-%d}; nearest "
                    f"content: {snapshot.text[:160]}"
                ),
                anchor={"char_start": 0, "char_end": 160},
                metric="claim_presence",
                value=round(overlap, 4),
                threshold=ABSENT_THRESHOLD,
            )

        return insufficient(
            ATTRIBUTION_NAME,
            VERSION,
            f"source neither carries nor clearly lacks it ({overlap:.2f})",
        )

    def _best_excerpt(self, claim_text: str, source_text: str) -> tuple[str, dict[str, int]]:
        """Find the longest run of the claim that appears in the source."""
        words = claim_text.split()
        for length in range(len(words), 3, -1):
            for start in range(len(words) - length + 1):
                excerpt, anchor = locate_excerpt(
                    source_text, " ".join(words[start : start + length])
                )
                if excerpt:
                    return excerpt, anchor
        return "", {}


class QuoteResolver:
    """Checks a quoted statement against the source that supposedly said it.

    *"Ambedkar said…"*, *"APJ Kalam said…"* — a signature Indian pattern. Famous
    fabricated quotes are usually already adjudicated, so the fact-check resolver
    catches those; this handles the rest by looking for the exact words.
    """

    name = QUOTE_NAME
    version = VERSION
    allowed_domains: frozenset[str] = frozenset()

    def __init__(self, *, fetcher: SecureFetcher) -> None:
        self._fetcher = fetcher

    async def candidates(
        self, claim: Claim, *, corpus_urls: tuple[str, ...] = ()
    ) -> list[SourceCandidate]:
        return [
            SourceCandidate(url=url, proposed_by="corpus_quote_search") for url in corpus_urls[:5]
        ]

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        response = await self._fetcher.fetch(candidate.url, provider="quote")
        if not isinstance(response, FetchResult):
            return None
        article = extract(response.text, url=candidate.url)
        return SourceSnapshot(
            id=f"snap:{response.final_url}",
            url=candidate.url,
            final_url=response.final_url,
            content_hash=f"sha256:{hash(response.body) & 0xFFFFFFFF:08x}",
            fetched_at=response.fetched_at,
            text=article.body or response.text,
            title=article.title,
            published_at=article.published_at,
        )

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Look for the quoted words, exactly."""
        quoted = _extract_quoted(claim.text)
        if not quoted:
            return insufficient(QUOTE_NAME, VERSION, "no quoted statement in the claim")

        excerpt, anchor = locate_excerpt(snapshot.text, quoted)
        if not excerpt:
            return insufficient(QUOTE_NAME, VERSION, "quote not found in this source")

        return SourceRelation(
            relation=Relation.SUPPORTS,
            validator=QUOTE_NAME,
            validator_version=VERSION,
            excerpt=excerpt,
            anchor=anchor,
            metric="exact_quote_match",
            value=1.0,
            threshold=1.0,
        )


_QUOTED = re.compile(r'["“”\'‘’](.{15,400}?)["“”\'‘’]')


def _extract_quoted(text: str) -> str:
    """The quoted span, if the claim contains one."""
    match = _QUOTED.search(text)
    return match.group(1).strip() if match else ""
