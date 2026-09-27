"""Temporal dating (M31).

Establishes when something first existed. This is what catches recycling — a real
2019 photograph presented as today's event — which the plan identifies as the
dominant Indian misinformation format, and which no deepfake detector can see.

The dating hierarchy, in the order it is actually used:

  1. **The matched page's own publish date**, extracted at fetch. Free, fast, and it
     carries the common case.
  2. **Structural disagreement**, when a page's stated date conflicts with its own
     metadata. A backdated article contradicts itself and that is citable.
  3. **Archive capture**, and only when a verdict genuinely hinges on a contested
     date. Optional, timeout-bounded, and no gate depends on it — an archive outage
     must cost a confirmation, not the flagship finding.

The asymmetry is deliberate: a page's own timestamp is editable by whoever runs the
page, so it is used as a claim to check rather than as an answer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.claim import Claim
from app.domain.enums import EvidenceKind, Method, Relation, Tier
from app.observability.logging import event
from app.sources.base import SourceCandidate, SourceRelation, SourceSnapshot, insufficient

logger = logging.getLogger("factify.temporal")

NAME = "temporal"
VERSION = "2026.08.1"

# How far apart an asserted date and the oldest known instance must be before the
# mismatch is a finding rather than editorial imprecision. A day covers timezone
# skew and "published late on the 15th, dated the 16th"; a month does not.
MISMATCH_THRESHOLD = timedelta(days=30)

# Beyond this the recycling is blatant and worth saying so plainly.
EGREGIOUS_THRESHOLD = timedelta(days=365)


@dataclass(frozen=True, slots=True)
class DatedInstance:
    """One known appearance of this content, and where the date came from."""

    url: str
    published_at: datetime
    publisher: str | None = None
    method: str = "matched_page_date"
    # The copy of the content at that appearance, when there is one to show.
    image_url: str | None = None

    @property
    def is_archive_confirmed(self) -> bool:
        return self.method == "archive_capture"


@dataclass(frozen=True, slots=True)
class TemporalFinding:
    """What the dates say."""

    relation: Relation
    reason: str
    oldest: DatedInstance | None = None
    asserted_at: datetime | None = None
    gap: timedelta | None = None

    @property
    def is_recycled(self) -> bool:
        """Genuine content, materially older than the date it is presented under."""
        return self.relation is Relation.CONTRADICTS and self.gap is not None

    @property
    def gap_description(self) -> str:
        if self.gap is None:
            return ""
        days = self.gap.days
        if days >= 365:
            return f"{days // 365} year(s) earlier"
        if days >= 30:
            return f"{days // 30} month(s) earlier"
        return f"{days} day(s) earlier"


def oldest_instance(instances: list[DatedInstance]) -> DatedInstance | None:
    """The earliest credible appearance.

    Archive confirmations win ties: a third-party capture is a timestamp the
    publisher could not have edited, and a page's own date is a claim.
    """
    if not instances:
        return None
    return min(
        instances, key=lambda instance: (instance.published_at, not instance.is_archive_confirmed)
    )


class TemporalResolver:
    """Compares an asserted date against the oldest instance actually found."""

    name = NAME
    version = VERSION
    allowed_domains: frozenset[str] = frozenset()

    # A dated page establishing that something predates what it is captioned as.
    # Tier B: strong, because a publication date is a checkable fact about a record.
    tier = Tier.B
    kind = EvidenceKind.DATED_SOURCE
    method = Method.MATCHED_PAGE_DATE

    def __init__(self, *, archive_enabled: bool = False) -> None:
        # Off by default. The flagship case must resolve from matched-page dates
        # alone, so that an archive outage on demo day costs a confirmation rather
        # than the finding.
        self._archive_enabled = archive_enabled

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        """Dating works over instances found by media matching, not by searching."""
        del claim
        return []

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        del candidate
        return None

    def assess(
        self,
        *,
        asserted_at: datetime | None,
        instances: list[DatedInstance],
        now: datetime | None = None,
    ) -> TemporalFinding:
        """Decide whether the content predates the date it is presented under."""
        del now

        if not instances:
            return TemporalFinding(
                relation=Relation.INSUFFICIENT,
                reason="no dated instance of this content was found",
            )

        oldest = oldest_instance(instances)
        assert oldest is not None

        if asserted_at is None:
            return TemporalFinding(
                relation=Relation.CONTEXTUALIZES,
                reason=(
                    f"Earliest known appearance: {oldest.published_at:%d %B %Y}"
                    f"{f' ({oldest.publisher})' if oldest.publisher else ''}."
                ),
                oldest=oldest,
            )

        gap = asserted_at - oldest.published_at

        if gap < MISMATCH_THRESHOLD:
            return TemporalFinding(
                relation=Relation.SUPPORTS,
                reason=(
                    f"Earliest appearance {oldest.published_at:%d %B %Y} is consistent "
                    "with the asserted date."
                ),
                oldest=oldest,
                asserted_at=asserted_at,
                gap=gap,
            )

        finding = TemporalFinding(
            relation=Relation.CONTRADICTS,
            reason="",
            oldest=oldest,
            asserted_at=asserted_at,
            gap=gap,
        )

        severity = "considerably " if gap >= EGREGIOUS_THRESHOLD else ""
        reason = (
            f"This content is {severity}older than presented. It appeared on "
            f"{oldest.published_at:%d %B %Y}"
            f"{f' via {oldest.publisher}' if oldest.publisher else ''}, "
            f"{finding.gap_description} than the asserted date of "
            f"{asserted_at:%d %B %Y}."
        )

        event(
            logger,
            "recycled content detected",
            module="sources.temporal",
            outcome="ok",
            gap_days=gap.days,
            archive_confirmed=oldest.is_archive_confirmed,
        )

        return TemporalFinding(
            relation=Relation.CONTRADICTS,
            reason=reason,
            oldest=oldest,
            asserted_at=asserted_at,
            gap=gap,
        )

    def needs_archive_confirmation(self, finding: TemporalFinding) -> bool:
        """Whether this verdict genuinely hinges on a contested date.

        The archive is consulted only here — for a borderline gap resting on a
        single unconfirmed page date. Everything clear-cut is already answered.
        """
        if not self._archive_enabled or finding.gap is None:
            return False
        if finding.oldest is not None and finding.oldest.is_archive_confirmed:
            return False
        return MISMATCH_THRESHOLD <= finding.gap < EGREGIOUS_THRESHOLD

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Relate a single dated page to a claim's asserted date."""
        if snapshot.published_at is None:
            return insufficient(NAME, VERSION, "source carries no publication date")

        finding = self.assess(
            asserted_at=_asserted_date(claim),
            instances=[
                DatedInstance(
                    url=snapshot.final_url,
                    published_at=snapshot.published_at,
                    publisher=snapshot.publisher,
                )
            ],
        )

        if finding.relation is Relation.INSUFFICIENT:
            return insufficient(NAME, VERSION, finding.reason)

        return SourceRelation(
            relation=finding.relation,
            validator=NAME,
            validator_version=VERSION,
            excerpt=finding.reason,
            anchor={"char_start": 0, "char_end": len(finding.reason)},
            metric="date_gap_days",
            value=float(finding.gap.days) if finding.gap else 0.0,
            threshold=float(MISMATCH_THRESHOLD.days),
        )


def _asserted_date(claim: Claim) -> datetime | None:
    """The date the claim asserts, if it stated one."""
    if not claim.entities and not claim.text:
        return None
    for raw in getattr(claim, "dates", ()) or ():
        try:
            return datetime.fromisoformat(str(raw)).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            continue
    return None
