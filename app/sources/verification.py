"""Source verification — the step between "sources were read" and "a verdict is made".

Every source a claim gathers passes through here before anything decides on it. Three
things happen, in this order:

1. **One citation per page.** The same URL reached a single claim two and three times
   — Full Fact's 5G page was cited three times for one claim in the stored ledger —
   through the fact-check API, the fact-check corpus and the web search each finding
   it. That double-counted support, and because a citation's id is derived from the
   page and the claim, it also crashed the evidence screen with duplicate keys.

2. **Only sources that take a side.** A source the reader marked as context neither
   supports nor contradicts the claim. The ledger holds 246 of them, and they are
   what a person sees as "irrelevant sources": a page on the topic that says nothing
   about the claim. They are no longer cited.

3. **A second opinion on relevance.** Every remaining source goes to one model call,
   side by side with the others, which answers per source: is this about *this*
   claim, and does it say true or false? A source survives only if the answer is yes
   and the direction agrees with what the reader found. Two independent readings that
   disagree about a page mean the page is ambiguous, and an ambiguous page is not
   evidence.

The step can only remove sources. It never adds one, and never turns a source from
one side to the other — the reader saw the whole passage and this call sees a quote,
so the reader's direction stands and this call can only veto it.

Credibility is attached last, from the curated publisher list rather than from a
model, so the same outlet weighs the same on every request.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import Direction, EvidenceKind
from app.domain.evidence import Evidence
from app.observability.logging import event

logger = logging.getLogger("factify.sources.verification")

# Kinds whose finding is not a passage of prose — a matched image, a dated copy, a
# content credential. There is no quote for a relevance check to read, and their own
# resolvers already require a date and a citation before they say anything.
_NOT_TEXT = frozenset(
    {
        EvidenceKind.DATED_SOURCE,
        EvidenceKind.MEDIA_MATCH,
        EvidenceKind.PROVENANCE,
        EvidenceKind.SOURCE_RISK,
    }
)

_AGREES = {Direction.SUPPORTS: "TRUE", Direction.CONTRADICTS: "FALSE"}

# When one page reaches a claim by more than one route, which copy to keep. A
# published fact-check outranks a news report of the same page, and a decisive
# reading outranks context.
_KIND_RANK = {EvidenceKind.FACT_CHECK: 0, EvidenceKind.ATTRIBUTION: 1, EvidenceKind.QUOTE: 1}
_DIRECTION_RANK = {Direction.CONTRADICTS: 0, Direction.SUPPORTS: 0}


class Checker(Protocol):
    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any: ...


class Ranker(Protocol):
    def credibility(self, url_or_domain: str | None) -> Any: ...


@dataclass(frozen=True, slots=True)
class Verified:
    """What survived, why the rest did not, and a plain summary when one was written."""

    evidence: list[Evidence]
    explanation: str | None
    duplicates: int = 0
    context_only: int = 0
    rejected: int = 0
    # False when the relevance check could not run. The evidence is kept rather than
    # thrown away, and the caller marks the run incomplete so it is not cached.
    checked: bool = True


def page_key(url: str) -> str:
    """One key per page, however the URL was written.

    Scheme, `www.`, trailing slash, query string and fragment are the differences that
    reached the ledger as separate citations of one article.
    """
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return f"{host}{path}"


def dedupe(evidence: list[Evidence]) -> tuple[list[Evidence], int]:
    """Keep the strongest copy of each page, in first-seen order."""
    best: dict[str, Evidence] = {}
    order: list[str] = []
    for item in evidence:
        key = page_key(item.citation_url)
        held = best.get(key)
        if held is None:
            best[key] = item
            order.append(key)
        elif _rank(item) < _rank(held):
            best[key] = item
    return [best[key] for key in order], len(evidence) - len(order)


def _rank(item: Evidence) -> tuple[int, int, str]:
    return (
        _DIRECTION_RANK.get(item.direction, 1),
        _KIND_RANK.get(item.kind, 2),
        item.tier.value,
    )


class SourceVerification:
    """Runs the three steps above for one claim."""

    def __init__(self, *, checker: Checker, ranker: Ranker) -> None:
        self._checker = checker
        self._ranker = ranker

    async def check(
        self, claim: Claim, evidence: list[Evidence], *, budget: float | None = None
    ) -> Verified:
        unique, duplicates = dedupe(evidence)

        passthrough = [item for item in unique if item.kind in _NOT_TEXT]
        text = [item for item in unique if item.kind not in _NOT_TEXT]
        sided = [item for item in text if item.direction in _AGREES]
        context_only = len(text) - len(sided)

        if not sided:
            return self._finish(
                claim,
                passthrough,
                explanation=None,
                duplicates=duplicates,
                context_only=context_only,
                rejected=0,
                checked=True,
            )

        # Bounded by what is left of the request. Past it, the sources are kept
        # unverified and the run is marked incomplete — never cached — rather than
        # holding the reply past the point the app stops waiting for it.
        try:
            answer = await asyncio.wait_for(
                self._checker.check_sources(
                    claim.text,
                    [
                        (item.publisher or _host(item.citation_url), item.source_excerpt)
                        for item in sided
                    ],
                ),
                timeout=budget,
            )
        except TimeoutError:
            answer = None
        if answer is None:
            return self._finish(
                claim,
                passthrough + sided,
                explanation=None,
                duplicates=duplicates,
                context_only=context_only,
                rejected=0,
                checked=False,
            )

        kept: list[Evidence] = []
        for index, item in enumerate(sided):
            reading = answer.readings.get(index)
            if reading is None:
                # The call did not say anything about this source. Silence is not a
                # vote of confidence; the page has not been confirmed relevant.
                continue
            if reading.addresses_claim and reading.verdict == _AGREES[item.direction]:
                kept.append(item)

        return self._finish(
            claim,
            passthrough + kept,
            explanation=answer.explanation or None,
            duplicates=duplicates,
            context_only=context_only,
            rejected=len(sided) - len(kept),
            checked=True,
        )

    def _finish(
        self,
        claim: Claim,
        evidence: list[Evidence],
        *,
        explanation: str | None,
        duplicates: int,
        context_only: int,
        rejected: int,
        checked: bool,
    ) -> Verified:
        # Weighed only when the check actually ran. Credibility is what lets a single
        # highly credible refutation decide a claim (rule 3c), and that rule is only
        # safe because every source reaching it was confirmed to be about this claim.
        # An unchecked source keeps no weight, so it cannot decide anything alone.
        weighed = (
            [
                item.model_copy(
                    update={"credibility": self._ranker.credibility(item.citation_url)}
                )
                for item in evidence
            ]
            if checked
            else list(evidence)
        )
        event(
            logger,
            "sources verified",
            module="sources.verification",
            outcome="ok" if checked else "degraded",
            claim_id=claim.id,
            kept=len(weighed),
            duplicates=duplicates,
            context_only=context_only,
            rejected=rejected,
            checked=checked,
        )
        return Verified(
            evidence=weighed,
            explanation=explanation,
            duplicates=duplicates,
            context_only=context_only,
            rejected=rejected,
            checked=checked,
        )


def _host(url: str) -> str:
    return (urlsplit(url).hostname or url).removeprefix("www.")
