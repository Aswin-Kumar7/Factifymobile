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

The step never adds a source, and never turns a source from one side to the other —
the reader saw the whole passage and this call sees a quote, so the reader's
direction stands and this call can veto it. What it can do besides is confirm a
support the reader held back: a passage read as only a narrower version, or as
someone else's word ("the Army said"), is support when this call reads it as
establishing the claim. Two readings that both find support are agreement, and
throwing such a page away cost true news reports their only evidence (2026-10-02).
And it can say a source finds the claim's words, picture or video genuine but
presented out of context, which is neither side: kept as that, never as support. The
one exception to "never to the other side" is a claim about who a picture shows, read
as support from a debunk calling the picture itself AI-made (`_MEDIA_FAKED`): the fake
does show them, and the check's FALSE is kept.

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
    OUT_OF_CONTEXT,
    PARTIAL_SCOPE,
    Evidence,
    MatchBasis,
    is_narrower_scope,
    is_out_of_context,
    is_shared_review,
)
from app.domain.typography import fold
from app.observability.logging import event
from app.sources.base import current_reference_date
from app.sources.reasoning import event_years, is_attributed_support

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


def _read_as(item: Evidence) -> str | None:
    """How the first reader left a source, for the check's answer to be read against:
    "supports", "contradicts", "narrower" (a smaller version of the claim),
    "attributed" (a support the article put in someone else's mouth),
    "out_of_context" (a fact-check rating the claim's material genuine but misframed),
    or None for other context, which is not sent."""
    if item.direction is Direction.SUPPORTS:
        return "supports"
    if item.direction is Direction.CONTRADICTS:
        return "contradicts"
    if item.direction is Direction.CONTEXTUALIZES:
        if is_narrower_scope(item.match_basis.metric):
            return "narrower"
        if is_attributed_support(item.match_basis.metric):
            return "attributed"
        if is_out_of_context(item.match_basis.metric):
            return "out_of_context"
    return None


# Read as support of some kind: the claim, a smaller version of it, or the claim on
# someone's word.
_SUPPORT_READS = frozenset({"supports", "narrower", "attributed"})


# A passage that calls the claim's material made up rather than misframed: a
# contradiction that must stay one. The check is asked to tell the two apart
# (`out_of_context`); this is the backstop that keeps a fabricated quote, an
# AI-made picture or a denial from ever being softened to "out of context".
_MADE_UP = re.compile(
    r"\b(?:fake|fabricated|made[- ]up|morphed|doctored|photoshopped|deep[- ]?fakes?|"
    r"ai[- ]generated|(?:made|created|generated) (?:with|using|by) "
    r"(?:ai|artificial intelligence)|digitally (?:altered|created|edited|manipulated)|"
    r"never (?:said|made|happened)|did not (?:say|happen)|didn't (?:say|happen)|"
    r"denied|denies|no such (?:statement|announcement|incident|attack|event))\b",
    re.IGNORECASE,
)


def _made_up(item: Evidence) -> bool:
    """Whether a source's headline or passage calls the claim's material made up."""
    return _affirmed(_MADE_UP, f"{item.title or ''}. {item.source_excerpt}")


# A word that turns what follows it in the same clause into its opposite, and where a
# clause ends.
_NEGATION = re.compile(r"\b(?:not|no|nor|neither|without|never)\b|n't\b", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[.;:!?]|\bbut\b", re.IGNORECASE)


def _affirmed(pattern: re.Pattern[str], text: str) -> bool:
    """Whether the text says what `pattern` matches, and not only that it is not so.

    Snopes on the clipped Netanyahu video: "While the clip was authentic, meaning not
    generated with artificial intelligence or digitally altered, it omits critical
    context" - a finding of misframing that names the words of a fake only to rule
    them out (2026-10-02).
    """
    for match in pattern.finditer(text):
        clause = _CLAUSE_END.split(text[max(0, match.start() - 80) : match.start()])[-1]
        if not _NEGATION.search(clause):
            return True
    return False


# A claim about what a picture or video shows: who is pictured, what it is a photo of.
_DEPICTS = re.compile(
    r"\b(?:pictured|appears? to be|are seen|is seen|are shown|is shown|selfie|"
    r"(?:photo(?:graph)?|picture|image|video|clip|footage)s? (?:shows?|of))\b",
    re.IGNORECASE,
)
# A passage saying a picture or video itself was made or altered: narrower than
# `_MADE_UP`, because it turns a source to the other side (`_settled`).
_MEDIA_FAKED = re.compile(
    r"\b(?:ai[- ]generated|(?:made|created|generated) (?:with|using|by) "
    r"(?:ai|artificial intelligence)|deep ?fakes?|digitally (?:altered|created|edited|"
    r"manipulated)|morphed|doctored|photoshopped)\b",
    re.IGNORECASE,
)


def depicts(claim: Claim) -> bool:
    """Whether a claim is about what a picture or video shows."""
    return any(_DEPICTS.search(text) for text in (claim.search_text, claim.text) if text)


def _settled(
    item: Evidence, read: str, reading: Any, *, depiction: bool = False
) -> tuple[Evidence | None, str]:
    """What the check's answer makes of one source: the copy to keep, or None, and
    the outcome for the log.

    A source is kept when the two readings agree on its side; the check can confirm a
    support the first reader held back as context, never turn a source to the other
    side. A fact-check or an official denial is still a contradiction: the check
    answers FALSE for those, and they are kept as that.

    A narrower version is, by definition, not "the same assertion", so the check has
    answered PARTLY and "not about the claim" in one breath: its own yes-or-no on
    "smaller version" decides, not `addresses_claim` (2026-09-27).

    Material the check finds genuine but presented out of context is neither side: a
    source explaining that Netanyahu spoke the words while quoting Hasan Piker was
    read as support and kept as support, and a cut clip read TRUE (2026-10-02). It is
    kept as what it is (`OUT_OF_CONTEXT`), never as support; and a contradiction only
    when the passage calls nothing made up (`_MADE_UP`) - a fabricated quote or an
    AI-made picture stays false.
    """
    verdict = reading.verdict
    about = reading.addresses_claim
    supports = read in _SUPPORT_READS
    framed = bool(getattr(reading, "out_of_context", False))
    rejected = f"rejected: read {read}, check said {verdict}, about the claim={about}"

    # A fact-check rated the claim "missing context" or "clipped": kept when the
    # check finds it is about this claim, whatever it makes of the rest.
    if read == "out_of_context":
        if about:
            return item, "kept (out of context)"
        return None, rejected

    # A claim about who or what a picture shows, and a passage saying the picture
    # itself is AI-made or altered: a contradiction, however the first reader read
    # it. An AI selfie of the BRICS leaders was read as "figures who appear to be
    # Putin, Modi, Xi ... are pictured", and France 24's "Viral Putin, Modi and Xi
    # selfie at BRICS summit is AI-generated" was read as support - a fake does show
    # them. The check said FALSE and about this claim for that and three more debunks,
    # and all four were thrown away (2026-10-02). The one place this step turns a
    # source to the other side, and only on the check's own FALSE and the debunk's
    # own words.
    if (
        depiction
        and supports
        and about
        and verdict == "FALSE"
        and _affirmed(_MEDIA_FAKED, f"{item.title or ''}. {item.source_excerpt}")
    ):
        return _as_contradiction(item, reading.reason), (
            "kept (contradicts: the picture itself is called AI-made or altered)"
        )

    if framed and about:
        if supports and not (verdict == "FALSE" and _made_up(item)):
            outcome = "kept (out of context)"
            if read != "supports":
                outcome = f"kept (out of context; read {read})"
            return _as_out_of_context(item, reading.reason), outcome
        # Never a published rating of false ("Alt News rated this False"): it is the
        # fact-checker's own verdict, not a passage this call can read otherwise.
        rating = not item.match_basis.metric.startswith("passage_")
        if read == "contradicts" and not rating and not _made_up(item):
            return (
                _as_out_of_context(item, reading.reason),
                "kept (out of context; read contradicts)",
            )

    if verdict == "TRUE":
        # The check found the passage establishes the claim. A support the first
        # reader called narrower, or held back as someone else's word, is support:
        # "read contextualizes, check said TRUE" threw away 23 reports in nine
        # checks - Rising Kashmir on the Budgam encounter, India Today on the EOS-05
        # launch from Sriharikota, The Hindu on the Koder House fire (2026-10-02).
        if supports and about:
            return _as_support(item), (
                "kept (supports)" if read == "supports" else f"kept (supports; read {read})"
            )
        return None, rejected

    if verdict == "FALSE":
        if read == "contradicts" and about:
            return item, "kept (contradicts)"
        return None, rejected

    # The passage confirms what the claim is about and leaves out only details - the
    # police station, the period, the time of day. Six reports of the 2013 Jhiram
    # Ghati ambush were each rejected for not naming the Darbha police station, and
    # the Guardian and ESPN on City's misstated accounts for not repeating
    # "2009-2018" (2026-10-02). What a source does not mention is unconfirmed by it,
    # not a reason to discard what it does confirm.
    #
    # Never when the check calls it a smaller version: two reports of a proposal,
    # read as narrower, would otherwise have cleared "Govt has approved Rs 5,000 a
    # month for every woman" as true - whatever the check said of stating it
    # differently.
    says_less = (
        supports
        and about
        and not reading.states_differently
        and not reading.other_group
        and not reading.smaller_version
        and getattr(reading, "core_established", False)
    )
    # A narrower reading the check finds states nothing differently: it reports part
    # of the claim and leaves the rest out. Kept as that (`PARTIAL_SCOPE`) - neither a
    # smaller version, which would call a true report misleading, nor support. The
    # Wire, TOI and NIE were narrower versions of "Baghel repeatedly alleged a larger
    # conspiracy" for not saying "repeatedly", and the NDTV report of the Jhiram Ghati
    # sentences read "partly true" (2026-10-02).
    partial = (
        read == "narrower" and about and not reading.states_differently and not reading.other_group
    )

    if verdict == "PARTLY":
        # Read as support, and the check found nothing it states differently - only
        # details it does not mention. What it says matches the claim: India Today on
        # the Aditya-L1 launch, without naming the launch site. Only for a passage
        # the reader found supports the claim itself: a narrower version or someone
        # else's word is support only on the check's own finding (`says_less`).
        if read == "supports" and about and not reading.states_differently:
            return _as_support(item), "kept (supports, says less)"
        # A smaller version of the claim: that version is what it is evidence of, not
        # the claim - "partly true". Asked as its own question, because asked through
        # the verdict the check called a one-time Rs 5,000 payment "FALSE, not about
        # the claim" and it was thrown away (2026-09-28). PARTLY alone is not enough:
        # for "Atal Free Pension Scheme" against the real Atal Pension Yojana the check
        # said PARTLY and, rightly, "not a smaller version" - a scam's borrowed name.
        # And never for another group of people: the PM Internship Scheme's Rs 5,000
        # for interns is no smaller version of "every woman gets Rs 5,000"
        # (`other_group`).
        #
        # "Smaller version" also needs a detail stated differently: it was said of
        # pages that merely said less ("the photographs were also shared", for a
        # claim naming Facebook and X), and of reports that each carried part of a
        # fire officer's account. A smaller version states something smaller - another
        # state, once rather than monthly, a lower amount, a proposal for a decision;
        # leaving a detail out states nothing (`partial`, below). Tamil Nadu's Rs 1,000
        # a month for women heads of families, read as denying "every woman gets Rs
        # 5,000 a month", is a smaller version too: the user decided a real smaller
        # version for the same people makes such a claim partly true (2026-09-28).
        smaller = reading.smaller_version and reading.states_differently and not reading.other_group
        if smaller:
            return _as_narrower(item, reading.reason), "kept (narrower than the claim)"
        # Checked after the smaller version, so a source both readers found smaller
        # stays the smaller version it is.
        if says_less:
            return _as_support(item), "kept (supports, says less)"
        if partial:
            return _as_partial(item, reading.reason), "kept (part of the claim)"
        return None, rejected

    if says_less:
        return _as_support(item), "kept (supports, says less)"
    if partial:
        return _as_partial(item, reading.reason), "kept (part of the claim)"
    return None, rejected


def _as_support(item: Evidence) -> Evidence:
    """A source the check read as establishing the claim, kept as support."""
    if item.direction is Direction.SUPPORTS:
        return item
    _, _, reason = item.match_basis.metric.partition(": ")
    return item.model_copy(
        update={
            "direction": Direction.SUPPORTS,
            "match_basis": MatchBasis(
                metric=f"passage_entailment: {reason}"[:200],
                value=item.match_basis.value,
                threshold=item.match_basis.threshold,
            ),
        }
    )


def _as_narrower(item: Evidence, reason: str) -> Evidence:
    """A support the check read as only part of the claim: kept, as a narrower version."""
    return _marked(item, NARROWER_SCOPE, reason)


def _as_contradiction(item: Evidence, reason: str) -> Evidence:
    """A source the check read as calling the claim's picture made or altered."""
    return item.model_copy(
        update={
            "direction": Direction.CONTRADICTS,
            "match_basis": MatchBasis(
                metric=f"passage_entailment: {reason}"[:200],
                value=item.match_basis.value,
                threshold=item.match_basis.threshold,
            ),
        }
    )


def _as_out_of_context(item: Evidence, reason: str) -> Evidence:
    """A source the check read as finding the claim's material genuine but misframed."""
    return _marked(item, OUT_OF_CONTEXT, reason)


def _as_partial(item: Evidence, reason: str) -> Evidence:
    """A narrower reading the check found states nothing differently: part of the claim."""
    return _marked(item, PARTIAL_SCOPE, reason)


def _marked(item: Evidence, marker: str, reason: str) -> Evidence:
    """The source as context, its metric starting with `marker` and the check's reason."""
    return item.model_copy(
        update={
            "direction": Direction.CONTEXTUALIZES,
            "match_basis": MatchBasis(
                metric=f"{marker}: {reason}"[:200],
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
    # Why it could not run, when the reason was time: no time was left before the
    # deadline, which is not the model provider being down. Both were reported as
    # "model provider unavailable", so a check that ran out of time read as an outage.
    timed_out: bool = False


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
    # A fact-checker's own rating that the material is genuine but misframed says
    # more than a reading of the same page as support or as a denial.
    framed = item.direction is Direction.CONTEXTUALIZES and is_out_of_context(
        item.match_basis.metric
    )
    return (
        -1 if framed else _DIRECTION_RANK.get(item.direction, 1),
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
        # A "contradiction" that gives the claim's own figure as "more than" or "at
        # least" it agrees with the claim instead (`_same_figure`).
        elsewhere |= {
            id(item): "the same figure, given as approximate"
            for item in text
            if id(item) not in elsewhere
            and item.direction is Direction.CONTRADICTS
            and _same_figure(item, claim)
        }
        early = [item for item in text if id(item) in elsewhere]
        text = [item for item in text if id(item) not in elsewhere]
        sided = [item for item in text if _read_as(item) is not None]
        context_only = len(text) - len(sided)
        # What happened to each source, by host, for the log. Counts alone could not
        # answer "why was The Hindu not cited?" without re-running the check.
        outcomes = [
            {"host": _host(item.citation_url), "outcome": "context", "reason": item.finding[:200]}
            for item in text
            if _read_as(item) is None
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
        timed_out = False
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
            timed_out = True
        if answer is None:
            # A support held back as someone else's word stays context unless the
            # check confirms it, and context is not cited.
            return self._finish(
                claim,
                passthrough + [item for item in sided if _read_as(item) != "attributed"],
                explanation=None,
                duplicates=duplicates,
                context_only=context_only,
                rejected=0,
                checked=False,
                timed_out=timed_out,
            )

        kept: list[Evidence] = []
        depiction = depicts(claim)
        for index, item in enumerate(sided):
            reading = answer.readings.get(index)
            host = _host(item.citation_url)
            if reading is None:
                # The call did not say anything about this source. Silence is not a
                # vote of confidence; the page has not been confirmed relevant.
                outcomes.append({"host": host, "outcome": "unmentioned"})
                continue
            read = _read_as(item)
            assert read is not None
            settled, outcome = _settled(item, read, reading, depiction=depiction)
            if settled is not None:
                kept.append(settled)
            outcomes.append(
                {
                    "host": host,
                    "outcome": outcome,
                    "reason": reading.reason[:200],
                    # The check's yes-or-no answers, which decide a narrower version
                    # from a report that only says less: without them a re-test could
                    # not tell which answer kept a source as what (2026-10-02).
                    "flags": _flags(reading),
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
        timed_out: bool = False,
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
            timed_out=timed_out,
            sources=outcomes or [],
        )
        return Verified(
            evidence=weighed,
            explanation=explanation,
            duplicates=duplicates,
            context_only=context_only,
            rejected=rejected,
            checked=checked,
            timed_out=timed_out,
        )


_FLAGS = (
    ("smaller_version", "smaller"),
    ("states_differently", "differs"),
    ("other_group", "other_group"),
    ("core_established", "core"),
    ("out_of_context", "out_of_context"),
)


def _flags(reading: Any) -> str:
    """The check's yes answers for one source, for the log: "smaller,core"."""
    return ",".join(name for field, name in _FLAGS if getattr(reading, field, False)) or "-"


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


# A figure given as approximate: "more than 170", "at least 1,300".
_APPROXIMATE = re.compile(
    r"\b(?:at least|more than|over|nearly|about|around|almost|roughly|upwards of|"
    r"in excess of|some)\s+(\d[\d,]*)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d[\d,]*")


def _same_figure(item: Evidence, claim: Claim) -> bool:
    """Whether a contradicting passage gives the claim's own number as approximate.

    "More than 170 people died in last week's flooding" was read as contradicting "the
    floods killed 170 people", and a true claim read False (2026-09-29): a rounded
    figure, or a toll that rose after the claim's report, is the same count.
    """
    wanted = {n.replace(",", "") for n in _NUMBER.findall(f"{claim.text} {claim.search_text}")}
    if not wanted:
        return False
    return any(
        m.group(1).replace(",", "") in wanted for m in _APPROXIMATE.finditer(item.source_excerpt)
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
    # When the claim says it happened - not a forecast's target year (`event_years`).
    # The target still dates the claim: "500 GW by 2030" is not an undated claim
    # about the shared page's moment ("an earlier occurrence" below), and the 2021
    # reports that set the target are about it.
    years = event_years(said)
    dated = bool(years) or _YEAR.search(said) is not None
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
        and not dated
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
