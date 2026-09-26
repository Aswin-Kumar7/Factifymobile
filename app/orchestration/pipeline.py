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
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.cache.keys import DEFAULT_POLICY_PROFILE, CacheKeyParts
from app.cache.service import CachedVerdict
from app.domain.claim import Claim
from app.domain.enums import Action, ClaimStatus, Direction, Importance, SourceRisk
from app.domain.evidence import Advisory, Evidence
from app.governor.governor import ProviderUnavailable, Skip
from app.intake.normalizer import NormalisedIntake
from app.observability.logging import event
from app.sources.base import (
    NORMAL,
    SourceCandidate,
    SourceResolver,
    build_evidence,
    current_check,
    current_depth,
)
from app.sources.corpus import CorroborationSignal
from app.sources.reasoning import REASONER_VERSION
from app.sources.verification import SourceVerification, dedupe, page_key
from app.verdict.engine import (
    RULE_VERSION,
    CaseDecision,
    Decision,
    decide,
    roll_up,
    verdict_for,
)
from app.verdict.strength import Strength, evidence_strength

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

# Kept back from the reading deadline for the source check that follows it. Reading
# used to run to the deadline itself, leaving the check no time at all — so it timed
# out at once and every source reached the verdict unchecked. The check is one model
# call over short excerpts; measured at three to four seconds.
_VERIFY_RESERVE_SECONDS = 6.0

# How much longer than its reading deadline a resolver is given before it is cut off
# whole. Pages are cut off individually at the deadline (see `_run_resolver`); this is
# the backstop for a search provider that never answers at all.
_RESOLVER_GRACE_SECONDS = 3.0

# How many resolvers may run at once. Independent producers are concurrent because
# they do not depend on each other; the ceiling exists so a burst of claims cannot
# open forty sockets against six publishers.
DEFAULT_CONCURRENCY = 6

# How many claims in one verification may reach a fallback resolver — the metered,
# open-web kind (`fallback = True`, today web search: a search-API call plus a model
# read per source). The most important claims go first. A forwarded message carries
# one to three claims and is unaffected; a long article can yield seven, and reading
# the open web for every supporting detail multiplied the model calls per check
# several times over for little change in the verdict.
#
# Five, not three: at three, one claim in every four-claim article was never searched
# and still read "Unconfirmed" — on a Hindu analysis, the one claim that kept the
# answer from True. Five covers most articles whole, for about ten more seconds and
# two more searched claims' worth of model calls.
MAX_FALLBACK_CLAIMS = 5

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

    def describe(self) -> str:
        return f"{self.check} was not checked: {self.reason}"


# Called as each claim finishes (done, total), for a check someone is watching.
claim_progress: ContextVar[Callable[[int, int], None] | None] = ContextVar(
    "claim_progress", default=None
)


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
    # (below the per-check cap) or "timed_out". An unconfirmed claim that was never
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


def _not_own(evidence: list[Evidence], own_pages: frozenset[str]) -> list[Evidence]:
    """The evidence, less anything from the pages the person submitted.

    A submitted article cannot confirm itself. Searching for the claims of a Times of
    India kabaddi report found that same report, and it stood as the headline claim's
    only supporting source — the article, quoted back as evidence that the article is
    right. For a fabricated page that search can reach, the same loop would support
    every claim it makes.
    """
    if not own_pages:
        return evidence
    return [item for item in evidence if page_key(item.citation_url) not in own_pages]


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
    ) -> None:
        self._cache = cache
        # Optional for the same reason as corroboration. Without it, sources are still
        # deduplicated but not checked for relevance.
        self._verification = verification
        self._governor = governor
        self._resolvers = resolvers
        self._extractor_version = extractor_version
        self._model_id = model_id
        self._semaphore = asyncio.Semaphore(concurrency)
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
        semaphore** — is shared, because the fetch ceiling only means anything if
        every in-flight request counts against the same one.
        """
        clone = Orchestrator(
            cache=self._cache,
            governor=self._governor,
            resolvers=resolvers,
            extractor_version=self._extractor_version,
            model_id=self._model_id,
            corroboration=self._corroboration,
            verification=self._verification,
        )
        clone._semaphore = self._semaphore
        return clone

    def _cache_key(self, intake: NormalisedIntake) -> CacheKeyParts:
        """The verdict-cache key for an input — computable before anything is extracted."""
        return CacheKeyParts(
            # `cache_identity` rather than the primary object's hash: for a URL it is
            # the canonicalised address, so two people sharing the same article with
            # different tracking parameters hit one entry instead of two.
            content_hash=intake.cache_identity,
            # A deep check is stored apart: a normal answer must never be served to
            # someone who asked (and paid) for a deep one, nor the reverse.
            policy_profile=(
                DEFAULT_POLICY_PROFILE
                if current_depth.get() is NORMAL
                else current_depth.get().name
            ),
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
    ) -> VerificationResult:
        """Run one verification end to end.

        `fresh` skips the stored verdict: a person pressed "Check again", and the
        answer from an hour ago is exactly what they are asking to replace.

        `own_pages` are the pages the person submitted — a link, or a link inside a
        message. They are never evidence for their own claims (see `_not_own`).

        `started_at` is when the request arrived, when the caller knows it. The budget
        is the person's wait, and extraction happened before this was called.

        Claims arrive already extracted: extraction is upstream because it has its own
        caching and its own provider budget, and threading it through here would put a
        second metered call inside a function whose job is to sequence, not to fetch.
        """
        started = started_at if started_at is not None else time.perf_counter()
        skipped: list[SkippedCheck] = []

        # Cache probe, before the governor and before any provider. A repeat costs
        # nothing external; the M13 gate asserts exactly this.
        cache_key = self._cache_key(intake)
        cached = None if fresh else await self._cache.get_verdict(cache_key)
        if cached is not None:
            return self._from_cache(cached, case_id=case_id, intake=intake, started=started)

        own = set(own_pages)
        if intake.primary.source_url:
            own.add(page_key(intake.primary.source_url))

        # The budget becomes a deadline here, not a wish. It was declared and
        # measured but never enforced, and real requests ran to 90 seconds — past
        # the mobile client's own 45 second timeout, so the server was still working
        # on answers nobody was waiting for.
        #
        # Which budget depends on what the resolvers are allowed to do. Reading a
        # source with a model measures 31 seconds; word overlap measures
        # milliseconds. One deadline for both would either cut every reasoned answer
        # off mid-call or let every lexical one dawdle.
        depth = current_depth.get()
        reading = REASONING_TARGET_SECONDS if depth is NORMAL else depth.seconds
        deadline = started + (reading if self._reads_sources else TARGET_SECONDS)

        check = current_check.set(str(case_id))
        try:
            outcomes = await self._resolve_all(
                claims, skipped=skipped, deadline=deadline, own_pages=frozenset(own)
            )
        finally:
            current_check.reset(check)
            for resolver in self._resolvers:
                end_check = getattr(resolver, "end_check", None)
                if end_check is not None:
                    end_check(str(case_id))

        case_decision = roll_up(
            [(outcome.claim, outcome.decision) for outcome in outcomes], source_risk=source_risk
        )

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
        if result.is_complete and outcomes:
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
                    developing=any(o.claim.within_developing_window for o in outcomes),
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
    ) -> list[ClaimOutcome]:
        """Resolve every claim, bounded by the concurrency ceiling.

        Only the `MAX_FALLBACK_CLAIMS` most important claims may reach a fallback
        resolver. The ranking is stable, so equally important claims keep the order the
        extractor gave them.
        """
        if not claims:
            return []

        unranked = len(_IMPORTANCE_ORDER)
        ranked = sorted(
            range(len(claims)),
            key=lambda index: _IMPORTANCE_ORDER.get(claims[index].importance, unranked),
        )
        depth = current_depth.get()
        cap = MAX_FALLBACK_CLAIMS if depth is NORMAL else depth.claims
        may_fall_back = set(ranked[:cap])

        # Progress, for a check someone is watching: one tick per finished claim.
        report = claim_progress.get()
        finished = 0
        if report is not None:
            report(0, len(claims))

        async def _counted(index: int, claim: Claim) -> ClaimOutcome:
            nonlocal finished
            outcome = await self._resolve_claim(
                claim,
                skipped=skipped,
                deadline=deadline,
                allow_fallback=index in may_fall_back,
                own_pages=own_pages,
            )
            finished += 1
            if report is not None:
                report(finished, len(claims))
            return outcome

        results = await asyncio.gather(
            *(_counted(index, claim) for index, claim in enumerate(claims))
        )
        return list(results)

    async def _resolve_claim(
        self,
        claim: Claim,
        *,
        skipped: list[SkippedCheck],
        deadline: float | None = None,
        allow_fallback: bool = True,
        own_pages: frozenset[str] = frozenset(),
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

        # This claim's own gaps and page count, to say what was done for it.
        mine: list[SkippedCheck] = []
        looked = [0]
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
        if fallback and allow_fallback and not decide(counted, evidence).status.is_decisive:
            evidence.extend(
                await self._run_stage(
                    fallback, claim, skipped=mine, deadline=deadline, tally=looked
                )
            )
            searched = True
        elif fallback:
            event(
                logger,
                "fallback resolvers not consulted",
                module="orchestration",
                outcome="ok",
                reason="already decisive" if allow_fallback else "claim below the fallback cap",
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
        if fallback and allow_fallback and not searched:
            counted = await self._count_origins(claim, evidence=evidence, skipped=[])
            if not decide(counted, evidence).status.is_decisive:
                evidence.extend(
                    await self._run_stage(
                        fallback, claim, skipped=mine, deadline=deadline, tally=looked
                    )
                )
                searched = True
                evidence = _not_own(evidence, own_pages)
                evidence, explanation = await self._verify_sources(
                    claim, evidence, skipped=skipped, deadline=deadline
                )

        scratch = []
        counted = await self._count_origins(claim, evidence=evidence, skipped=scratch)
        skipped.extend(scratch)
        skipped.extend(mine)

        if fallback and not searched and not allow_fallback:
            search = "not_searched"
        elif any("deadline" in gap.reason for gap in mine):
            search = "timed_out"
        else:
            search = "searched"

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
            explanation = None

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
        if self._verification is None:
            unique, _ = dedupe(evidence)
            return unique, None

        budget = None if deadline is None else max(0.0, deadline - time.perf_counter())
        verified = await self._verification.check(claim, evidence, budget=budget)
        if not verified.checked:
            skipped.append(
                SkippedCheck(check="source_verification", reason="model provider unavailable")
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
    ) -> list[Evidence]:
        """Run a set of resolvers concurrently for one claim and collect their evidence.

        Each resolver runs under what remains of the request deadline. Per resolver
        rather than around the gather: a timeout on the gather cancels everything,
        discarding the evidence the fast resolvers already produced, and a partial
        answer that says what was skipped beats an empty one that took just as long.
        """
        evidence: list[Evidence] = []
        if not resolvers:
            return evidence

        # Reading stops early enough for the source check to run after it.
        read_by = deadline
        if deadline is not None and self._verification is not None:
            read_by = deadline - _VERIFY_RESERVE_SECONDS

        remaining = max(2.0, read_by - time.perf_counter()) if read_by is not None else None
        backstop = None if remaining is None else remaining + _RESOLVER_GRACE_SECONDS

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
                budget = REASONING_TARGET_SECONDS if self._reads_sources else TARGET_SECONDS
                skipped.append(
                    SkippedCheck(check=name, reason=f"deadline of {budget:.0f}s exceeded")
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
                skipped.append(SkippedCheck(check=name, reason=skip))
            if tally is not None:
                tally[0] += read
            evidence.extend(found)

        return evidence

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
        """
        async with self._semaphore:
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
        async with self._semaphore:
            snapshot = await resolver.snapshot(candidate)

        if snapshot is None:
            return None

        relation = await resolver.relate(claim, snapshot)
        return build_evidence(
            resolver=resolver, claim_id=claim.id, snapshot=snapshot, relation=relation
        )

    async def probe_provider(self, provider: str) -> str | None:
        """Ask the governor whether a provider may be used, without using it.

        Callers that need to know before building a request use this rather than
        catching a refusal after the fact.
        """
        outcome = await self._governor.try_acquire(provider)
        return outcome.reason.value if isinstance(outcome, Skip) else None


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


def decisive_claims(result: VerificationResult) -> list[ClaimOutcome]:
    """Claims that reached a decisive status, and therefore carry citations."""
    return [outcome for outcome in result.claims if outcome.decision.status.is_decisive]


def abstained(result: VerificationResult) -> bool:
    """Whether the case is one the system correctly refused to decide (M43)."""
    return result.action is Action.SEND_TO_REVIEW or all(
        outcome.decision.status is ClaimStatus.UNVERIFIED for outcome in result.claims
    )


def observed_at() -> datetime:
    return datetime.now(UTC)
