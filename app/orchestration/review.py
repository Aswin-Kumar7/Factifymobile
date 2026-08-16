"""Human review queue (M43).

The designed destination for cases the system correctly refuses to decide — not an
error channel, and not a backlog of failures. A case reaching this queue means the
evidence did not support a verdict, which is the product working.

**The rule that shapes everything here: the human label is recorded *beside* the
machine output, never over it.** There is no update path that overwrites
`machine_status`, and the reviewer's label lands in its own column. Two reasons, and
the second matters more:

  1. The pair is the only honest record of what happened. "The system said
     UNVERIFIED and a reviewer said false" is a different fact from "false", and the
     second erases how it was reached.
  2. Disagreements between the two are the calibration data. Overwriting throws away
     the only signal that says where the rules are wrong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.db.repositories import ReviewRepository
from app.domain.enums import Action, ClaimStatus
from app.observability.logging import event
from app.orchestration.pipeline import VerificationResult

logger = logging.getLogger("facify.review")


class ReviewReason(StrEnum):
    """Why a case is here. Rendered to the reviewer as their starting context."""

    NO_EVIDENCE = "no_citable_evidence"
    CONFLICTING_EVIDENCE = "sources_disagree"
    SOURCE_RISK = "publisher_risk_signals"
    INCOMPLETE_RUN = "checks_could_not_run"
    DEVELOPING_STORY = "story_still_developing"


class HumanLabel(StrEnum):
    """What a reviewer concluded. Deliberately the same vocabulary as the engine,
    so the two columns are directly comparable when calibrating."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    MISLEADING_CONTEXT = "MISLEADING_CONTEXT"
    UNVERIFIED = "UNVERIFIED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True, slots=True)
class QueuedCase:
    """One case awaiting review, with everything needed to judge it."""

    item_id: UUID
    case_id: UUID
    reason: ReviewReason
    machine_status: str | None
    created_at: datetime

    @property
    def context(self) -> str:
        """The line the reviewer sees first."""
        return {
            ReviewReason.NO_EVIDENCE: (
                "No citable source was found. The system abstained rather than guessing."
            ),
            ReviewReason.CONFLICTING_EVIDENCE: (
                "Sources disagree. Both sides are cited in the evidence list."
            ),
            ReviewReason.SOURCE_RISK: (
                "The publisher carries risk signals. Risk never decides a claim, so this "
                "case abstained and came here."
            ),
            ReviewReason.INCOMPLETE_RUN: (
                "One or more checks could not run. The result may be thinner than the "
                "evidence that actually exists."
            ),
            ReviewReason.DEVELOPING_STORY: (
                "The story is still developing. Early coverage is often revised."
            ),
        }[self.reason]


@dataclass(frozen=True, slots=True)
class ReviewedCase:
    """A case with both records: what the system said, and what a person said."""

    item_id: UUID
    case_id: UUID
    machine_status: str | None
    human_label: HumanLabel
    reviewer: str
    reviewed_at: datetime
    notes: str | None = None

    @property
    def disagrees(self) -> bool:
        """Whether the reviewer reached a different conclusion.

        Not a failure — this is the number worth watching. A system that never
        disagrees with its reviewers is either perfect or not being reviewed.
        """
        return self.machine_status is not None and self.machine_status != self.human_label.value

    @property
    def is_promotable(self) -> bool:
        """Whether this reviewed finding can feed M38's trusted store.

        Only decisive human labels qualify. A reviewer confirming "still unverified"
        is a useful record and not a new fact about the world, so it promotes nothing.
        """
        return self.human_label in {
            HumanLabel.SUPPORTED,
            HumanLabel.CONTRADICTED,
            HumanLabel.MISLEADING_CONTEXT,
        }


def reason_for(result: VerificationResult) -> ReviewReason | None:
    """Why this case needs review, or `None` if it does not.

    Checked most-specific first: a case that both had an incomplete run and found no
    evidence is better described by the incomplete run, because that is the one a
    reviewer can act on by re-running it.
    """
    if not result.is_complete:
        return ReviewReason.INCOMPLETE_RUN

    if any(outcome.decision.conflicting for outcome in result.claims):
        return ReviewReason.CONFLICTING_EVIDENCE

    if any(outcome.claim.within_developing_window for outcome in result.claims):
        return ReviewReason.DEVELOPING_STORY

    if result.action is not Action.SEND_TO_REVIEW:
        return None

    if any(outcome.claim.source_risk.value in {"HIGH", "MEDIUM"} for outcome in result.claims):
        return ReviewReason.SOURCE_RISK

    return ReviewReason.NO_EVIDENCE


class ReviewQueue:
    """Routes abstaining cases in, and records human labels beside machine ones."""

    def __init__(self, *, repository: ReviewRepository) -> None:
        self._repository = repository

    async def route(self, result: VerificationResult) -> UUID | None:
        """Enqueue this case if it needs review. Returns the item id, or `None`.

        Called on every verification. A case that resolved cleanly is not enqueued,
        so the queue length is a real measure of how often the system abstains rather
        than a copy of the request log.
        """
        reason = reason_for(result)
        if reason is None:
            return None

        machine_status = _dominant_status(result)

        item_id = await self._repository.enqueue(
            case_id=result.case_id,
            reason=reason.value,
            machine_status=machine_status,
        )

        event(
            logger,
            "case routed for review",
            module="review",
            outcome="ok",
            reason=reason.value,
            machine_status=machine_status,
        )
        return item_id

    async def record(
        self,
        *,
        item_id: UUID,
        label: HumanLabel,
        reviewer: str,
        notes: str | None = None,
    ) -> None:
        """Record a human judgement alongside the machine's.

        The repository has no path that touches `machine_status`, so this cannot
        overwrite it even by mistake — the guarantee is structural rather than a rule
        someone has to remember.
        """
        if not reviewer:
            raise ValueError("a review must name its reviewer; an anonymous label is unaccountable")

        await self._repository.record_human_label(
            item_id=item_id, human_label=label.value, reviewer=reviewer, notes=notes
        )

        event(
            logger,
            "human label recorded",
            module="review",
            outcome="ok",
            label=label.value,
        )

    async def pending(self, limit: int = 50) -> list[QueuedCase]:
        rows = await self._repository.pending(limit)
        return [
            QueuedCase(
                item_id=UUID(str(row["id"])),
                case_id=UUID(str(row["case_id"])),
                reason=ReviewReason(str(row["reason"])),
                machine_status=row["machine_status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


def _dominant_status(result: VerificationResult) -> str | None:
    """The status that best represents the case, for the reviewer's context.

    A decisive claim if there is one, because that is what a reviewer is being asked
    to check; otherwise `UNVERIFIED`, which is what an abstaining case actually said.
    """
    for outcome in result.claims:
        if outcome.decision.status.is_decisive:
            return outcome.decision.status.value
    return ClaimStatus.UNVERIFIED.value if result.claims else None
