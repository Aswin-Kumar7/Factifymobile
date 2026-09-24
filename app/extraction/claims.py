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
from dataclasses import dataclass
from typing import Any, Protocol

from app.cache.service import CacheService
from app.domain.claim import Claim, ClaimAnchor
from app.domain.typography import fold
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

    @property
    def succeeded(self) -> bool:
        return self.reason is None


def _normalise(text: str) -> str:
    # Typography folded as well as case and spacing. Without it a newsonair.gov.in
    # article produced six claims and all six were discarded as "not found in source",
    # the same failure the citation quote gate had before it learned the same rule.
    return fold(text)


def _locate(claim_text: str, source: str) -> tuple[int, int] | None:
    """Find the claim in the source, returning character offsets.

    Exact match first, then a longest-run fallback for the common case where the
    model tidied punctuation. If neither finds it, the claim does not correspond to
    the document and is not stored.
    """
    haystack = _normalise(source)
    needle = _normalise(claim_text)

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

    return None


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

        for index, proposal in enumerate(proposals):
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
