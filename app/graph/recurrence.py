"""Recurrence and caption variants (M39).

The "identify misinformation patterns" deliverable, and the strongest thing the
product can show that a per-request classifier structurally cannot: *this exact image
has been circulating for three years, and here are the four different stories it has
been told with.*

Both views are queries over what M38 promoted. No new pipeline, no new retrieval —
which is the point. The compounding value comes from having written the right things
down, not from computing something clever at read time.

**The counting rule.** A user-facing recurrence figure counts promoted verifications
only. Raw observations are traffic; presenting them as recurrence would let anyone
manufacture "seen 500 times" by submitting 500 times, and the number would be reported
in the same typeface as everything else the product says. When there is nothing
promoted, these views say so rather than falling back to the observation count.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.db.repositories import FingerprintRepository
from app.observability.logging import event

logger = logging.getLogger("factify.graph.recurrence")

# Below this, "recurring" overstates it. Two sightings is a coincidence worth
# recording and not a pattern worth announcing.
MIN_SIGHTINGS_TO_CALL_IT_RECURRING = 3


@dataclass(frozen=True, slots=True)
class CaptionVariant:
    """One narrative attached to a piece of media at one point in time."""

    caption: str
    observed_at: datetime
    language: str | None = None
    source_domain: str | None = None


@dataclass(frozen=True, slots=True)
class RecurrenceReport:
    """What is truthfully known about a fingerprint's history.

    Every field here is derived from promoted rows. `is_known` distinguishes "we have
    never verified this" from "we verified it once", which are different answers and
    must not render as the same empty state.
    """

    sha256: str
    times_seen: int = 0
    first_verified_at: datetime | None = None
    last_verified_at: datetime | None = None
    last_verdict: str | None = None
    source_date: datetime | None = None
    citation_url: str | None = None
    captions: tuple[CaptionVariant, ...] = field(default_factory=tuple)

    @property
    def is_known(self) -> bool:
        return self.times_seen > 0

    @property
    def is_recurring(self) -> bool:
        return self.times_seen >= MIN_SIGHTINGS_TO_CALL_IT_RECURRING

    @property
    def age(self) -> str | None:
        """How long this has been circulating, from the first verification.

        Reported from `first_verified_at` — when *we* first confirmed it — and never
        from `source_date`, which is when the source published. Conflating them would
        claim we have been watching something since 2019 when the corpus is weeks old.
        """
        if self.first_verified_at is None:
            return None

        days = (datetime.now(UTC) - self.first_verified_at).days
        if days < 1:
            return "today"
        if days == 1:
            return "since yesterday"
        if days < 30:
            return f"over {days} days"
        if days < 365:
            return f"over {days // 30} months"
        years = days // 365
        return "over a year" if years == 1 else f"over {years} years"

    @property
    def distinct_captions(self) -> int:
        return len({variant.caption.strip().lower() for variant in self.captions})

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(sorted({v.language for v in self.captions if v.language}))

    @property
    def has_contradictory_captions(self) -> bool:
        """Whether one piece of media has carried several different stories.

        The strongest single signal available without any model: an authentic
        photograph does not acquire four mutually exclusive captions by accident.
        """
        return self.distinct_captions >= 2

    def summary(self) -> str:
        """The line a user reads. Says nothing that is not counted above."""
        if not self.is_known:
            return "This has not been verified before."

        times = "once" if self.times_seen == 1 else f"{self.times_seen} times"
        line = f"Verified {times}"
        if self.age:
            line += f", {self.age}"

        if self.has_contradictory_captions:
            captions = self.distinct_captions
            line += f". It has appeared with {captions} different captions"
            languages = self.languages
            if len(languages) > 1:
                line += f" across {len(languages)} languages"

        return line + "."


@dataclass(frozen=True, slots=True)
class CaptionTimeline:
    """The contradictory-caption view: one image, several narratives, over time."""

    sha256: str
    variants: tuple[CaptionVariant, ...] = field(default_factory=tuple)

    @property
    def is_renderable(self) -> bool:
        """Two distinct captions is the minimum that makes the view mean anything."""
        return len({v.caption.strip().lower() for v in self.variants}) >= 2

    @property
    def by_domain(self) -> tuple[tuple[str, int], ...]:
        counts = Counter(v.source_domain for v in self.variants if v.source_domain)
        return tuple(counts.most_common())

    @property
    def span(self) -> tuple[datetime, datetime] | None:
        if not self.variants:
            return None
        stamps = sorted(v.observed_at for v in self.variants)
        return stamps[0], stamps[-1]


class RecurrenceService:
    """Reads the write-back stores. Never writes, never promotes."""

    def __init__(self, *, fingerprints: FingerprintRepository) -> None:
        self._fingerprints = fingerprints

    async def report(self, sha256: str) -> RecurrenceReport:
        """Everything truthfully known about this fingerprint.

        An unknown fingerprint returns an empty report rather than raising: "we have
        not seen this" is a legitimate answer and by far the most common one.
        """
        row = await self._fingerprints.get(sha256)
        if row is None:
            return RecurrenceReport(sha256=sha256)

        variants = await self._captions(UUID(str(row["id"])))

        report = RecurrenceReport(
            sha256=sha256,
            times_seen=int(row["times_seen"]),
            first_verified_at=row["first_verified_at"],
            last_verified_at=row["last_verified_at"],
            last_verdict=row["last_verdict"],
            source_date=row["source_date"],
            citation_url=row["citation_url"],
            captions=variants,
        )

        event(
            logger,
            "recurrence report",
            module="graph.recurrence",
            outcome="ok",
            times_seen=report.times_seen,
            distinct_captions=report.distinct_captions,
            recurring=report.is_recurring,
        )
        return report

    async def timeline(self, sha256: str) -> CaptionTimeline:
        """The captions this media has carried, oldest first."""
        row = await self._fingerprints.get(sha256)
        if row is None:
            return CaptionTimeline(sha256=sha256)

        return CaptionTimeline(sha256=sha256, variants=await self._captions(UUID(str(row["id"]))))

    async def _captions(self, fingerprint_id: UUID) -> tuple[CaptionVariant, ...]:
        rows = await self._fingerprints.occurrences(fingerprint_id)
        return tuple(
            CaptionVariant(
                caption=str(row["caption_text"]),
                observed_at=row["observed_at"],
                language=row["language"],
                source_domain=row["source_domain"],
            )
            for row in rows
            if row["caption_text"]
        )
