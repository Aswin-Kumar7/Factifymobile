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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.cache.keys import CacheKeyParts
from app.cache.service import CachedVerdict, CacheService
from app.domain.claim import Claim
from app.domain.enums import Action, ClaimStatus, Direction, SourceRisk
from app.domain.evidence import Advisory, Evidence
from app.governor.governor import Governor, Skip
from app.intake.normalizer import NormalisedIntake
from app.observability.logging import event
from app.sources.base import SourceCandidate, SourceResolver, build_evidence
from app.sources.corpus import CorroborationSignal
from app.verdict.engine import RULE_VERSION, CaseDecision, Decision, decide, roll_up
from app.verdict.strength import Strength, evidence_strength

logger = logging.getLogger("facify.orchestration")

# The synchronous budget for text, URL, image and PDF (codexplan §11). Video returns
# accepted-with-progress instead of blocking a request for half a minute.
TARGET_SECONDS = 8.0

# How many resolvers may run at once. Independent producers are concurrent because
# they do not depend on each other; the ceiling exists so a burst of claims cannot
# open forty sockets against six publishers.
DEFAULT_CONCURRENCY = 6


class Corroboration(Protocol):
    """Anything that can count independent origins for a claim.

    A protocol rather than a concrete type so the orchestrator does not depend on the
    corpus module, and so a test can count origins without a database.
    """

    async def signal(self, claim: Claim, *, citation_urls: list[str]) -> CorroborationSignal: ...


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


@dataclass(slots=True)
class ClaimOutcome:
    """One claim, its decision, its evidence and its score."""

    claim: Claim
    decision: Decision
    strength: Strength
    evidence: list[Evidence] = field(default_factory=list)


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


class Orchestrator:
    """Runs the fixed order. The only place that order is expressed."""

    def __init__(
        self,
        *,
        cache: CacheService,
        governor: Governor,
        resolvers: list[SourceResolver],
        extractor_version: str,
        model_id: str = "",
        concurrency: int = DEFAULT_CONCURRENCY,
        corroboration: Corroboration | None = None,
    ) -> None:
        self._cache = cache
        self._governor = governor
        self._resolvers = resolvers
        self._extractor_version = extractor_version
        self._model_id = model_id
        self._semaphore = asyncio.Semaphore(concurrency)
        # Optional so existing callers — the audit runner, every unit test — keep
        # working unchanged and simply count no origins.
        self._corroboration = corroboration

    async def verify(
        self,
        intake: NormalisedIntake,
        *,
        case_id: UUID,
        claims: list[Claim],
        advisories: list[Advisory] | None = None,
        source_risk: SourceRisk = SourceRisk.UNKNOWN,
    ) -> VerificationResult:
        """Run one verification end to end.

        Claims arrive already extracted: extraction is upstream because it has its own
        caching and its own provider budget, and threading it through here would put a
        second metered call inside a function whose job is to sequence, not to fetch.
        """
        started = time.perf_counter()
        skipped: list[SkippedCheck] = []

        # Cache probe, before the governor and before any provider. A repeat costs
        # nothing external; the M13 gate asserts exactly this.
        cache_key = CacheKeyParts(
            # `cache_identity` rather than the primary object's hash: for a URL it is
            # the canonicalised address, so two people sharing the same article with
            # different tracking parameters hit one entry instead of two.
            content_hash=intake.cache_identity,
            rule_version=RULE_VERSION,
            extractor_version=self._extractor_version,
            language=intake.language.language.value,
            model_id=self._model_id,
        )
        cached = await self._cache.get_verdict(cache_key)
        if cached is not None:
            return self._from_cache(cached, case_id=case_id, intake=intake, started=started)

        outcomes = await self._resolve_all(claims, skipped=skipped)

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

        age = int(cached.age.total_seconds())
        event(
            logger,
            "verification served from cache",
            module="orchestration",
            outcome="ok",
            cache="hit",
            age_s=age,
            usable=raw_action is not None,
        )

        return VerificationResult(
            case_id=case_id,
            content_hash=intake.primary.sha256,
            action=action,
            case_decision=CaseDecision(
                action=action,
                rule_id="cache",
                reason=(
                    f"Previously verified {age}s ago; the stored result was reused unchanged."
                    if raw_action is not None
                    else "A stored result was found but could not be read; routed for review."
                ),
                rule_version=cached.rule_version,
            ),
            from_cache=True,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _resolve_all(
        self, claims: list[Claim], *, skipped: list[SkippedCheck]
    ) -> list[ClaimOutcome]:
        """Resolve every claim, bounded by the concurrency ceiling."""
        if not claims:
            return []

        results = await asyncio.gather(
            *(self._resolve_claim(claim, skipped=skipped) for claim in claims)
        )
        return list(results)

    async def _resolve_claim(self, claim: Claim, *, skipped: list[SkippedCheck]) -> ClaimOutcome:
        """Gather evidence for one claim, then decide on it.

        `decide` and `evidence_strength` are both called here and neither is
        bypassable: there is no branch in this function that produces a status any
        other way.
        """
        evidence: list[Evidence] = []

        gathered = await asyncio.gather(
            *(self._run_resolver(resolver, claim) for resolver in self._resolvers),
            return_exceptions=True,
        )

        for resolver, outcome in zip(self._resolvers, gathered, strict=True):
            name = getattr(resolver, "name", type(resolver).__name__)

            if isinstance(outcome, BaseException):
                # A producer failing is a gap, not a crash. It is recorded so the
                # response can say so rather than presenting a thinner evidence set
                # as if it were the whole picture.
                skipped.append(SkippedCheck(check=name, reason=type(outcome).__name__))
                continue

            found, skip = outcome
            if skip is not None:
                skipped.append(SkippedCheck(check=name, reason=skip))
            evidence.extend(found)

        # Corroboration is counted here — after the evidence exists and before
        # anything decides. Rule 4 reads `independent_origin_count` off the claim,
        # and nothing in this codebase ever wrote it: the field was read and never
        # set, so a claim carried by several independent outlets still fell through
        # to `rule.insufficient_origins`.
        #
        # The count must come from the citations rather than from what retrieval
        # shortlisted. An earlier version counted the shortlist and handed the engine
        # "6 independent origins" for a claim only one document actually supported.
        claim = await self._count_origins(claim, evidence=evidence, skipped=skipped)

        decision = decide(claim, evidence)
        strength = evidence_strength(
            evidence,
            independent_origin_count=claim.independent_origin_count,
            document_count=claim.document_count,
            source_risk=claim.source_risk,
        )

        return ClaimOutcome(claim=claim, decision=decision, strength=strength, evidence=evidence)

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
        if self._corroboration is None:
            return claim

        urls = sorted(
            {
                e.citation_url
                for e in evidence
                if e.direction is Direction.SUPPORTS and e.citation_url
            }
        )
        if not urls:
            return claim

        try:
            signal = await self._corroboration.signal(claim, citation_urls=urls)
        except Exception as error:
            skipped.append(SkippedCheck(check="corroboration", reason=type(error).__name__))
            return claim

        return signal.applied_to(claim)

    async def _run_resolver(
        self, resolver: SourceResolver, claim: Claim
    ) -> tuple[list[Evidence], str | None]:
        """Drive one resolver through candidates → snapshot → relate.

        Returns what it found and, separately, why it found nothing when the reason
        was a skip rather than an absence. Those are different answers and the
        response distinguishes them.
        """
        async with self._semaphore:
            candidates = await resolver.candidates(claim)

        if not candidates:
            return [], None

        # Candidates are fetched concurrently. They are independent pages and nothing
        # about one informs another, so serialising them only added latency: six
        # candidates at roughly two seconds each spent fourteen seconds of an eight
        # second budget, and measured 14.4 s on the corpus resolver before this
        # changed. The semaphore still bounds real concurrency, so this widens the
        # window rather than the load.
        gathered = await asyncio.gather(
            *(self._resolve_candidate(resolver, claim, candidate) for candidate in candidates),
            return_exceptions=True,
        )

        evidence: list[Evidence] = []
        for outcome in gathered:
            # One unreachable page is an ordinary event and must not discard the
            # evidence its siblings produced.
            if isinstance(outcome, BaseException) or outcome is None:
                continue
            evidence.append(outcome)

        return evidence, None

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
