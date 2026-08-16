"""Corroboration (M30).

Two questions, and the second is the one people get wrong.

**How many genuinely independent sources carry this?** Origins, not documents. The
count comes from the clusterer, and both numbers reach the interface so a reader can
see the difference between coverage and confirmation.

**What does silence mean here?** Almost always: nothing. Absence of coverage is
evidence only when coverage was *expected*, and the expectation is captured at
extraction rather than guessed at here. A claim that would be front-page news if
true, absent from every outlet in the corpus, is meaningful. A village-level story
absent from national feeds is not — and treating it as suspicious would systematically
penalise exactly the local reporting that has no national footprint.

The developing-news window sits on top of both. For the first hours of a real event
credible coverage may simply not exist yet, so silence is ambiguous and produces
abstention with a re-check, never a contradiction. Skipping this is how a system
embarrasses itself on a true breaking story.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.claim import Claim
from app.domain.enums import CoverageExpectation, EvidenceKind, Method, Relation, Tier
from app.knowledge.clustering import CorroborationCount, OriginClusterer
from app.observability.logging import event
from app.sources.base import SourceCandidate, SourceRelation, SourceSnapshot, insufficient

logger = logging.getLogger("facify.corroboration")

NAME = "corroboration"
VERSION = "2026.08.1"

# Independent origins required before corroboration supports a claim. One origin is
# a source, not a corroboration.
DEFAULT_MIN_ORIGINS = 2

# How long after an asserted event silence stays ambiguous. Within this window the
# story may simply not have been written yet.
DEVELOPING_WINDOW = timedelta(hours=2)

# Corpus coverage below which "we found nothing" says more about the corpus than
# about the claim. With a thin corpus, absence is not evidence of anything.
MIN_CORPUS_ITEMS_FOR_SILENCE = 200


@dataclass(frozen=True, slots=True)
class CorroborationResult:
    """What the corpus knows about a claim, and what that is worth."""

    count: CorroborationCount
    relation: Relation
    reason: str
    within_developing_window: bool = False
    silence_is_meaningful: bool = False

    @property
    def is_negative_evidence(self) -> bool:
        """Absence that actually counts against the claim."""
        return self.relation is Relation.CONTRADICTS and self.silence_is_meaningful


def within_developing_window(asserted_at: datetime | None, *, now: datetime | None = None) -> bool:
    """Whether the asserted event is too recent for absence to mean anything."""
    if asserted_at is None:
        return False
    moment = now or datetime.now(UTC)
    if asserted_at > moment:
        # An event asserted in the future is not a corroboration question.
        return True
    return moment - asserted_at < DEVELOPING_WINDOW


def silence_is_meaningful(claim: Claim, *, corpus_size: int, developing: bool) -> tuple[bool, str]:
    """Whether finding nothing is evidence, and why or why not.

    Three conditions, all required. Any one of them missing makes silence
    uninformative, and saying so explicitly is what keeps this honest.
    """
    if developing:
        return False, "too recent to corroborate; coverage may not exist yet"

    if corpus_size < MIN_CORPUS_ITEMS_FOR_SILENCE:
        return False, f"corpus too small ({corpus_size} items) for absence to mean anything"

    if claim.coverage_expectation is not CoverageExpectation.HIGH:
        expectation = (
            claim.coverage_expectation.value if claim.coverage_expectation else "unassessed"
        )
        return False, (
            f"coverage expectation is {expectation}; a story of this scale need not "
            "appear in national feeds"
        )

    return True, "a claim of this significance would be widely reported if true"


class CorroborationResolver:
    """Counts independent origins and interprets absence."""

    name = NAME
    version = VERSION
    allowed_domains: frozenset[str] = frozenset()

    # Independent origins agreeing. Tier D: real, and never decisive alone —
    # twenty outlets carrying one wire story is one origin, which M26 collapses.
    tier = Tier.D
    kind = EvidenceKind.CORROBORATION
    method = Method.ORIGIN_CLUSTER_COUNT

    def __init__(
        self,
        *,
        clusterer: OriginClusterer,
        min_origins: int = DEFAULT_MIN_ORIGINS,
    ) -> None:
        self._clusterer = clusterer
        self._min_origins = min_origins

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        """Corroboration searches the corpus rather than proposing URLs.

        Retrieval belongs to the caller, which holds the database connection and the
        embedder; this resolver's job is what the results mean.
        """
        del claim
        return []

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        del candidate
        return None

    def assess(
        self,
        claim: Claim,
        *,
        matching_document_ids: list[str],
        corpus_size: int,
        asserted_at: datetime | None = None,
        now: datetime | None = None,
    ) -> CorroborationResult:
        """Turn corpus matches into a finding, or into an honest nothing."""
        developing = within_developing_window(asserted_at, now=now)
        origins = self._clusterer.distinct_origins(matching_document_ids)
        count = CorroborationCount(documents=len(matching_document_ids), origins=origins)

        if count.is_syndicated:
            event(
                logger,
                "syndication detected in corroboration set",
                module="sources.corroboration",
                outcome="ok",
                documents=count.documents,
                origins=count.origins,
            )

        if origins >= self._min_origins:
            return CorroborationResult(
                count=count,
                relation=Relation.SUPPORTS,
                reason=f"{count} carry this claim",
            )

        if origins > 0:
            # Some coverage, but not enough independence to support. Abstention, not
            # contradiction — one outlet reporting something is not evidence against it.
            return CorroborationResult(
                count=count,
                relation=Relation.INSUFFICIENT,
                reason=(
                    f"{count}; {self._min_origins} independent origins are required "
                    "before corroboration can support a claim"
                ),
                within_developing_window=developing,
            )

        meaningful, why = silence_is_meaningful(
            claim, corpus_size=corpus_size, developing=developing
        )

        if meaningful:
            return CorroborationResult(
                count=count,
                relation=Relation.CONTRADICTS,
                reason=(f"No coverage in {corpus_size} corpus items. {why.capitalize()}."),
                silence_is_meaningful=True,
            )

        return CorroborationResult(
            count=count,
            relation=Relation.INSUFFICIENT,
            reason=f"No corroborating coverage found, but {why}",
            within_developing_window=developing,
        )

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Not the path corroboration uses — `assess` is.

        Present so the resolver satisfies the protocol, and explicit about it rather
        than quietly returning something plausible.
        """
        del claim, snapshot
        return insufficient(
            NAME, VERSION, "corroboration is assessed over the corpus, not per source"
        )
