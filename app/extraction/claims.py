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

    A protocol rather than a base class, so a test double is a first-class
    implementation rather than a degraded subclass of the real one.
    """

    async def extract_claims(self, text: str) -> ExtractionOutcome: ...


# How much of a proposed claim must appear verbatim in the source before the anchor is
# believed. Not 100%: extraction legitimately normalises whitespace and drops a
# trailing clause. Low enough to survive that, high enough that an invented sentence
# cannot pass.
_ANCHOR_MATCH_THRESHOLD = 0.6

# A message this short that yields a claim is that claim, when no reading of it can be
# found in it word for word (`ClaimPipeline._verify`).
_WHOLE_MESSAGE = 400
# A sentence ending inside a message: the fallback is for one-sentence forwards only.
_SENTENCE_END = re.compile(r"[.!?।|]\s+\S")
_RANK = {
    Importance.HEADLINE: 0,
    Importance.MAIN_THESIS: 1,
    Importance.SUPPORTING_DETAIL: 2,
    Importance.BACKGROUND: 3,
}


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


# How much of a word in an Indian script is its stem, in characters (code points).
_STEM = 5
# Joiners that shape a script's letters but carry no meaning of their own.
_JOINERS = str.maketrans("", "", "‌‍")


def _fact_words(text: str) -> list[str]:
    """The fact-bearing words of folded text: no function words, months abbreviated,
    and a plain suffix trimmed, so "arrested" matches "arrests" and "January" "Jan".

    In the Indian scripts a word carries its case ending: Kannada "2024ರ" (of 2024)
    and "2024ರಲ್ಲಿ" (in 2024), "ಆಸ್ಟ್ರೇಲಿಯಾವನ್ನು" and "ಆಸ್ಟ್ರೇಲಿಯಾ". gpt-5.6-luna split
    "India won the 2024 T20 World Cup and beat Australia in the final" into two claims
    and wrote the second in full, and it was discarded as not in the text (2026-09-28).
    So a number there is its digits and a word its first few letters.
    """
    words: list[str] = []
    for raw in text.split():
        word = raw.strip(".,;:!?()[]\"'।").translate(_JOINERS)
        if not word or word in _FUNCTION_WORDS:
            continue
        if not word.isascii():
            if any(ch.isdigit() for ch in word):
                word = "".join(ch for ch in word if ch.isdigit())
            else:
                word = word[:_STEM]
            words.append(word)
            continue
        word = _MONTHS.get(word, word)
        if not word.isdigit() and len(word) > 4:
            for suffix in _SUFFIXES:
                if word.endswith(suffix):
                    word = word[: -len(suffix)]
                    break
        words.append(word)
    return words


def _shares_a_fact(source: str, reading: str) -> bool:
    """Whether a reading of a message names something the message itself does: a
    number, or a word of four letters or more. What guards the whole-message fallback
    against a claim the model invented - which shares nothing with the message."""
    ours = set(_fact_words(fold(source)))
    theirs = set(_fact_words(fold(reading)))
    return any(any(ch.isdigit() for ch in word) or len(word) >= 4 for word in ours & theirs)


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
        # An English claim is shown self-contained - "Chandrayaan-3's rover payloads
        # include APXS and LIBS" where the article says "Rover payloads include ..." -
        # since a claim listed as wrong has to say what it is about. Located, above,
        # by the document's exact words, which is what the anchor points at. A claim
        # in another language keeps its own words, and the app shows the English in
        # full beside it (`in_full` in the response).
        text=_shown(proposal, language),
        normalized_text=_normalise(proposal.text),
        claim_type=proposal.claim_type,
        severity=proposal.severity,
        importance=proposal.importance,
        coverage_expectation=proposal.coverage_expectation,
        entities=tuple(proposal.entities),
        search_phrases=tuple(proposal.search_phrases),
        location=proposal.location,
        language=language,
        # Written by the extractor, which saw the whole document: "NASA launched
        # Chandrayaan-3" where the claim's own words say "NASA launched it". A
        # translation of the claim alone kept the "it", and a NASA page about Artemis
        # II then "confirmed" it (2026-09-28).
        english_text=_standalone(proposal.standalone_english),
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
        # Stored readings are the model's, so they are kept per model: switching from
        # gpt-4.1-mini to gpt-5.6-luna would otherwise go on serving the old model's
        # claims for every text it had read before.
        model = getattr(extractor, "model_id", None)
        self._version = f"{EXTRACTOR_VERSION}+{model}" if model else EXTRACTOR_VERSION

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
                content_hash=content_hash, extractor_version=self._version
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
                extractor_version=self._version,
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

        # A short message whose one claim was read but not found word for word: the
        # message itself is the claim. gpt-5.6-luna sometimes writes a Hinglish
        # forward's claim in Devanagari or English, and "Modi ji ne bola hai ki kal
        # se desh ke sab petrol pump band rahenge" came back with nothing to check
        # (2026-09-30). The person's own words are shown, so nothing invented can
        # reach storage; the model's English still drives the search.
        first = min(proposals, key=lambda p: _RANK.get(p.importance, 9), default=None)
        if (
            not claims
            and first is not None
            and len(proposals) == 1
            and len(source.strip()) <= _WHOLE_MESSAGE
            and len(_SENTENCE_END.findall(source.strip().rstrip(".!?।|"))) == 0
            and _shares_a_fact(source, f"{first.text} {first.standalone_english}")
        ):
            whole = _to_claim(
                first.model_copy(update={"text": source.strip()}),
                claim_id="cl_1",
                source=source,
                content_hash=content_hash,
                input_kind=input_kind,
                language=language,
            )
            if whole is not None:
                claims.append(whole)
                discarded = [text for text in discarded if text != first.text[:120]]

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


# Longest self-contained English sentence taken from the extractor. A claim is a
# sentence; anything far longer is the model writing an essay, not restating it.
_STANDALONE_CHARACTERS = 400


def _standalone(text: str) -> str:
    """The extractor's self-contained English version of a claim, tidied, or ""."""
    line = " ".join(text.split())
    return line if 0 < len(line) <= _STANDALONE_CHARACTERS else ""


def _shown(proposal: ProposedClaim, language: str | None) -> str:
    """The claim as a person reads it: for an English document, its self-contained
    version when the extractor wrote one; otherwise the document's own words."""
    standalone = _standalone(proposal.standalone_english)
    if not standalone or (language or "en") != "en":
        return proposal.text
    # A translation instead of the document's language, or a sentence about something
    # else, is not shown: it must share words with what the document says.
    own = set(_WORDS.findall(_normalise(proposal.text)))
    shared = own & set(_WORDS.findall(_normalise(standalone)))
    return standalone if own and len(shared) / len(own) >= 0.5 else proposal.text


# Words in Latin, digits and the Indian and Arabic scripts, less the danda.
_WORDS = re.compile(r"[a-z0-9ऀ-ॣ०-ൿ؀-ۿݐ-ݿ]+")
