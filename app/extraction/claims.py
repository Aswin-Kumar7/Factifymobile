"""Claim extraction (M20).

Turns a document into atomic, anchored, checkable claims. The model's part is
segmentation and labelling; everything that decides anything happens elsewhere.

The gate that matters here is not "did we get claims" but **"can every claim be traced
back to real text"**. A model can hallucinate a sentence the document does not
contain, and a document can instruct the model to produce one. Both are caught by the
same check: the proposed span is verified against the source, and a claim whose anchor
does not resolve is discarded rather than stored.

That check is why a successful injection cannot manufacture a claim out of nothing —
it would have to also make the text it invented appear in the document.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.cache.service import CacheService
from app.domain.claim import Claim, ClaimAnchor
from app.domain.enums import Importance
from app.domain.typography import fold, fold_with_positions
from app.extraction.llm import EXTRACTOR_VERSION, ExtractionOutcome, ProposedClaim
from app.observability.logging import event

logger = logging.getLogger("factify.claims")


class Extractor(Protocol):
    """What the pipeline needs from a model client.

    A protocol rather than a base class so `UnavailableExtractor` — which exists
    precisely to return nothing — is a first-class implementation rather than a
    degraded subclass of the real one.
    """

    async def extract_claims(self, text: str) -> ExtractionOutcome: ...


# How much of a proposed claim must appear verbatim in the source before the anchor is
# believed. Not 100%: extraction legitimately normalises whitespace and drops a
# trailing clause. Low enough to survive that, high enough that an invented sentence
# cannot pass.
_ANCHOR_MATCH_THRESHOLD = 0.6


@dataclass(frozen=True, slots=True)
class ExtractedClaims:
    """Verified claims, plus everything discarded and why."""

    claims: tuple[Claim, ...] = ()
    model_id: str | None = None
    from_cache: bool = False
    reason: str | None = None
    discarded: tuple[str, ...] = ()
    injection_findings: tuple[str, ...] = ()
    # Set when the claims came from less than the whole source: a linked page whose
    # article could not be read, checked on its published headline and summary.
    partial_source: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.reason is None


def _normalise(text: str) -> str:
    # Typography folded as well as case and spacing. Without it a newsonair.gov.in
    # article produced six claims and all six were discarded as "not found in source",
    # the same failure the citation quote gate had before it learned the same rule.
    return fold(text)


def _locate(claim_text: str, source: str) -> tuple[int, int] | None:
    """Find the claim in the source, returning character offsets in `source` itself.

    Exact match first, then a longest-run fallback for the common case where the
    model tidied punctuation. If neither finds it, the claim does not correspond to
    the document and is not stored.

    The search runs in folded text, whose whitespace is flattened; the offsets are
    carried back to the source's own characters, so a claim's location points at
    what the person sent - the app underlines it there - not at a tidied copy.
    """
    haystack, origin = fold_with_positions(source)
    found = _locate_folded(_normalise(claim_text), haystack)
    if found is None:
        return None
    start, end = found
    return origin[start], origin[end - 1] + 1


def _locate_folded(needle: str, haystack: str) -> tuple[int, int] | None:
    """The claim's offsets in the folded source, or None."""

    if not needle:
        return None

    position = haystack.find(needle)
    if position != -1:
        return position, position + len(needle)

    # Fall back to the longest contiguous run of the claim that does appear. A
    # paraphrase keeps most of its subject and object intact; an invention does not.
    words = needle.split()
    for length in range(len(words), 2, -1):
        for start in range(len(words) - length + 1):
            fragment = " ".join(words[start : start + length])
            found = haystack.find(fragment)
            if found != -1 and length / len(words) >= _ANCHOR_MATCH_THRESHOLD:
                return found, found + len(fragment)

    return _locate_by_coverage(needle, haystack)


# Words that carry no fact of their own, so a claim is matched on the ones that do.
_FUNCTION_WORDS = frozenset(
    """a an the is are was were be been being has have had do does did will would shall
    should can could may might must and or but nor so yet of in on at to for from by with
    about as into onto over under after before during than that this these those which
    who whom whose what when where why how it its their there they them he she his her
    him we our you your i me my not no also just only very more most such both each
    said says say according""".split()
)
_MONTHS = {
    "january": "jan", "february": "feb", "march": "mar", "april": "apr", "june": "jun",
    "july": "jul", "august": "aug", "september": "sep", "sept": "sep", "october": "oct",
    "november": "nov", "december": "dec",
}  # fmt: skip
_SUFFIXES = ("ing", "ed", "es", "s")

# Share of a claim's fact-bearing words that one short stretch of the source must hold,
# with every number among them.
_COVERAGE_THRESHOLD = 0.8
_YEAR = re.compile(r"(19|20)\d\d")


def _fact_words(text: str) -> list[str]:
    """The fact-bearing words of folded text: no function words, months abbreviated,
    and a plain suffix trimmed, so "arrested" matches "arrests" and "January" "Jan"."""
    words: list[str] = []
    for raw in text.split():
        word = raw.strip(".,;:!?()[]\"'")
        if not word or word in _FUNCTION_WORDS:
            continue
        word = _MONTHS.get(word, word)
        if not word.isdigit() and len(word) > 4:
            for suffix in _SUFFIXES:
                if word.endswith(suffix):
                    word = word[: -len(suffix)]
                    break
        words.append(word)
    return words


def _locate_by_coverage(needle: str, haystack: str) -> tuple[int, int] | None:
    """The shortest stretch of the source holding the claim's facts, or None.

    A claim extracted from a list is rewritten as a sentence, and no run of its words
    survives. On a page listing "Barack Obama / Arrested Jan 29, facing tribunal for
    High Treason.", the claim "Barack Obama was arrested on January 29 and is facing a
    tribunal for High Treason" matched four of fifteen words in a row and was
    discarded — as were all seven claims on the page, faithful every one.

    So the facts are matched rather than the wording: 80% of the claim's fact-bearing
    words, and every number, within a stretch of the source not much longer than the
    claim. A year is the one number allowed to come from elsewhere on the page — a
    list dated February 2025 says "Feb 3", and the claim rightly says "February 3,
    2025" — but it must still be on the page. An invented claim fails, because the
    facts it invents are not there; a claim assembled from words scattered across the
    page fails, because the stretch is bounded.
    """
    wanted = _fact_words(needle)
    if len(wanted) < 3:
        return None
    distinct = set(wanted)
    years = {word for word in distinct if _YEAR.fullmatch(word)}
    if any(year not in haystack for year in years):
        return None
    numbers = {word for word in distinct - years if any(ch.isdigit() for ch in word)}
    need = max(len(numbers), int(len(distinct) * _COVERAGE_THRESHOLD + 0.999))

    # The source as fact-bearing words, each with where it sits in the folded text.
    positions: list[tuple[str, int, int]] = []
    cursor = 0
    for raw in haystack.split():
        start = haystack.find(raw, cursor)
        cursor = start + len(raw)
        words = _fact_words(raw)
        if words:
            positions.append((words[0], start, cursor))

    span = max(12, 3 * len(distinct))
    best: tuple[int, int] | None = None
    for first in range(len(positions)):
        if positions[first][0] not in distinct:
            continue
        seen: set[str] = set()
        for last in range(first, min(len(positions), first + span)):
            word = positions[last][0]
            if word in distinct:
                seen.add(word)
            if len(seen | years) >= need and numbers <= seen:
                candidate = (positions[first][1], positions[last][2])
                if best is None or candidate[1] - candidate[0] < best[1] - best[0]:
                    best = candidate
                break
    return best


def _to_claim(
    proposal: ProposedClaim,
    *,
    claim_id: str,
    source: str,
    content_hash: str,
    input_kind: str,
    language: str | None,
) -> Claim | None:
    """Convert a proposal into a stored claim, or reject it."""
    located = _locate(proposal.text, source)
    if located is None:
        return None

    char_start, char_end = located

    return Claim(
        id=claim_id,
        text=proposal.text,
        normalized_text=_normalise(proposal.text),
        claim_type=proposal.claim_type,
        severity=proposal.severity,
        importance=proposal.importance,
        coverage_expectation=proposal.coverage_expectation,
        entities=tuple(proposal.entities),
        search_phrases=tuple(proposal.search_phrases),
        location=proposal.location,
        language=language,
        anchor=ClaimAnchor(
            input_kind=input_kind,
            content_hash=content_hash,
            section=proposal.source_anchor.section,
            paragraph_index=proposal.source_anchor.paragraph_index,
            char_start=char_start,
            char_end=char_end,
        ),
    )


class ClaimPipeline:
    """Extraction, verification and caching around one model call per document."""

    def __init__(self, extractor: Extractor, cache: CacheService | None = None) -> None:
        self._extractor = extractor
        self._cache = cache

    async def extract(
        self,
        text: str,
        *,
        content_hash: str,
        input_kind: str = "text",
        language: str | None = None,
    ) -> ExtractedClaims:
        """Extract claims from a document, at most one model call.

        A cache hit costs zero calls, which is what makes re-running the audit
        manifest after a code change affordable.
        """
        if not text.strip():
            return ExtractedClaims(reason="no text to extract from")

        if self._cache is not None:
            cached = await self._cache.get_extraction(
                content_hash=content_hash, extractor_version=EXTRACTOR_VERSION
            )
            if cached is not None:
                return self._from_cache(
                    cached,
                    source=text,
                    content_hash=content_hash,
                    input_kind=input_kind,
                    language=language,
                )

        outcome = await self._extractor.extract_claims(text)

        if not outcome.succeeded:
            # No claims and a stated reason. The case continues on media evidence or
            # abstains; nothing is invented to fill the gap.
            return ExtractedClaims(
                reason=outcome.reason, injection_findings=outcome.injection_findings
            )

        claims, discarded = self._verify(
            outcome.claims,
            source=text,
            content_hash=content_hash,
            input_kind=input_kind,
            language=language,
        )

        if self._cache is not None:
            await self._cache.put_extraction(
                content_hash=content_hash,
                extractor_version=EXTRACTOR_VERSION,
                payload={"claims": [claim.model_dump(mode="json") for claim in outcome.claims]},
                model_id=outcome.model_id,
            )

        return ExtractedClaims(
            claims=claims,
            model_id=outcome.model_id,
            discarded=discarded,
            injection_findings=outcome.injection_findings,
        )

    def _verify(
        self,
        proposals: tuple[ProposedClaim, ...],
        *,
        source: str,
        content_hash: str,
        input_kind: str,
        language: str | None,
    ) -> tuple[tuple[Claim, ...], tuple[str, ...]]:
        claims: list[Claim] = []
        discarded: list[str] = []
        # At most one headline and one main thesis, enforced rather than trusted: the
        # instruction says so, and an India TV fact-check still came back with two
        # main theses. Every one of them must be confirmed before a case can read
        # True, so a second one quietly raises the bar. Later ones become details.
        ranked_once: set[Importance] = set()

        for index, proposal in enumerate(proposals):
            if proposal.importance in (Importance.HEADLINE, Importance.MAIN_THESIS):
                if proposal.importance in ranked_once:
                    proposal = proposal.model_copy(
                        update={"importance": Importance.SUPPORTING_DETAIL}
                    )
                else:
                    ranked_once.add(proposal.importance)
            claim = _to_claim(
                proposal,
                claim_id=f"cl_{index + 1}",
                source=source,
                content_hash=content_hash,
                input_kind=input_kind,
                language=language,
            )
            if claim is None:
                discarded.append(proposal.text[:120])
                event(
                    logger,
                    "claim discarded: not found in source",
                    module="extraction.claims",
                    outcome="discarded",
                    failure_reason="anchor did not resolve",
                    level=logging.WARNING,
                )
                continue
            claims.append(claim)

        return tuple(claims), tuple(discarded)

    def _from_cache(
        self,
        payload: dict[str, Any],
        *,
        source: str,
        content_hash: str,
        input_kind: str,
        language: str | None,
    ) -> ExtractedClaims:
        raw = payload.get("claims", [])
        proposals = tuple(
            ProposedClaim.model_validate(item) for item in raw if isinstance(item, dict)
        )
        # Re-verified rather than trusted: a cached proposal is still a proposal, and
        # the anchor check is cheap next to the call it saved.
        claims, discarded = self._verify(
            proposals,
            source=source,
            content_hash=content_hash,
            input_kind=input_kind,
            language=language,
        )
        return ExtractedClaims(claims=claims, from_cache=True, discarded=discarded)
