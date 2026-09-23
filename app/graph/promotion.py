"""Observation recording and promotion (M38).

Grows the corpus from usage without letting usage poison it.

Every request writes an observation, whatever the outcome. An observation is **not**
evidence: it records that somebody asked about something, which is a fact about our
traffic and not a fact about the world. The two live in different tables and reach
the user through different surfaces.

Promotion is the narrow gate between them, and it exists because of one specific
attack: **a recurrence counter that rises on submission is a counter an attacker
owns.** Submit the same fabricated image five hundred times and "seen 500 times,
first seen three years ago" becomes a sentence the product will say — with no source,
no citation and no verification behind it. That reads as authority and is worth
exactly nothing.

So repetition promotes nothing, ever. `times_seen` moves only when a submission was
matched against dated, citable material or reviewed by a person — and the reason is
carried on the promotion so the counter can always be explained.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.db.repositories import FingerprintRepository, ObservationRepository
from app.domain.enums import ClaimStatus
from app.observability.logging import event

logger = logging.getLogger("factify.graph.promotion")


class TrustState(StrEnum):
    """How far an observation has travelled toward being trusted.

    The values match the `observation.trust_state` check constraint, so an invalid
    state is rejected by the database as well as here.
    """

    RAW = "raw"
    VALIDATED = "validated"
    PROMOTED = "promoted"


class ObservationKind(StrEnum):
    """What was observed. Kept coarse — this is traffic, not taxonomy."""

    SUBMISSION = "submission"
    CLAIM_EXTRACTED = "claim_extracted"
    MEDIA_SUBMITTED = "media_submitted"
    CAPTION_SEEN = "caption_seen"


class PromotionBasis(StrEnum):
    """Why something earned promotion. There are exactly two legitimate reasons.

    Both terminate in something outside the submission itself: a dated citation, or
    a person's judgement. Neither can be manufactured by submitting more.
    """

    VALIDATED_MATCH = "validated_match"
    REVIEWED_FINDING = "reviewed_finding"


@dataclass(frozen=True, slots=True)
class PromotionRefused:
    """Why a promotion did not happen. Returned, not raised.

    A refusal is the ordinary case — most traffic is unverified content — so it is a
    value the caller handles rather than an exception the caller catches.
    """

    reason: str

    @property
    def promoted(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Promoted:
    """A fingerprint that moved, and what moved it."""

    fingerprint_id: UUID
    basis: PromotionBasis
    times_seen: int
    first_verified_at: datetime | None

    @property
    def promoted(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class MatchWarrant:
    """The evidence that a media match is real enough to promote.

    Deliberately not a `MatchResult` from the media layer: this asks only the
    questions promotion depends on, so a change to matching internals cannot quietly
    alter what qualifies. Both fields must hold — a verified match to undated
    material tells us the image existed, not when, and "when" is the entire finding.
    """

    verified: bool
    source_date: datetime | None
    citation_url: str | None
    matched_sha256: str | None = None

    @property
    def is_sufficient(self) -> bool:
        return bool(self.verified and self.source_date and self.citation_url)

    @property
    def shortfall(self) -> str:
        if not self.verified:
            return "the match did not pass visual verification"
        if not self.source_date:
            return "the matched material carries no publication date"
        if not self.citation_url:
            return "the matched material has no citable URL"
        return ""


class PromotionGate:
    """Writes observations always; promotes only on a warrant."""

    def __init__(
        self,
        *,
        observations: ObservationRepository,
        fingerprints: FingerprintRepository,
    ) -> None:
        self._observations = observations
        self._fingerprints = fingerprints

    async def observe(
        self,
        *,
        kind: ObservationKind,
        case_id: UUID | None = None,
        content_object_id: UUID | None = None,
        claim_id: UUID | None = None,
        raw_claim: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> UUID:
        """Record that this was submitted. Unconditional, and never promoting.

        Called on every request including the ones that resolve to nothing, because
        an observation the pipeline declined to act on is still the record that
        somebody asked.
        """
        observation_id = await self._observations.record(
            kind=kind.value,
            case_id=case_id,
            content_object_id=content_object_id,
            claim_id=claim_id,
            raw_claim=raw_claim,
            detail=dict(detail or {}),
        )

        event(
            logger,
            "observation recorded",
            module="graph.promotion",
            outcome="ok",
            kind=kind.value,
            trust_state=TrustState.RAW.value,
        )
        return observation_id

    async def promote_match(
        self,
        *,
        sha256: str,
        warrant: MatchWarrant,
        phash: str | None = None,
        verdict: ClaimStatus | None = None,
        observation_id: UUID | None = None,
    ) -> Promoted | PromotionRefused:
        """Promote a media fingerprint, if the warrant holds.

        The warrant is checked here rather than trusted from the caller. A caller
        that has already decided the match is good is exactly the caller that would
        skip the date check.
        """
        if not warrant.is_sufficient:
            event(
                logger,
                "promotion refused",
                module="graph.promotion",
                outcome="rejected",
                failure_reason=warrant.shortfall,
            )
            return PromotionRefused(reason=warrant.shortfall)

        return await self._write(
            sha256=sha256,
            phash=phash,
            basis=PromotionBasis.VALIDATED_MATCH,
            verdict=verdict,
            source_date=warrant.source_date,
            citation_url=warrant.citation_url,
            observation_id=observation_id,
        )

    async def promote_reviewed(
        self,
        *,
        sha256: str,
        citation_url: str,
        source_date: datetime | None = None,
        phash: str | None = None,
        verdict: ClaimStatus | None = None,
        observation_id: UUID | None = None,
    ) -> Promoted | PromotionRefused:
        """Promote a finding a person reviewed and accepted.

        The second legitimate basis. A citation is still required: review establishes
        that a human judged the finding sound, not that a source exists, and the
        trusted store holds only things that can be pointed at.
        """
        if not citation_url:
            return PromotionRefused(reason="a reviewed finding still requires a citation")

        return await self._write(
            sha256=sha256,
            phash=phash,
            basis=PromotionBasis.REVIEWED_FINDING,
            verdict=verdict,
            source_date=source_date,
            citation_url=citation_url,
            observation_id=observation_id,
        )

    async def _write(
        self,
        *,
        sha256: str,
        phash: str | None,
        basis: PromotionBasis,
        verdict: ClaimStatus | None,
        source_date: datetime | None,
        citation_url: str | None,
        observation_id: UUID | None,
    ) -> Promoted:
        """The single path that moves `times_seen`. There is deliberately no other."""
        fingerprint_id = await self._fingerprints.promote(
            sha256=sha256,
            phash=phash,
            last_verdict=verdict.value if verdict else None,
            source_date=source_date,
            citation_url=citation_url,
        )

        if observation_id is not None:
            await self._observations.mark(observation_id, TrustState.PROMOTED.value)

        row = await self._fingerprints.get(sha256)
        times_seen = int(row["times_seen"]) if row else 1
        first_verified = row["first_verified_at"] if row else None

        event(
            logger,
            "fingerprint promoted",
            module="graph.promotion",
            outcome="ok",
            basis=basis.value,
            times_seen=times_seen,
        )

        return Promoted(
            fingerprint_id=fingerprint_id,
            basis=basis,
            times_seen=times_seen,
            first_verified_at=first_verified,
        )

    async def record_caption(
        self,
        *,
        fingerprint_id: UUID,
        caption_text: str | None,
        language: str | None = None,
        source_domain: str | None = None,
        claim_id: UUID | None = None,
        case_id: UUID | None = None,
    ) -> UUID | None:
        """Attach a caption to a promoted fingerprint.

        Captions hang off the trusted store because M39 renders them as "this image
        has carried these narratives". Recording one against an unpromoted
        fingerprint would put unverified user text into a view the user reads as
        established history, so callers must promote first — the foreign key makes
        that structural rather than advisory.
        """
        if not caption_text:
            return None

        return await self._fingerprints.record_occurrence(
            fingerprint_id=fingerprint_id,
            caption_text=caption_text,
            language=language,
            source_domain=source_domain,
            claim_id=claim_id,
            case_id=case_id,
        )
