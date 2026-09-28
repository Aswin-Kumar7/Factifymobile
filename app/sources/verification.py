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
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import ClaimType, Direction, EvidenceKind
from app.domain.evidence import (
    NARROWER_SCOPE,
    Evidence,
    MatchBasis,
    is_narrower_scope,
    is_shared_review,
)
from app.domain.typography import fold
from app.observability.logging import event
from app.sources.base import current_reference_date

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


def _expected(item: Evidence) -> str | None:
    """What the check must say for this source to be kept: TRUE for support, FALSE
    for a contradiction, PARTLY for a narrower version of the claim; None for other
    context, which is not sent."""
    if item.direction in _AGREES:
        return _AGREES[item.direction]
    if item.direction is Direction.CONTEXTUALIZES and is_narrower_scope(item.match_basis.metric):
        return "PARTLY"
    return None


def _as_narrower(item: Evidence, reason: str) -> Evidence:
    """A support the check read as only part of the claim: kept, as a narrower version."""
    return item.model_copy(
        update={
            "direction": Direction.CONTEXTUALIZES,
            "match_basis": MatchBasis(
                metric=f"{NARROWER_SCOPE}: {reason}"[:200],
                value=item.match_basis.value,
                threshold=item.match_basis.threshold,
            ),
        }
    )


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


# Query parameters that say how someone arrived at a page, not which page it is.
_TRACKING_PREFIXES = ("utm_", "mc_")
_TRACKING_NAMES = frozenset({"fbclid", "gclid", "ref", "ref_src", "src", "amp", "share", "cmp"})


def page_key(url: str) -> str:
    """One key per page, however the URL was written.

    Scheme, `www.`, trailing slash, tracking parameters and fragment are the
    differences that reached the ledger as separate citations of one article.

    The rest of the query string is kept. It used to be dropped whole, and for some
    publishers it is the page: every PIB release is `PressReleasePage.aspx?PRID=...`,
    so two different releases would have been merged into one citation.
    """
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    # The mobile and AMP copies of an article are the article. The Hindu's AMP copy
    # (".../article71502791.ece/amp/") was cited as evidence for the article it copies.
    for prefix in ("www.", "m.", "amp."):
        host = host.removeprefix(prefix)
    path = parts.path.rstrip("/") or "/"
    path = path.removesuffix("/amp").removeprefix("/amp/") or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    query = "&".join(
        sorted(
            pair
            for pair in parts.query.split("&")
            if pair and not _is_tracking(pair.split("=", 1)[0].lower())
        )
    )
    return f"{host}{path}?{query}" if query else f"{host}{path}"


def _is_tracking(name: str) -> bool:
    return name in _TRACKING_NAMES or name.startswith(_TRACKING_PREFIXES)


def dedupe(evidence: list[Evidence]) -> tuple[list[Evidence], int]:
    """Keep the strongest copy of each page, in first-seen order.

    Two pages of one publisher quoting the same words count as one page too. The Hindu
    printed a story and embedded the same paragraph in its live blog; both were cited,
    and the result showed The Hindu twice with an identical quote — one source, dressed
    as two.
    """
    best: dict[str, Evidence] = {}
    order: list[str] = []
    same_words: dict[tuple[str, str], str] = {}
    for item in evidence:
        key = page_key(item.citation_url)
        words = (_host(item.citation_url).removeprefix("www."), fold(item.source_excerpt))
        if key not in best:
            key = same_words.setdefault(words, key)
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

    def trusted(self, url: str) -> bool:
        """Whether this page's publisher is one we rank: highly or moderately credible."""
        return str(self._ranker.credibility(url)) in ("HIGH", "MEDIUM")

    async def check(
        self, claim: Claim, evidence: list[Evidence], *, budget: float | None = None
    ) -> Verified:
        unique, duplicates = dedupe(evidence)

        # A shared fact-check's own rating names this claim in the page's markup;
        # there is no passage to check it against (`is_shared_review`).
        held = {
            id(item)
            for item in unique
            if item.kind in _NOT_TEXT or is_shared_review(item.match_basis.metric)
        }
        passthrough = [item for item in unique if id(item) in held]
        text = [item for item in unique if id(item) not in held]
        # A report of another occurrence of the thing the claim is about - an earlier
        # or later year's, another match of the tournament - is not about this one,
        # whatever it says (`_other_occurrence`). Set aside before anyone reads it as
        # support or contradiction.
        elsewhere = {id(item): why for item in text if (why := _other_occurrence(item, claim))}
        early = [item for item in text if id(item) in elsewhere]
        text = [item for item in text if id(item) not in elsewhere]
        sided = [item for item in text if _expected(item) is not None]
        context_only = len(text) - len(sided)
        # What happened to each source, by host, for the log. Counts alone could not
        # answer "why was The Hindu not cited?" without re-running the check.
        outcomes = [
            {"host": _host(item.citation_url), "outcome": "context", "reason": item.finding[:200]}
            for item in text
            if _expected(item) is None
        ] + [
            {"host": _host(item.citation_url), "outcome": f"set aside: {elsewhere[id(item)]}"}
            for item in early
        ]

        if not sided:
            return self._finish(
                claim,
                passthrough,
                explanation=None,
                duplicates=duplicates,
                context_only=context_only,
                rejected=0,
                checked=True,
                outcomes=outcomes,
            )

        # Bounded by what is left of the request. Past it, the sources are kept
        # unverified and the run is marked incomplete — never cached — rather than
        # holding the reply past the point the app stops waiting for it.
        try:
            answer = await asyncio.wait_for(
                self._checker.check_sources(
                    claim.reading_text,
                    [
                        (item.publisher or _host(item.citation_url), _under_headline(item))
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
            host = _host(item.citation_url)
            if reading is None:
                # The call did not say anything about this source. Silence is not a
                # vote of confidence; the page has not been confirmed relevant.
                outcomes.append({"host": host, "outcome": "unmentioned"})
                continue
            # A narrower version of the claim is, by definition, not "the same
            # assertion", so the check answered PARTLY and "not about the claim" in
            # one breath, and requiring both threw away every narrower source: the
            # Tamil Nadu reports behind "Govt pays every woman Rs 5,000 a month" were
            # read as PARTLY twice and kept by neither (2026-09-27). When the reader
            # found a narrower version and the check agrees it is PARTLY, it is kept.
            partly = reading.verdict == "PARTLY"
            # A smaller version states a detail of the claim differently; a page that
            # only leaves details out is not one (`states_differently`).
            smaller = (
                partly
                and reading.smaller_version
                and reading.states_differently
                and not reading.other_group
            )
            if not partly and reading.verdict == _expected(item) and reading.addresses_claim:
                kept.append(item)
                outcomes.append({"host": host, "outcome": f"kept ({item.direction.value})"})
            elif (
                partly
                and not reading.states_differently
                and item.direction is Direction.SUPPORTS
                and reading.addresses_claim
            ):
                # Read as support, and the check found nothing it states differently -
                # only details it does not mention. What it says matches the claim:
                # India Today on the Aditya-L1 launch, without naming the launch site.
                kept.append(item)
                outcomes.append({"host": host, "outcome": "kept (supports, says less)"})
            elif smaller:
                # Read as support (or as a narrower version), and the check says it
                # shows only a smaller version of the claim: that version is what it
                # is evidence of, not the claim - "partly true". Asked as its own
                # question, because asked through the verdict the check called a
                # one-time Rs 5,000 payment "FALSE, not about the claim" and it was
                # thrown away (2026-09-28). Both answers are required. PARTLY alone:
                # for "Atal Free Pension Scheme" against the real Atal Pension Yojana
                # the check said PARTLY and, rightly, "not a smaller version" - a
                # scam's borrowed name. "Smaller version" alone: it was said of pages
                # that merely said less ("the photographs were also shared", for a
                # claim naming Facebook and X). And for the claim's own people or
                # some of them: the PM Internship Scheme's Rs 5,000 for interns is no
                # smaller version of "every woman gets Rs 5,000" (`other_group`).
                #
                # Read as a contradiction too, when the check calls it a smaller
                # version. Tamil Nadu's Rs 1,000 a month for women heads of families
                # was read as denying "every woman gets Rs 5,000 a month" and dropped,
                # four outlets on one card, while the check called each a smaller
                # version; the user decided a real smaller version for the same
                # people is what makes such a claim partly true (2026-09-28). A
                # fact-check or official denial is still a contradiction: the check
                # answers FALSE for those, and they are kept as that.
                kept.append(_as_narrower(item, reading.reason))
                outcomes.append(
                    {
                        "host": host,
                        "outcome": "kept (narrower than the claim)",
                        "reason": reading.reason[:200],
                    }
                )
            else:
                outcomes.append(
                    {
                        "host": host,
                        "outcome": (
                            f"rejected: read {item.direction.value}, check said "
                            f"{reading.verdict}, about the claim={reading.addresses_claim}"
                        ),
                        "reason": reading.reason[:200],
                    }
                )

        return self._finish(
            claim,
            passthrough + kept,
            explanation=answer.explanation or None,
            duplicates=duplicates,
            context_only=context_only,
            rejected=len(sided) - len(kept),
            checked=True,
            outcomes=outcomes,
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
        outcomes: list[dict[str, str]] | None = None,
    ) -> Verified:
        # Weighed only when the check actually ran. Credibility is what lets a single
        # highly credible refutation decide a claim (rule 3c), and that rule is only
        # safe because every source reaching it was confirmed to be about this claim.
        # An unchecked source keeps no weight, so it cannot decide anything alone.
        weighed = (
            [
                item.model_copy(update={"credibility": self._ranker.credibility(item.citation_url)})
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
            sources=outcomes or [],
        )
        return Verified(
            evidence=weighed,
            explanation=explanation,
            duplicates=duplicates,
            context_only=context_only,
            rejected=rejected,
            checked=checked,
        )


def _under_headline(item: Evidence) -> str:
    """The quoted passage, with the headline it was published under when known.

    A quote alone is a sentence out of context. The Hindu's report of a party's
    ultimatum quoted "warned of a nationwide agitation ... if he does not step down",
    and the check rejected it for not naming the protest the claim named — which the
    article's own headline did, in the words of the claim. The first reader already
    sees the headline; the check now does too.
    """
    lines = []
    if item.title and item.title.strip():
        lines.append(f"HEADLINE: {item.title.strip()}")
    if item.published_on is not None:
        lines.append(f"PUBLISHED: {item.published_on.isoformat()}")
    if not lines:
        return item.source_excerpt
    return "\n".join([*lines, f"PASSAGE: {item.source_excerpt}"])


def _host(url: str) -> str:
    return (urlsplit(url).hostname or url).removeprefix("www.")


# A year a claim names: 1900-2099.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


# A full date in a claim's English: "2 September 2023" or "September 2, 2023".
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_DAY_FIRST = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+((?:19|20)\d{2})\b", re.I)
_MONTH_FIRST = re.compile(r"\b([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b", re.I)
# A claim that something happened, not that it will.
_HAPPENED = re.compile(
    r"\b(?:launched|landed|won|beat|died|was|were|held|announced|withdrew|declared|"
    r"passed|signed|arrested|released|killed|opened|inaugurated|took place)\b",
    re.IGNORECASE,
)


# How much older than a shared news page a report must be to be about an earlier
# occurrence of what the page reports.
_EARLIER_DAYS = 60

_ORDINALS = {
    word: number
    for number, word in enumerate(
        (
            "first second third fourth fifth sixth seventh eighth ninth tenth eleventh "
            "twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth "
            "nineteenth twentieth"
        ).split(),
        start=1,
    )
}
_ROUND = re.compile(
    r"\b(?:rounds?\s+(\d{1,2})|(\d{1,2})(?:st|nd|rd|th)?\s+rounds?|([a-z]+)\s+rounds?)\b",
    re.IGNORECASE,
)


def _rounds(text: str) -> set[int]:
    """The round numbers a text names: "round 11", "11 rounds", "the eighth round"."""
    found: set[int] = set()
    for number, before, word in _ROUND.findall(text):
        if number or before:
            found.add(int(number or before))
        elif word.casefold() in _ORDINALS:
            found.add(_ORDINALS[word.casefold()])
    return found


# A passage written before an outcome, and one that reports an outcome.
_PREVIEW = re.compile(
    r"\b(?:will (?:face|meet|play|launch|take on|be held|land)|set to|one (?:win|step) away|"
    r"ahead of|gear(?:s|ing)? up|to face|to take on|are expected to|is expected to|"
    r"scheduled to|preview|build-?up to|countdown)\b",
    re.IGNORECASE,
)
_COMPLETED = re.compile(
    r"\b(?:won|beat|beaten|defeated|lifted|clinched|landed|launched|lifted off|"
    r"was held|were held|died|passed away|announced|declared|withdrew|signed)\b",
    re.IGNORECASE,
)


def _claimed_day(text: str) -> date | None:
    """The first full date a claim names, or None."""
    for pattern, order in ((_DAY_FIRST, (0, 1)), (_MONTH_FIRST, (1, 0))):
        for match in pattern.finditer(text):
            parts = match.groups()
            day_text, month_text = parts[order[0]], parts[order[1]]
            month = _MONTHS.get(month_text.casefold())
            if month is None or not day_text.isdigit():
                continue
            try:
                return date(int(parts[2]), month, int(day_text))
            except ValueError:
                continue
    return None


# Stages of a tournament other than the final. A claim about the final is not
# answered by a report of another match: "India beat Australia by 24 runs in the
# Super Eight" was read as support for "India beat Australia in the 2024 T20 World Cup
# final", and the model, asked outright whether it was the same match, said yes while
# its own reason said "not the final" (2026-09-28).
_OTHER_STAGE = re.compile(
    r"\b(?:semi[- ]?finals?|quarter[- ]?finals?|super[- ](?:eights?|8|six|6|fours?|4)|"
    r"group[- ]stage|group [a-h]\b|league (?:stage|match|game)|qualifiers?|"
    r"warm[- ]?up|eliminator|play[- ]?offs?)",
    re.IGNORECASE,
)
_FINAL = re.compile(r"\bfinals?\b", re.IGNORECASE)
# Things that happen again and again, where a later report is about a later one.
_RECURRING = re.compile(
    r"\b(?:world cup|t20|odi|ipl|olympics?|asian games|commonwealth games|elections?|"
    r"budget|census|championships?|tournament|trophy|finals?|summit|awards?|nobel)\b",
    re.IGNORECASE,
)


def _other_occurrence(item: Evidence, claim: Claim) -> str | None:
    """Why a news report is about another occurrence than the claim's, or None.

    Rules, not the model: asked "is this the same occurrence?" as a question of its
    own, gpt-4.1-mini said yes to the 2023 ODI World Cup final and to a Super Eight
    match for a claim about the 2024 T20 final (2026-09-28). Only for a news report: a
    fact-check or an earlier copy of a picture is exactly what speaks to a claim's
    date, and must never be set aside for it.
    """
    if item.kind is not EvidenceKind.CORROBORATION:
        return None
    said = claim.search_text
    passage = f"{item.title or ''} {item.source_excerpt}"
    years = {int(year) for year in _YEAR.findall(said)}
    named = any(str(year) in passage for year in years)

    # Published before the year the claim is about, and not naming it: it cannot be
    # reporting it. A 2025 report of a launch planned for 2027 names 2027, and stays.
    published = item.published_on
    if years and published is not None and published.year < min(years) and not named:
        return "published before the event"

    # Published before the day a claim says something happened: a preview, not a
    # report. "ISRO will launch Aditya-L1 on September 2" read as a smaller version of
    # "ISRO launched Aditya-L1 on 2 September 2023" (2026-09-28).
    day = _claimed_day(said)
    if day is not None and published is not None and published < day and _HAPPENED.search(said):
        return "published before the event"

    # Another round of the same event: "after the eighth round" is not "after 11
    # rounds". The Chess Olympiad's standings after rounds seven and eight
    # contradicted the final standings (2026-09-28).
    claimed_rounds = _rounds(said)
    reported_rounds = _rounds(passage)
    if claimed_rounds and reported_rounds and not claimed_rounds & reported_rounds:
        return "another round"

    # A claim from a dated news page that names no year is about that page's moment.
    # News from months before it is about an earlier one: a 2020 report of a different
    # Supreme Court petition "supported" a 2026 report that the court issued notices
    # to the Centre, the RBI and NPCI (2026-09-28).
    reference = current_reference_date.get()
    if (
        reference is not None
        and not years
        and published is not None
        and (reference - published).days > _EARLIER_DAYS
        and claim.claim_type is ClaimType.EVENT
    ):
        return "an earlier occurrence"

    # A preview, whatever its date: written before the outcome, it neither confirms
    # nor contradicts it. "India are just one win away ... as they face South Africa
    # in the final" was read as contradicting "India won the 2024 T20 World Cup".
    if (
        _HAPPENED.search(said)
        and _PREVIEW.search(item.source_excerpt)
        and not _COMPLETED.search(item.source_excerpt)
    ):
        return "a preview, written before the outcome"

    # Another match of the tournament, for a claim about the final.
    claimed_final = _FINAL.search(_OTHER_STAGE.sub(" ", said)) is not None
    if (
        claimed_final
        and _OTHER_STAGE.search(said) is None
        and _OTHER_STAGE.search(passage) is not None
        and _FINAL.search(_OTHER_STAGE.sub(" ", passage)) is None
    ):
        return "another match"

    # A report from years later about something that recurs, not naming the claim's
    # year: about a later one. "India won the T20 World Cup for a record third time"
    # is not the 2024 title.
    if (
        years
        and published is not None
        and published.year > max(years) + 1
        and _RECURRING.search(said) is not None
        and not named
    ):
        return "a later occurrence"
    return None
