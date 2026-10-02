"""Verification orchestrator (M40).

The request pipeline. Its whole job is to run one fixed order and never deviate:

    validate → create case → hash → cache probe → governor → extract →
    retrieve evidence → decide → persist ledger → write back → respond

The order is not stylistic. Two steps in it are load-bearing and their position is
the point:

  - **Cache probe before governor.** A repeat submission must cost zero external
    units. Probing after acquiring a unit would spend budget to learn something
    already known, and the M13 gate asserts the zero.
  - **Governor before any provider call.** Every metered call goes through it, so a
    module that "just needs one direct call" is a bug and not a shortcut.

The other property this module owes the rest of the system is honesty about gaps.
A response assembled from partial results must say what was missing — an answer that
silently omits the fact-check nobody could reach reads exactly like an answer where
no fact-check existed, and those are different situations.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.cache.keys import DEFAULT_POLICY_PROFILE, CacheKeyParts
from app.cache.service import CachedVerdict
from app.domain.claim import Claim
from app.domain.enums import (
    Action,
    ClaimStatus,
    ClaimType,
    CoverageExpectation,
    Direction,
    EvidenceKind,
    Importance,
    SourceRisk,
    Verdict,
)
from app.domain.evidence import Advisory, Evidence, is_narrower_scope, is_out_of_context
from app.domain.publishers import registrable_domain
from app.governor.governor import ProviderUnavailable
from app.intake.normalizer import NormalisedIntake
from app.observability.logging import event
from app.orchestration.progress import addresses_claim, current_progress, stance_of
from app.sources.base import (
    SourceCandidate,
    SourceResolver,
    build_evidence,
    check_seconds,
    current_check,
    current_follow_up,
    current_own_pages,
    current_reference_date,
)
from app.sources.corpus import CorroborationSignal
from app.sources.factcheck import shared_review_for
from app.sources.reasoning import REASONER_VERSION
from app.sources.verification import SourceVerification, dedupe, page_key
from app.verdict.engine import (
    FABRICATED_MIN_READ,
    RULE_VERSION,
    CaseDecision,
    Decision,
    blocks_clearance,
    decide,
    fabricated_news,
    is_central,
    roll_up,
    verdict_for,
)
from app.verdict.explain import explain, narrower_note, shared_fact_check_note
from app.verdict.strength import Strength, evidence_strength
from app.verdict.wording import WORDING

logger = logging.getLogger("factify.orchestration")

# The synchronous budget for text, URL, image and PDF (codexplan §11). Video returns
# accepted-with-progress instead of blocking a request for half a minute.
#
# 8 seconds is the target for the lexical path and remains what `within_target`
# reports against, because that is the number the product promised.
TARGET_SECONDS = 8.0

# The deadline actually enforced when a resolver may read sources with a model.
#
# Measured, not guessed: one source of four passages takes **31 seconds** through
# `PassageReasoner`, against a 129ms fetch. Reading is two orders of magnitude
# slower than the word overlap the 8 second budget was written for, so enforcing 8
# here did not make the system fast — it made every reasoned verification abstain
# with "deadline exceeded" while the model was still mid-sentence.
#
# The mobile client's timeout is the real ceiling: past it the server is computing
# an answer nobody is waiting for. It was 45 seconds and this was 40; the client now
# waits 75, and 40 had become the reason links were never checked. A link spends
# 12-25 seconds being read and having its claims extracted before checking starts,
# and on The Hindu's report the reads were cancelled at 34 seconds with every claim
# unchecked. 55 leaves checking its time and still answers well inside the 75.
# Requests that exceed `TARGET_SECONDS` are still reported as over target — the
# promise is not quietly rewritten, it is measured against honestly.
REASONING_TARGET_SECONDS = 55.0

# The least time reading and checking sources gets, however long finding the claims took.
MIN_READING_SECONDS = 40.0

# Kept back from the reading deadline for the source check that follows it. Reading
# used to run to the deadline itself, leaving the check no time at all — so it timed
# out at once and every source reached the verdict unchecked. The check is one model
# call over short excerpts; measured at three to four seconds.
_VERIFY_RESERVE_SECONDS = 6.0

# The same reserve for a check in the background. There the call is made patiently -
# it waits its turn under the model's per-minute ceiling and retries a busy provider
# (app/security/patience.py) - and the claims still reading at the deadline all stop
# at once, so their source checks queue for the model together. Six seconds left
# most of them timed out in that queue, and their sources reached the verdict
# unchecked.
_BACKGROUND_VERIFY_RESERVE_SECONDS = 20.0

# How much longer than its reading deadline a resolver is given before it is cut off
# whole. Pages are cut off individually at the deadline (see `_run_resolver`); this is
# the backstop for a search provider that never answers at all.
_RESOLVER_GRACE_SECONDS = 3.0

# How many resolvers may run at once. Independent producers are concurrent because
# they do not depend on each other; the ceiling exists so a burst of claims cannot
# open forty sockets against six publishers.
DEFAULT_CONCURRENCY = 8

# How many web searches may be in flight at once, across every check. A search is
# paced under the provider's per-minute ceiling and can wait a long time for its
# turn. It used to wait holding one of the slots above, which are for fetching
# pages: a burst of claims' searches took them all, and pages already found sat
# unread behind searches that were only waiting.
_SEARCHES_AT_ONCE = 4

# How many claims of one background check are searched and read at a time. Started
# all at once, a seven-claim article's details took as many search and read slots as
# its headline, and the claims the verdict rests on were the ones still unread at
# the deadline. Three at a time, in order of importance, finishes the main claims
# first; the rest follow as each one is done.
_CLAIMS_AT_ONCE = 3

# The least reading time worth starting a web search for in the background. Started
# with less, its queries are paid for and its pages cut off unread at the deadline:
# a claim that waited its turn behind the main ones spent its credits for nothing.
_MIN_SEARCH_SECONDS = 10.0

# A check someone runs in the background (see `check_seconds`) has this long,
# at most, to search and read every claim. A seven-claim article reads about forty
# pages through the model, paced to the provider's per-minute limits: two to three
# minutes. Five is the ceiling for a provider having a slow day, not the plan.
BACKGROUND_SECONDS = 300.0

# However long reading the input and finding its claims took, a background check
# keeps at least this long to search and read sources afterwards - a post with a
# ten-minute video spends minutes being read before checking starts - and never runs
# past the ceiling, counted from when it started. The ceiling is what the clients
# wait for before they give up on an answer (contract 1.8), so it bounds both.
BACKGROUND_MIN_READING_SECONDS = 150.0
BACKGROUND_CEILING_SECONDS = 420.0

# What still runs after the deadline: deciding each claim, the presence check, the
# roll-up, the ledger and the receipt. The deadline stops this much short of the
# ceiling, so the answer is stored before the apps stop waiting for it - the app
# released today gives up after about four hundred seconds, and the live stream at
# six minutes.
_BACKGROUND_TAIL_SECONDS = 20.0

_IMPORTANCE_ORDER = {
    Importance.HEADLINE: 0,
    Importance.MAIN_THESIS: 1,
    Importance.SUPPORTING_DETAIL: 2,
    Importance.BACKGROUND: 3,
}


class Corroboration(Protocol):
    """Anything that can count independent origins for a claim.

    A protocol rather than a concrete type so the orchestrator does not depend on the
    corpus module, and so a test can count origins without a database.
    """

    async def signal(self, claim: Claim, *, citation_urls: list[str]) -> CorroborationSignal: ...


class VerdictCache(Protocol):
    """The two cache operations the pipeline performs.

    A protocol rather than `CacheService` because that class binds to one database
    connection, and an orchestrator that lives for the process cannot hold one
    connection for the process. `PoolCacheService` satisfies this by checking a
    connection out per operation; the audit's null cache satisfies it by doing
    nothing.
    """

    async def get_verdict(self, parts: CacheKeyParts) -> CachedVerdict | None: ...

    async def put_verdict(
        self,
        parts: CacheKeyParts,
        payload: dict[str, Any],
        *,
        case_id: object | None = None,
        is_negative: bool = False,
        developing: bool = False,
    ) -> None: ...


class CallGovernor(Protocol):
    """The single operation the pipeline needs from the governor."""

    async def try_acquire(self, provider: str) -> object: ...


@dataclass(frozen=True, slots=True)
class SkippedCheck:
    """Something the pipeline could not do, and why.

    Carried into the response so it can say what was not checked. A gap the user
    cannot see is a gap they will read as an absence of findings.
    """

    check: str
    reason: str
    # What kind of gap: "reading" (part of the input could not be read), "deadline"
    # (the check ran out of time), "provider" (an outside service did not answer) or
    # "other". Sent to the clients (contract 1.8) so a gap in reading is shown where
    # what was read is shown, and the time running out is said only when it did.
    kind: str = "other"

    def describe(self) -> str:
        return f"{self.check} was not checked: {self.reason}"


# Called as each claim finishes (done, total), for a check someone is watching.
claim_progress: ContextVar[Callable[[int, int], None] | None] = ContextVar(
    "claim_progress", default=None
)

# The time the check running now actually had, set for the length of one. Its deadline
# moves with how long reading the input took (`Orchestrator.verify`), so the time a
# claim ran out of is said as it was, not as the budget it started from.
_check_budget: ContextVar[float | None] = ContextVar("check_budget", default=None)


def _in_background() -> bool:
    """Whether the check running now is one the app follows in the background."""
    return check_seconds.get() is not None


def _verify_reserve() -> float:
    """How long before the deadline reading stops, so the source check can run."""
    return _BACKGROUND_VERIFY_RESERVE_SECONDS if _in_background() else _VERIFY_RESERVE_SECONDS


@dataclass(slots=True)
class ClaimOutcome:
    """One claim, its decision, its evidence and its score."""

    claim: Claim
    decision: Decision
    strength: Strength
    evidence: list[Evidence] = field(default_factory=list)
    # One or two plain sentences on what the verified sources show, written by the
    # source check. None when no check ran.
    explanation: str | None = None
    # Whether the open web was searched for this claim: "searched", "not_searched"
    # (below the per-check cap), "timed_out", or "unavailable" (the search provider
    # could not be reached or refused every query). An unconfirmed claim that was never
    # searched said "we couldn't find reliable sources" all the same.
    search: str = "searched"
    # How many candidate pages were read for it, whatever they turned out to say.
    looked_at: int = 0


@dataclass(slots=True)
class VerificationResult:
    """Everything one verification produced.

    `advisories` is a separate field from every evidence list on purpose — the two
    types share no base class, and keeping them apart here means no assembly step can
    accidentally concatenate them.
    """

    case_id: UUID
    content_hash: str
    action: Action
    case_decision: CaseDecision
    claims: list[ClaimOutcome] = field(default_factory=list)
    advisories: list[Advisory] = field(default_factory=list)
    skipped: list[SkippedCheck] = field(default_factory=list)
    from_cache: bool = False
    elapsed_ms: int = 0
    rule_version: str = RULE_VERSION
    # The case the cached verdict was originally computed under, set only on a
    # cache hit. The hit itself writes no ledger row — rewriting would record a
    # second case for one verification — so this is the id under which the claims,
    # evidence and verdicts actually exist. The endpoint uses it to serve the full
    # stored result instead of an action with nothing behind it.
    source_case_id: UUID | None = None

    # Set by the ledger once a receipt has been issued and stored. Carried on the
    # result rather than looked up by the endpoint so the response can only ever
    # offer a receipt that actually exists.
    receipt_id: str | None = None

    @property
    def evidence(self) -> list[Evidence]:
        """Every citation across every claim, in claim order."""
        return [item for outcome in self.claims for item in outcome.evidence]

    @property
    def is_complete(self) -> bool:
        """Whether every intended check actually ran."""
        return not self.skipped

    @property
    def within_target(self) -> bool:
        return self.elapsed_ms <= TARGET_SECONDS * 1000

    def completeness_note(self) -> str | None:
        """One line naming what was missed, or nothing when the run was complete."""
        if not self.skipped:
            return None
        return "Not everything could be checked. " + " ".join(s.describe() for s in self.skipped)


# What an undecided case says when a claim that would be national news was searched
# for in full and nothing reliable reports it. A forward saying the Prime Minister
# had announced Rs 5,000 a month for every student came back "Unconfirmed" with the
# app's generic line, which reads like "we don't know" about something that - were it
# true - every newspaper and the government's own sites would carry.
#
# Still not FALSE: nothing refutes it, and a verdict of False is only ever shown
# above the sources that establish it. So it is said, not decided: a fixed sentence,
# never a model's words, and only when nothing at all supports the claim and the
# search ran to the end.
_UNREPORTED = {
    "en": (
        "We searched official sources and reliable news outlets and found nothing "
        "reporting this. Something this big would be widely reported if it were true, "
        "so treat it as likely false until an official source confirms it."
    ),
    "hi": (
        "हमने आधिकारिक स्रोतों और भरोसेमंद समाचार माध्यमों में खोजा, पर कहीं भी इसकी "
        "कोई ख़बर नहीं मिली। अगर यह सच होता तो इसकी ख़बर हर जगह होती, इसलिए जब तक कोई "
        "आधिकारिक स्रोत इसकी पुष्टि न करे, इसे संभवतः झूठा मानें।"
    ),
}


# Time a follow-up round needs to be worth starting: a search and a few reads.
_FOLLOW_UP_MIN_SECONDS = 45.0

# How recent a shared news page must be for what it reports to be "too recent to
# confirm yet": published today or yesterday.
_FRESH_DAYS = 1


def _fresh_news(claim: Claim) -> bool:
    """A claim about an event, from a news page the person shared that was published
    in the last day or so, and naming no earlier year."""
    published = current_reference_date.get()
    if published is None or claim.claim_type is not ClaimType.EVENT:
        return False
    today = datetime.now(UTC).date()
    if not 0 <= (today - published).days <= _FRESH_DAYS:
        return False
    years = {int(year) for year in _YEAR.findall(claim.search_text)}
    return all(year >= today.year for year in years)


_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def _unreported_note(
    claim: Claim, evidence: list[Evidence], *, reported: bool = False
) -> str | None:
    """ "Nothing reports this, so treat it as likely false" - only where that follows.

    It follows for a claim the message rests on, which would be news if it were true.
    It does not for a detail, and not when the page the person shared is itself a
    publisher we trust ([reported]): then the claim IS reported, by them. ISRO's own
    Chandrayaan-3 page had its launch-orbit detail called "likely false" because no
    other outlet repeated the numbers (2026-09-28).

    Nor when anything found reports on the claim at all, whichever way: a source that
    contradicts it, or shows a smaller version, has reported the event. "Found nothing
    reporting this" stood beside The Quint's debunk of the same forward (2026-10-02).
    And never for an opinion or a forecast, which nothing is expected to report: an
    unchecked "America deserved 9-Eleven" was called likely false.
    """
    if reported or not blocks_clearance(claim) or not claim.is_checkable:
        return None
    if claim.coverage_expectation is not CoverageExpectation.HIGH:
        return None
    if any(_reports_on(item) for item in evidence):
        return None
    language = claim.language or "en"
    return _UNREPORTED.get(language) or WORDING.get(language, {}).get(
        "pipeline.unreported", _UNREPORTED["en"]
    )


def _reports_on(item: Evidence) -> bool:
    """Whether a source reports on the claim: either way, in a smaller version, or as
    genuine material shown out of context."""
    return item.direction in (Direction.SUPPORTS, Direction.CONTRADICTS) or (
        item.direction is Direction.CONTEXTUALIZES
        and (
            is_narrower_scope(item.match_basis.metric) or is_out_of_context(item.match_basis.metric)
        )
    )


# Every wording of the note, to recognise it on a finished claim.
_UNREPORTED_TEXTS = frozenset(_UNREPORTED.values()) | frozenset(
    text for words in WORDING.values() if (text := words.get("pipeline.unreported"))
)


def _story_reported(outcomes: list[ClaimOutcome]) -> bool:
    """Whether reliable sources confirm what the piece is about: its headline or main
    thesis is supported.

    Only those. A supported detail does not vouch for the piece around it: a fake
    scheme is hung on a real programme on purpose, and "apply on the National
    Scholarship Portal", supported by the portal itself, must leave "likely false" on
    the invented "National Sports Scholarship 2026-27" it was attached to.
    """
    return any(
        blocks_clearance(outcome.claim) and outcome.decision.status is ClaimStatus.SUPPORTED
        for outcome in outcomes
    )


def _without_unreported_notes(outcomes: list[ClaimOutcome]) -> None:
    """Drop "nothing reports this" from every claim of a piece whose story is confirmed.

    Said of one claim, the sentence reads as a verdict on the piece: beside a headline
    that Reuters and the BBC carry, "treat it as likely false" about a detail of the
    same story is not true of it (2026-10-02).
    """
    if not _story_reported(outcomes):
        return
    for outcome in outcomes:
        if outcome.explanation in _UNREPORTED_TEXTS:
            outcome.explanation = None


def _not_own(evidence: list[Evidence], own_pages: frozenset[str]) -> list[Evidence]:
    """The evidence, less anything from the outlets whose pages the person submitted.

    A submitted article cannot confirm itself. Searching for the claims of a Times of
    India kabaddi report found that same report, and it stood as the headline claim's
    only supporting source — the article, quoted back as evidence that the article is
    right. For a fabricated page that search can reach, the same loop would support
    every claim it makes.

    Nor can its outlet. A CNN report's claims were "confirmed" by cnn.com,
    us.cnn.com and edition.cnn.com — CNN's own live blog and follow-ups — and one
    detail stood on CNN plus one other outlet, counted as two. BOOM's fact-check had
    two other BOOM pages as the only support for its main claim. The same newsroom
    repeating itself is one witness, and the question a reader asks is whether
    anyone else reports it.
    """
    if not own_pages:
        return evidence
    own_outlets = {domain for key in own_pages if (domain := registrable_domain(key))}
    return [
        item
        for item in evidence
        if page_key(item.citation_url) not in own_pages
        and registrable_domain(item.citation_url) not in own_outlets
    ]


class Orchestrator:
    """Runs the fixed order. The only place that order is expressed."""

    def __init__(
        self,
        *,
        cache: VerdictCache,
        governor: CallGovernor,
        resolvers: list[SourceResolver],
        extractor_version: str,
        model_id: str = "",
        concurrency: int = DEFAULT_CONCURRENCY,
        corroboration: Corroboration | None = None,
        verification: SourceVerification | None = None,
        translator: Any | None = None,
        presence: Any | None = None,
    ) -> None:
        self._cache = cache
        # Reads a company's own list of locations for a claim that it opened one
        # somewhere (app/sources/official_presence.py). Optional.
        self._presence = presence
        # Translates a claim made in another language into English before its sources
        # are sought (app/extraction/translate.py). Optional: without it, a claim is
        # searched in its own words only.
        self._translator = translator
        # Optional for the same reason as corroboration. Without it, sources are still
        # deduplicated but not checked for relevance.
        self._verification = verification
        self._governor = governor
        self._resolvers = resolvers
        self._extractor_version = extractor_version
        self._model_id = model_id
        self._semaphore = asyncio.Semaphore(concurrency)
        # Web searches have their own ceiling, so one waiting for its turn under the
        # provider's pacing never holds a slot a page could be read in.
        self._search_gate = asyncio.Semaphore(_SEARCHES_AT_ONCE)
        # Optional so existing callers — the audit runner, every unit test — keep
        # working unchanged and simply count no origins.
        self._corroboration = corroboration
        # Whether any resolver reads sources with a model, which decides the
        # deadline. Asked of the resolvers rather than configured separately, so the
        # budget cannot drift out of step with what the pipeline actually does.
        self._reads_sources = any(getattr(r, "reads_sources", False) for r in resolvers)

    @property
    def resolvers(self) -> list[SourceResolver]:
        return list(self._resolvers)

    def with_resolvers(self, resolvers: list[SourceResolver]) -> Orchestrator:
        """A view of this orchestrator over a different resolver set.

        Exists for media: its resolvers carry per-request findings and cannot be
        process-lifetime. Everything else — cache, governor, corroboration, **and the
        semaphores** — is shared, because the fetch and search ceilings only mean
        anything if every in-flight request counts against the same ones.
        """
        clone = Orchestrator(
            cache=self._cache,
            governor=self._governor,
            resolvers=resolvers,
            extractor_version=self._extractor_version,
            model_id=self._model_id,
            corroboration=self._corroboration,
            verification=self._verification,
            presence=self._presence,
        )
        clone._semaphore = self._semaphore
        clone._search_gate = self._search_gate
        return clone

    def _cache_key(self, intake: NormalisedIntake) -> CacheKeyParts:
        """The verdict-cache key for an input — computable before anything is extracted."""
        return CacheKeyParts(
            # `cache_identity` rather than the primary object's hash: for a URL it is
            # the canonicalised address, so two people sharing the same article with
            # different tracking parameters hit one entry instead of two.
            content_hash=intake.cache_identity,
            policy_profile=DEFAULT_POLICY_PROFILE,
            rule_version=RULE_VERSION,
            extractor_version=self._extractor_version,
            language=intake.language.language.value,
            model_id=self._model_id,
            reader_version=REASONER_VERSION,
            retrieval_version=self._retrieval_version(),
        )

    def _retrieval_version(self) -> str:
        """Every configured resolver's name and version, in a stable order.

        Sorted because resolver order is a composition detail and must not change
        the key; taken from the resolvers themselves because `SourceResolver`
        already declares both fields, so this keeps step with a new resolver
        without anything here being edited.
        """
        return ",".join(
            sorted(
                f"{getattr(r, 'name', type(r).__name__)}:{getattr(r, 'version', '-')}"
                for r in self._resolvers
            )
        )

    async def cached(self, intake: NormalisedIntake, *, case_id: UUID) -> VerificationResult | None:
        """The stored verdict for this input, or `None` — asked before any work is done.

        `verify` probes the cache too, but only after its caller has already extracted
        claims: for text that is a metered model call, for a link a page fetch plus
        that call, spent on every repeat just to learn the answer was stored. The key
        depends only on the input and the versions, never on the claims, so the probe
        can move to the front — and a repeat then costs nothing external at all, which
        is what the M13 gate always claimed.
        """
        started = time.perf_counter()
        stored = await self._cache.get_verdict(self._cache_key(intake))
        if stored is None:
            return None
        return self._from_cache(stored, case_id=case_id, intake=intake, started=started)

    async def verify(
        self,
        intake: NormalisedIntake,
        *,
        case_id: UUID,
        claims: list[Claim],
        advisories: list[Advisory] | None = None,
        source_risk: SourceRisk = SourceRisk.UNKNOWN,
        started_at: float | None = None,
        fresh: bool = False,
        own_pages: frozenset[str] = frozenset(),
        synthetic: Callable[[], Awaitable[bool]] | None = None,
        noted: Sequence[SkippedCheck] = (),
        partial_input: bool = False,
    ) -> VerificationResult:
        """Run one verification end to end.

        `synthetic`, for an uploaded picture or video, says whether its own checks found
        it AI-made. Asked only when a claim could make it matter (`_fabricated`).

        `fresh` skips the stored verdict: a person pressed "Check again", and the
        answer from an hour ago is exactly what they are asking to replace.

        `own_pages` are the pages the person submitted — a link, or a link inside a
        message. They are never evidence for their own claims (see `_not_own`).

        `started_at` is when the request arrived, when the caller knows it. The budget
        is the person's wait, and extraction happened before this was called.

        `noted` is what the caller already knows was not checked - part of the input
        that could not be read. It is reported with everything this run skips, and it
        keeps the run out of the cache: a post read in part must not be served as the
        answer to the whole post. `partial_input` says the person asked to check what
        could be read all the same, and holds the answer back from TRUE (`roll_up`).

        Claims arrive already extracted: extraction is upstream because it has its own
        caching and its own provider budget, and threading it through here would put a
        second metered call inside a function whose job is to sequence, not to fetch.
        """
        started = started_at if started_at is not None else time.perf_counter()
        # What the caller could not read goes first, so `cacheable` sees it: it was
        # added after this returned, and a partly read link was cached as if whole.
        skipped: list[SkippedCheck] = list(noted)
        if partial_input and not any(item.kind == "reading" for item in skipped):
            # Checked from part of the input with no gap named: name one, so the
            # answer still says so and is still kept out of the cache.
            skipped.append(
                SkippedCheck(
                    check="input", reason="only part of the input could be read", kind="reading"
                )
            )

        # Cache probe, before the governor and before any provider. A repeat costs
        # nothing external; the M13 gate asserts exactly this.
        cache_key = self._cache_key(intake)
        cached = None if fresh else await self._cache.get_verdict(cache_key)
        if cached is not None:
            return self._from_cache(cached, case_id=case_id, intake=intake, started=started)

        own = set(own_pages)
        if intake.primary.source_url:
            own.add(page_key(intake.primary.source_url))
        # Whether a page the person shared comes from a publisher we trust: its claims
        # are then reported, whatever else is found (see `_unreported_note`).
        verification = self._verification
        reported = verification is not None and any(
            verification.trusted(f"https://{key}") for key in own
        )

        # The budget becomes a deadline here, not a wish. It was declared and
        # measured but never enforced, and real requests ran to 90 seconds — past
        # the mobile client's own 45 second timeout, so the server was still working
        # on answers nobody was waiting for.
        #
        # Which budget depends on what the resolvers are allowed to do. Reading a
        # source with a model measures 31 seconds; word overlap measures
        # milliseconds. One deadline for both would either cut every reasoned answer
        # off mid-call or let every lexical one dawdle.
        # A check run in the background has the time to read everything; one a
        # person waits on in a single request has what that request can hold.
        background = check_seconds.get()
        budget: float | None = None
        if background is not None and self._reads_sources:
            # Its budget, but never less than a fixed time to search and read after
            # the input was read and its claims found, and never past the ceiling the
            # apps wait for (contract 1.8). A post with a ten-minute video spends
            # minutes being read before checking starts; counted against the same
            # five minutes, it would have left the claims almost nothing.
            deadline = min(
                max(started + background, time.perf_counter() + BACKGROUND_MIN_READING_SECONDS),
                started + BACKGROUND_CEILING_SECONDS - _BACKGROUND_TAIL_SECONDS,
            )
            budget = deadline - started
        else:
            reading = background if background is not None else REASONING_TARGET_SECONDS
            deadline = started + (reading if self._reads_sources else TARGET_SECONDS)
            # Reading always gets its own time after the claims are found. Finding
            # them in a linked page takes about twenty seconds, and counting that
            # against the same budget left too little to read anything: a fresh ISRO
            # link came back with every web page unread (2026-09-28).
            if self._reads_sources:
                deadline = max(deadline, time.perf_counter() + MIN_READING_SECONDS)
                budget = deadline - started

        claims = await self._in_english(claims)

        check = current_check.set(str(case_id))
        shared = current_own_pages.set(frozenset(own))
        had = _check_budget.set(budget)
        try:
            outcomes = await self._resolve_all(
                claims,
                skipped=skipped,
                deadline=deadline,
                own_pages=frozenset(own),
                reported=reported,
            )
        finally:
            _check_budget.reset(had)
            current_own_pages.reset(shared)
            current_check.reset(check)
            for resolver in self._resolvers:
                end_check = getattr(resolver, "end_check", None)
                if end_check is not None:
                    end_check(str(case_id))
        _without_unreported_notes(outcomes)

        case_decision = roll_up(
            [(outcome.claim, outcome.decision) for outcome in outcomes],
            source_risk=source_risk,
            partial_input=partial_input,
        )
        fabricated = await self._fabricated(outcomes, case_decision, synthetic)
        if fabricated is not None:
            case_decision = fabricated

        result = VerificationResult(
            case_id=case_id,
            content_hash=intake.primary.sha256,
            action=case_decision.action,
            case_decision=case_decision,
            claims=outcomes,
            advisories=list(advisories or []),
            skipped=skipped,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

        event(
            logger,
            "verification complete",
            module="orchestration",
            outcome="ok",
            action=case_decision.action.value,
            claims=len(outcomes),
            evidence=len(result.evidence),
            skipped=len(skipped),
            # Which checks, and why: a count could not say what ran out of time.
            skipped_checks=[f"{item.check}: {item.reason}" for item in skipped][:10],
            elapsed_ms=result.elapsed_ms,
            within_target=result.within_target,
        )

        # Write-back — the half of M13 that was missing. `get_verdict` was probed on
        # every request while `put_verdict` had no caller anywhere, so the cache was
        # permanently empty and every repeat submission paid the full price. The
        # probe asserted "a repeat costs zero"; nothing made it true.
        #
        # Only complete runs are cached, the same rule pre-warming follows: caching a
        # partial run would store a provider outage as the answer and serve it all
        # day. A write failure is logged and swallowed — losing a cache entry must
        # never lose the verdict that was already computed.
        if cacheable(result) and outcomes:
            try:
                await self._cache.put_verdict(
                    cache_key,
                    {
                        "action": result.action.value,
                        "action_reason": result.case_decision.reason,
                        # The case id travels in the payload, NOT in the row's
                        # `case_id` column. The column is a foreign key to
                        # `verification_case`, and the ledger writes that row *after*
                        # this method returns — the fixed order puts write-back
                        # before persist — so using the column violated the
                        # constraint and every cache write failed silently. The
                        # payload copy has no constraint to violate at write time,
                        # and by any later read the ledger row exists.
                        "case_id": str(case_id),
                    },
                    case_id=None,
                    is_negative=result.action is Action.SEND_TO_REVIEW,
                    developing=developing(result),
                )
            except Exception as error:
                event(
                    logger,
                    "verdict cache write failed; result returned uncached",
                    module="orchestration",
                    outcome="degraded",
                    failure_reason=f"{type(error).__name__}: {error}",
                    level=logging.WARNING,
                )

        return result

    def _from_cache(
        self,
        cached: CachedVerdict,
        *,
        case_id: UUID,
        intake: NormalisedIntake,
        started: float,
    ) -> VerificationResult:
        """Rebuild a result from a stored payload.

        The action is read from the payload rather than recomputed. A stored verdict
        whose payload has no action is treated as unusable and routed to review — a
        cache entry that cannot say what it decided must not be allowed to default to
        anything, least of all to something reassuring.
        """
        raw_action = cached.payload.get("action")
        try:
            action = Action(str(raw_action))
        except ValueError:
            action = Action.SEND_TO_REVIEW

        # The case the verdict was originally recorded under. Older cache rows
        # carry no case id — they predate the field — and parse to `None`, which
        # downstream reads as "serve the thin result", exactly what those rows hold.
        source_case_id: UUID | None = None
        try:
            source_case_id = UUID(str(cached.payload["case_id"]))
        except (KeyError, ValueError):
            source_case_id = None

        age = int(cached.age.total_seconds())
        event(
            logger,
            "verification served from cache",
            module="orchestration",
            outcome="ok",
            cache="hit",
            age_s=age,
            usable=raw_action is not None,
            ledger_backed=source_case_id is not None,
        )

        # The original rollup reason when the payload carries one. The staleness
        # signal does not belong in this sentence — `from_cache` and `retrieved_at`
        # already say it, and the interface renders both.
        stored_reason = cached.payload.get("action_reason")
        if raw_action is None:
            reason = "A stored result was found but could not be read; routed for review."
        elif isinstance(stored_reason, str) and stored_reason:
            reason = stored_reason
        else:
            reason = f"Previously verified {age}s ago; the stored result was reused unchanged."

        return VerificationResult(
            case_id=case_id,
            content_hash=intake.primary.sha256,
            action=action,
            case_decision=CaseDecision(
                action=action,
                rule_id="cache",
                reason=reason,
                rule_version=cached.rule_version,
                verdict=verdict_for(action),
            ),
            from_cache=True,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            source_case_id=source_case_id,
        )

    async def _resolve_all(
        self,
        claims: list[Claim],
        *,
        skipped: list[SkippedCheck],
        deadline: float | None = None,
        own_pages: frozenset[str] = frozenset(),
        reported: bool = False,
    ) -> list[ClaimOutcome]:
        """Resolve every claim, bounded by the concurrency ceiling.

        Every claim is searched and read. They start in order of importance - first
        each claim that can decide the verdict (`is_central`: the headline, the
        main thesis, anything of critical severity), then the rest - so when
        slots are scarce the claims that decide the answer are not the ones waiting.
        The ranking is stable, so equally ranked claims keep the extractor's order.

        In the background they are also taken a few at a time (`_CLAIMS_AT_ONCE`), so
        the main claims are finished first rather than merely started first. The
        tasks are created in ranked order and the gate hands out its places in the
        order they were asked for, so no other ordering is needed. A check someone
        waits on in one request still starts every claim at once: it has no time for
        claims to wait their turn.
        """
        if not claims:
            return []

        unranked = len(_IMPORTANCE_ORDER)
        ranked = sorted(
            range(len(claims)),
            key=lambda index: (
                not is_central(claims[index]),
                _IMPORTANCE_ORDER.get(claims[index].importance, unranked),
            ),
        )

        watching = current_progress.get()
        if watching is not None:
            await watching.step("search")

        # Progress, for a check someone is watching: one tick per finished claim.
        report = claim_progress.get()
        finished = 0
        if report is not None:
            report(0, len(claims))

        # Per check: one check's claims never wait behind another's.
        gate = asyncio.Semaphore(_CLAIMS_AT_ONCE) if _in_background() else None

        async def _resolved(claim: Claim) -> ClaimOutcome:
            return await self._resolve_claim(
                claim,
                skipped=skipped,
                deadline=deadline,
                own_pages=own_pages,
                reported=reported,
            )

        async def _counted(claim: Claim) -> ClaimOutcome:
            nonlocal finished
            if gate is None:
                outcome = await _resolved(claim)
            else:
                async with gate:
                    outcome = await _resolved(claim)
            finished += 1
            if report is not None:
                report(finished, len(claims))
            return outcome

        # Started most important first; answered in the extractor's order.
        tasks = {index: asyncio.ensure_future(_counted(claims[index])) for index in ranked}
        try:
            return [await tasks[index] for index in range(len(claims))]
        finally:
            for task in tasks.values():
                task.cancel()

    async def _fabricated(
        self,
        outcomes: list[ClaimOutcome],
        case: CaseDecision,
        synthetic: Callable[[], Awaitable[bool]] | None,
    ) -> CaseDecision | None:
        """FALSE for an AI-made picture or video passing off an unreported world event
        as news (`fabricated_news`), or None to leave the case as it was decided."""
        if synthetic is None or case.verdict is not Verdict.UNCONFIRMED:
            return None
        if any(o.decision.status is ClaimStatus.SUPPORTED for o in outcomes):
            return None
        unreported = [
            o
            for o in outcomes
            if o.decision.status is ClaimStatus.UNVERIFIED
            and not o.decision.conflicting
            and o.claim.claim_type in (ClaimType.EVENT, ClaimType.STATISTIC)
            and o.claim.coverage_expectation is CoverageExpectation.HIGH
            and is_central(o.claim)
            and not o.claim.within_developing_window
            and o.search == "searched"
            and o.looked_at >= FABRICATED_MIN_READ
            and not any(e.direction is Direction.SUPPORTS for e in o.evidence)
        ]
        if not unreported:
            return None
        try:
            made_by_ai = await synthetic()
        except Exception:  # the picture's checks failing leaves the answer as it was
            logger.exception("the picture's checks could not be read for the case")
            return None
        if not made_by_ai:
            return None
        main = unreported[0]
        event(
            logger,
            "fabricated news",
            module="orchestration",
            outcome="ok",
            claim=main.claim.text[:120],
            pages_read=main.looked_at,
        )
        return fabricated_news(main.claim.text, main.looked_at)

    async def _in_english(self, claims: list[Claim]) -> list[Claim]:
        """Each claim not made in English, with its English translation beside it.

        A Tamil forward searched only in Tamil finds Tamil pages; the fact-check of it
        is as likely to be in English. The translation is used to search and to read,
        never shown as the claim. A translation that fails leaves the claim as it was.
        """
        translator = self._translator
        if translator is None:
            return claims

        async def translated(claim: Claim) -> Claim:
            if claim.english_text or (claim.language or "en") in ("en", "hi-Latn", "und"):
                return claim
            english = await translator.translate(claim.text, target="en")
            if english is None or not english.text.strip():
                return claim
            return claim.model_copy(update={"english_text": english.text.strip()})

        return list(await asyncio.gather(*(translated(claim) for claim in claims)))

    async def _resolve_claim(
        self,
        claim: Claim,
        *,
        skipped: list[SkippedCheck],
        deadline: float | None = None,
        own_pages: frozenset[str] = frozenset(),
        reported: bool = False,
    ) -> ClaimOutcome:
        """Gather evidence for one claim, then decide on it.

        `decide` and `evidence_strength` are both called here and neither is
        bypassable: there is no branch in this function that produces a status any
        other way.

        Evidence is gathered in two stages, cheapest first. The primary resolvers — the
        local corpus and published fact-checks — run together. A **fallback** resolver
        (`fallback = True`: the open-web search, a metered search call plus a model
        read per source) runs only when their evidence does not already decide the
        claim. A published adjudication is decisive on its own, so reading five more
        web pages after one would spend search and model calls to reach the same
        verdict. This changes what is *consulted*, never how anything is decided: the
        final `decide` still runs over every citation gathered.
        """
        primary = [r for r in self._resolvers if not getattr(r, "fallback", False)]
        fallback = [r for r in self._resolvers if getattr(r, "fallback", False)]

        # A shared fact-check is not the claimant of the claim it examines; it is that
        # claim's adjudicator, and its rating is the evidence (`current_shared_review`).
        # For every other claim it is still the person's own page.
        shared = shared_review_for(claim)
        if shared is not None:
            own_pages = frozenset(own_pages - {page_key(shared.record.url)})

        # This claim's own gaps and page count, to say what was done for it.
        mine: list[SkippedCheck] = []
        looked = [0]
        # Set when this claim's search was not started for want of time (`_run_stage`).
        late = [False]
        evidence: list[Evidence]
        if self._reading_left(deadline) <= 0:
            # Its turn (`_CLAIMS_AT_ONCE`) came only after reading had to stop. Read,
            # it ran past the deadline in waves of three - each of its stages given
            # its two-second floor and the grace after it - and its search was said
            # to be skipped twice, once for the round it never had. It is decided
            # from nothing, and said once to have run out of time.
            mine.extend(self._too_late(fallback or primary))
            late[0] = True
            evidence = []
        else:
            evidence = await self._run_stage(
                primary, claim, skipped=mine, deadline=deadline, tally=looked
            )

        # Corroboration is counted after the evidence exists and before anything
        # decides. Rule 4 reads `independent_origin_count` off the claim, and nothing
        # in this codebase ever wrote it: the field was read and never set, so a claim
        # carried by several independent outlets still fell through to
        # `rule.insufficient_origins`. The count must come from the citations rather
        # than from what retrieval shortlisted — an earlier version counted the
        # shortlist and handed the engine "6 independent origins" for a claim only one
        # document actually supported.
        #
        # Counted into a scratch list first, so a recount after the fallback stage
        # cannot report the same corroboration failure twice.
        scratch: list[SkippedCheck] = []
        counted = await self._count_origins(claim, evidence=evidence, skipped=scratch)

        searched = False
        if fallback and not late[0] and not decide(counted, evidence).status.is_decisive:
            evidence.extend(
                await self._run_stage(
                    fallback, claim, skipped=mine, deadline=deadline, tally=looked, late=late
                )
            )
            searched = not late[0]
        elif fallback and not late[0]:
            event(
                logger,
                "fallback resolvers not consulted",
                module="orchestration",
                outcome="ok",
                reason="already decisive",
            )

        evidence = _not_own(evidence, own_pages)

        # Every source is verified against the claim before anything decides on it:
        # one citation per page, only sources that take a side, and a second opinion
        # on whether each is about this claim at all. See `app/sources/verification.py`.
        evidence, explanation = await self._verify_sources(
            claim, evidence, skipped=skipped, deadline=deadline
        )

        # Verification can remove the very source that made the first stage look
        # decided, which is exactly when the open web was skipped. Search now rather
        # than answer from nothing.
        if fallback and not searched and not late[0]:
            counted = await self._count_origins(claim, evidence=evidence, skipped=[])
            if not decide(counted, evidence).status.is_decisive:
                evidence.extend(
                    await self._run_stage(
                        fallback, claim, skipped=mine, deadline=deadline, tally=looked, late=late
                    )
                )
                searched = not late[0]
                evidence = _not_own(evidence, own_pages)
                evidence, explanation = await self._verify_sources(
                    claim, evidence, skipped=skipped, deadline=deadline
                )

        # One more, sharper round for a claim the piece rests on that the first round
        # left undecided: the model writes up to two queries from what the pages said,
        # and a few more pages are read (`current_follow_up`). Only for such claims, so
        # the extra searches go where they can change the answer.
        if fallback and searched and is_central(claim):
            counted = await self._count_origins(claim, evidence=evidence, skipped=[])
            if not decide(counted, evidence).status.is_decisive:
                more = await self._follow_up(
                    fallback, claim, evidence, skipped=mine, deadline=deadline, tally=looked
                )
                if more:
                    evidence.extend(more)
                    evidence = _not_own(evidence, own_pages)
                    evidence, explanation = await self._verify_sources(
                        claim, evidence, skipped=skipped, deadline=deadline
                    )

        scratch = []
        counted = await self._count_origins(claim, evidence=evidence, skipped=scratch)
        skipped.extend(scratch)
        skipped.extend(mine)

        # A search that could not run is not a search that found nothing. With the
        # Tavily plan used up (HTTP 432 on every query), a true tweet about the Rs 2000
        # notes read "We searched official sources and reliable news outlets and found
        # nothing reporting this... treat it as likely false" - not one page had been
        # searched.
        search_names = {getattr(r, "name", type(r).__name__) for r in fallback}
        search_failed = searched and any(
            gap.check in search_names and "deadline" not in gap.reason for gap in mine
        )
        if any("deadline" in gap.reason for gap in mine):
            search = "timed_out"
        elif search_failed:
            search = "unavailable"
        else:
            search = "searched"

        decision = decide(counted, evidence)

        # A claim that a company opened a showroom or office somewhere, left undecided:
        # the company's own list of locations, when it leaves the place out, is the
        # one source that would know (rule 3d, app/sources/official_presence.py). Not
        # for a claim any source disagrees about, nor for news too fresh to be listed.
        if (
            self._presence is not None
            and search == "searched"
            and claim.is_checkable
            and not decision.status.is_decisive
            and not decision.conflicting
            and not _fresh_news(counted)
        ):
            absent = await self._presence.check(counted)
            if absent is not None:
                evidence.append(absent)
                decision = decide(counted, evidence)

        # News too fresh for others to have reported it yet. A claim from a news page
        # the person shared, published today or yesterday, that nothing confirms or
        # contradicts is "too recent to confirm", not "unconfirmed": Hindustan Times on
        # a scheme launched that morning had four claims confirmed and its headline
        # read Unconfirmed (2026-09-28). Only after deciding, and only an undecided
        # claim, so nothing already confirmed is held back by it.
        if not decision.status.is_decisive and _fresh_news(counted):
            counted = counted.model_copy(update={"within_developing_window": True})
            decision = decide(counted, evidence)

        # A plain explanation is shown only under a verdict it can agree with.
        #
        # The source check writes one for every claim, including undecided ones, and
        # on an undecided claim it can say the opposite of the badge above it. For the
        # scam "National Sports Scholarship", it matched a PIB release about the real
        # National Scholarship Portal and wrote "pib.gov.in confirms the National
        # Sports Scholarship portal is open" — under UNCONFIRMED, where the two-origin
        # rule had correctly declined to call it true. The app says what UNCONFIRMED
        # means in its own words instead.
        if not decision.status.is_decisive:
            explanation = narrower_note(evidence, language=claim.language) or (
                _unreported_note(claim, evidence, reported=reported)
                if search == "searched"
                else None
            )
        else:
            # Written from what decided the claim - its source, named and quoted - and
            # never by the model (app/verdict/explain.py).
            explanation = (
                shared_fact_check_note(
                    evidence,
                    decision.supporting_evidence_ids,
                    rating=shared.record.rating or "",
                    certified=shared.certified,
                    language=claim.language,
                )
                if shared is not None
                else None
            ) or explain(
                decision.status,
                evidence,
                decision.supporting_evidence_ids,
                language=claim.language,
            )

        # Strength counts the evidence that *carries* this verdict, which is not
        # always the evidence the decision counted.
        #
        # `counted` holds supporting origins only, and deliberately: rule 4 asks
        # whether enough independent outlets carry a claim, and a citation that
        # contradicts it is not corroboration for it. But strength answers a
        # different question — how independent is the evidence this verdict rests
        # on — and feeding it the supporting count made a contradicted claim report
        # "0 distinct origin(s) across 0 document(s)" on the same card that said,
        # truthfully, "3 independent sources contradict this claim: dw.com,
        # jansatta.com, ndtv.com". Two statements about one set of citations,
        # visibly disagreeing, on the screen built to explain the verdict.
        #
        # It also cost the score a quarter of its weight on exactly the cases the
        # product exists for: a debunked claim scored 0.36 because the component
        # measuring corroboration was measuring the wrong direction.
        #
        # Costs no extra work in the common case. A contradicted claim usually has
        # no supporting citations, so the count above short-circuits without
        # querying, and this runs in its place rather than in addition to it.
        carrying = None
        if decision.status is ClaimStatus.CONTRADICTED:
            # A throwaway list: a corroboration failure in the supporting direction
            # is already reported above, and reporting the same check twice for one
            # claim describes one outage as two gaps.
            carrying = await self._origins(
                claim, evidence=evidence, direction=Direction.CONTRADICTS, skipped=[]
            )

        strength = evidence_strength(
            evidence,
            independent_origin_count=(
                counted.independent_origin_count
                if carrying is None
                else carrying.independent_origin_count
            ),
            document_count=(
                counted.document_count if carrying is None else carrying.document_count
            ),
            source_risk=counted.source_risk,
        )

        return ClaimOutcome(
            claim=counted,
            decision=decision,
            strength=strength,
            evidence=evidence,
            explanation=explanation,
            search=search,
            looked_at=looked[0],
        )

    async def _follow_up(
        self,
        fallback: list[SourceResolver],
        claim: Claim,
        evidence: list[Evidence],
        *,
        skipped: list[SkippedCheck],
        deadline: float | None,
        tally: list[int],
    ) -> list[Evidence]:
        """The second round's evidence, or nothing when no better search was found."""
        writer = next((r for r in fallback if hasattr(r, "follow_up_queries")), None)
        if writer is None:
            return []
        if deadline is not None and deadline - time.perf_counter() < _FOLLOW_UP_MIN_SECONDS:
            # Said in the background, where a claim like this one is owed a second
            # round: dropped in silence, the answer read as though it had had one,
            # and was cached as complete. A check someone waits on in one request has
            # never had the time for it, and saying so there would say it of nearly
            # every answer. Not worded as a deadline: the claim was searched, and its
            # first round stands (`_resolve_claim` reads "deadline" as timed out).
            if _in_background():
                skipped.append(
                    SkippedCheck(
                        check="follow_up_search",
                        reason="too little time left for a second search round",
                        kind="deadline",
                    )
                )
            return []
        notes = [item.finding for item in evidence if item.finding][:6]
        try:
            queries = await writer.follow_up_queries(claim, notes)
        except Exception:
            logger.exception("follow-up queries could not be written")
            return []
        if not queries:
            return []
        event(
            logger,
            "follow-up search",
            module="orchestration",
            outcome="ok",
            queries=len(queries),
        )
        token = current_follow_up.set(tuple(queries))
        try:
            return await self._run_stage(
                fallback, claim, skipped=skipped, deadline=deadline, tally=tally
            )
        finally:
            current_follow_up.reset(token)

    async def _verify_sources(
        self,
        claim: Claim,
        evidence: list[Evidence],
        *,
        skipped: list[SkippedCheck],
        deadline: float | None = None,
    ) -> tuple[list[Evidence], str | None]:
        """Verified evidence and a plain summary, or deduplicated evidence without one.

        Deduplication happens even when no verifier is configured: a page cited three
        times for one claim is a bug whatever else runs, and its repeated id is what
        crashed the evidence screen.
        """
        watching = current_progress.get()
        if watching is not None:
            await watching.step("compare")

        if self._verification is None:
            unique, _ = dedupe(evidence)
            return unique, None

        budget = None if deadline is None else max(0.0, deadline - time.perf_counter())
        verified = await self._verification.check(claim, evidence, budget=budget)
        if not verified.checked:
            # Out of time is not an outage. Both read "model provider unavailable",
            # so a check that only ran out of time told the reader a service was down.
            skipped.append(
                SkippedCheck(
                    check="source_verification",
                    reason="no time left to check the sources",
                    kind="deadline",
                )
                if verified.timed_out
                else SkippedCheck(
                    check="source_verification",
                    reason="model provider unavailable",
                    kind="provider",
                )
            )
        if watching is not None:
            await watching.verified(
                claim.id,
                [
                    (item.citation_url, stance_of(item) or "context", item.source_excerpt)
                    for item in verified.evidence
                    if addresses_claim(item)
                ],
            )
        return verified.evidence, verified.explanation

    async def _run_stage(
        self,
        resolvers: list[SourceResolver],
        claim: Claim,
        *,
        skipped: list[SkippedCheck],
        deadline: float | None,
        tally: list[int] | None = None,
        late: list[bool] | None = None,
    ) -> list[Evidence]:
        """Run a set of resolvers concurrently for one claim and collect their evidence.

        Each resolver runs under what remains of the request deadline. Per resolver
        rather than around the gather: a timeout on the gather cancels everything,
        discarding the evidence the fast resolvers already produced, and a partial
        answer that says what was skipped beats an empty one that took just as long.

        `late[0]` is set when a web search was not started for want of time.
        """
        evidence: list[Evidence] = []
        if not resolvers:
            return evidence

        read_by = self._read_by(deadline)
        remaining = max(2.0, read_by - time.perf_counter()) if read_by is not None else None
        backstop = None if remaining is None else remaining + _RESOLVER_GRACE_SECONDS

        # A claim that waited its turn in the background (`_CLAIMS_AT_ONCE`) can reach
        # the web search with no reading time left. Its search is not started then:
        # the queries would be paid for and every page found cut off unread.
        if self._reading_left(deadline) < _MIN_SEARCH_SECONDS:
            searches = [r for r in resolvers if getattr(r, "fallback", False)]
            skipped.extend(self._too_late(searches))
            if searches and late is not None:
                late[0] = True
            resolvers = [r for r in resolvers if r not in searches]
            if not resolvers:
                return evidence

        gathered = await asyncio.gather(
            *(
                asyncio.wait_for(
                    self._run_resolver(resolver, claim, read_by=read_by), timeout=backstop
                )
                for resolver in resolvers
            ),
            return_exceptions=True,
        )

        for resolver, outcome in zip(resolvers, gathered, strict=True):
            name = getattr(resolver, "name", type(resolver).__name__)

            if isinstance(outcome, TimeoutError):
                # The time this check had, not the budget of a check someone waits
                # on: every background check was said to have run out of 55 seconds.
                # "deadline" is what marks the claim's search as timed out
                # (`_resolve_claim`), so it stays in the wording.
                skipped.append(
                    SkippedCheck(
                        check=name,
                        reason=f"deadline of {self._budget():.0f}s exceeded",
                        kind="deadline",
                    )
                )
                continue

            if isinstance(outcome, BaseException):
                # A producer failing is a gap, not a crash. It is recorded so the
                # response can say so rather than presenting a thinner evidence set
                # as if it were the whole picture.
                skipped.append(SkippedCheck(check=name, reason=type(outcome).__name__))
                continue

            found, skip, read = outcome
            if skip is not None:
                # A resolver skips for one of two reasons (`_run_resolver`): pages
                # still unread at the deadline, or the provider not called at all.
                skipped.append(
                    SkippedCheck(
                        check=name,
                        reason=skip,
                        kind="deadline" if "deadline" in skip else "provider",
                    )
                )
            if tally is not None:
                tally[0] += read
            evidence.extend(found)

        return evidence

    def _read_by(self, deadline: float | None) -> float | None:
        """When reading stops: early enough for the source check to run after it."""
        if deadline is not None and self._verification is not None:
            return deadline - _verify_reserve()
        return deadline

    def _reading_left(self, deadline: float | None) -> float:
        """Seconds of reading left to a claim of a background check; unbounded for
        any other, which starts every claim at once and has no turn to wait for."""
        read_by = self._read_by(deadline)
        if not _in_background() or not self._reads_sources or read_by is None:
            return float("inf")
        return read_by - time.perf_counter()

    def _too_late(self, resolvers: list[SourceResolver]) -> list[SkippedCheck]:
        """What a claim says of [resolvers] it reached with no time left to run."""
        return [
            SkippedCheck(
                check=getattr(resolver, "name", type(resolver).__name__),
                # "deadline" is what marks the claim's search as timed out.
                reason=(
                    f"deadline of {self._budget():.0f}s reached before it was "
                    + ("searched" if getattr(resolver, "fallback", False) else "checked")
                ),
                kind="deadline",
            )
            for resolver in resolvers
        ]

    def _budget(self) -> float:
        """The time this check had, in seconds, for saying what it ran out of.

        What `verify` gave it, which moves with how long reading the input took;
        else the budget it was asked to keep. It said 55 seconds of every
        background check, which had five minutes and more.
        """
        if not self._reads_sources:
            return TARGET_SECONDS
        return _check_budget.get() or check_seconds.get() or REASONING_TARGET_SECONDS

    async def _count_origins(
        self, claim: Claim, *, evidence: list[Evidence], skipped: list[SkippedCheck]
    ) -> Claim:
        """Attach the independent-origin count, or leave the claim untouched.

        Only supporting citations are counted. Contradicting evidence has its own
        decisive rule and does not need an origin count, and mixing the two would let
        sources that disagree inflate the corroboration behind a claim.

        A failure degrades to "no corroboration counted" rather than aborting: the
        counts stay zero, which can only make the verdict more cautious.
        """
        signal = await self._origins(
            claim, evidence=evidence, direction=Direction.SUPPORTS, skipped=skipped
        )
        return claim if signal is None else signal.applied_to(claim)

    async def _origins(
        self,
        claim: Claim,
        *,
        evidence: list[Evidence],
        direction: Direction,
        skipped: list[SkippedCheck],
    ) -> CorroborationSignal | None:
        """Independent origins among the citations pointing one way, or None.

        None means "not counted", never "none found". The two must stay
        distinguishable: a caller that cannot tell them apart overwrites a real
        count with a zero it never measured.
        """
        if self._corroboration is None:
            return None

        urls = sorted(_distinct_citations(evidence, direction))
        if not urls:
            return None

        try:
            return await self._corroboration.signal(claim, citation_urls=urls)
        except Exception as error:
            skipped.append(SkippedCheck(check="corroboration", reason=type(error).__name__))
            return None

    async def _run_resolver(
        self, resolver: SourceResolver, claim: Claim, *, read_by: float | None = None
    ) -> tuple[list[Evidence], str | None, int]:
        """Drive one resolver through candidates → snapshot → relate.

        Returns what it found and, separately, why it found nothing when the reason
        was a skip rather than an absence. Those are different answers and the
        response distinguishes them.

        Pages still being read at `read_by` are abandoned one by one; what was already
        read is kept. The deadline used to wrap the whole resolver, so one page that
        hung took every finished page down with it. Live: "India won the ICC Men's T20
        World Cup in 2024" was read from The Canadian Press, Wikipedia and Sportstar —
        three model calls, all answered — and came back Unconfirmed with no sources,
        because a sixth page's fetch timed out and the cancellation discarded all six.

        A web search (`fallback`) asks under its own ceiling, not the fetch slots: it
        is paced query by query and can wait its turn for a long time, and waiting in
        a fetch slot kept pages that were already found from being read.
        """
        gate = self._search_gate if getattr(resolver, "fallback", False) else self._semaphore
        async with gate:
            try:
                candidates = await resolver.candidates(claim)
            except ProviderUnavailable as unavailable:
                # The reason, not just the exception name: "capacity limited" tells a
                # reader the budget ran out, where `ProviderUnavailable` only says
                # something went wrong. It also marks the run incomplete, which is
                # what keeps `cacheable` from freezing the gap into a stored verdict.
                return [], unavailable.reason.value, 0

        if not candidates:
            return [], None, 0

        # Candidates are fetched concurrently. They are independent pages and nothing
        # about one informs another, so serialising them only added latency: six
        # candidates at roughly two seconds each spent fourteen seconds of an eight
        # second budget, and measured 14.4 s on the corpus resolver before this
        # changed. The semaphore still bounds real concurrency, so this widens the
        # window rather than the load.
        tasks = [
            asyncio.create_task(self._resolve_candidate(resolver, claim, candidate))
            for candidate in candidates
        ]
        remaining = None if read_by is None else max(0.5, read_by - time.perf_counter())
        try:
            done, pending = await asyncio.wait(tasks, timeout=remaining)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            raise
        for task in pending:
            task.cancel()
        if pending:
            # Let the cancellations land before returning, so no read outlives the
            # request that asked for it.
            await asyncio.gather(*pending, return_exceptions=True)

        evidence: list[Evidence] = []
        for task in done:
            # One unreachable page is an ordinary event and must not discard the
            # evidence its siblings produced.
            if task.cancelled() or task.exception() is not None:
                continue
            outcome = task.result()
            if outcome is not None:
                evidence.append(outcome)

        # Said, not hidden: a run that stopped reading early is incomplete, which also
        # keeps it out of the cache.
        skip = (
            f"{len(pending)} of {len(tasks)} sources not read before the deadline"
            if pending
            else None
        )
        return evidence, skip, len(done)

    async def _resolve_candidate(
        self, resolver: SourceResolver, claim: Claim, candidate: SourceCandidate
    ) -> Evidence | None:
        """Fetch one candidate and turn it into evidence, or into nothing."""
        watching = current_progress.get()
        if watching is not None:
            await watching.source_started(
                candidate.url,
                candidate.publisher,
                title=candidate.title,
                via="fact_check" if resolver.kind is EvidenceKind.FACT_CHECK else "page",
            )
        found: Evidence | None = None
        try:
            async with self._semaphore:
                snapshot = await resolver.snapshot(candidate)

            if snapshot is None:
                return None

            relation = await resolver.relate(claim, snapshot)
            found = build_evidence(
                resolver=resolver, claim_id=claim.id, snapshot=snapshot, relation=relation
            )
            return found
        finally:
            # Also when the read is abandoned at the deadline, so the screen never
            # shows a source as still being read after the check has moved on.
            if watching is not None:
                spoke = found is not None and addresses_claim(found)
                await watching.source_done(
                    candidate.url,
                    claim_id=claim.id,
                    found=spoke,
                    stance=stance_of(found) if spoke else None,
                    quote=found.source_excerpt if spoke and found is not None else None,
                )


def _distinct_citations(
    evidence: list[Evidence], direction: Direction = Direction.SUPPORTS
) -> set[str]:
    """Citation URLs pointing one way, with republished copies of one story collapsed.

    Origins are what rule 4 counts, and two outlets carrying the same wire story are
    one origin however many mastheads run it. For corpus documents the stored minhash
    signatures settle that; for a page found on the open web there is no signature,
    so the quote does the work instead. Two citations whose verified excerpt is the
    same text are the same reporting, and only the first is counted.

    The excerpt is the right thing to compare because it is already the part a
    resolver proved is in the page — a shared boilerplate footer cannot merge two
    genuinely different articles, since a footer is never what was quoted.
    """
    citations: dict[str, str] = {}
    for item in evidence:
        if item.direction is not direction or not item.citation_url:
            continue
        excerpt = " ".join((item.source_excerpt or "").lower().split())
        # Short or absent excerpts are not evidence of syndication, only of a short
        # quote, so they are keyed by URL and always kept.
        key = excerpt if len(excerpt) >= 120 else f"url:{item.citation_url}"
        citations.setdefault(key, item.citation_url)
    return set(citations.values())


def cacheable(result: VerificationResult) -> bool:
    """Whether this result should be written back to the cache.

    An incomplete run is not cached. Caching one would freeze a temporary provider
    outage into a stored verdict and serve it for the next thirty days, which turns a
    transient gap into a durable wrong answer.
    """
    return result.is_complete and not result.from_cache


def developing(result: VerificationResult) -> bool:
    """Whether this case is about a developing story, which shortens the TTL."""
    return any(outcome.claim.within_developing_window for outcome in result.claims)
