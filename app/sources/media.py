"""Media evidence producers — Tier A and Tier B.

Closes two gaps that only became visible once the orchestrator asked every resolver
what tier it produces: **Tier A had no producer at all**, and Tier B was reachable
only through page dating. C2PA validation and media matching both existed as modules
(M33, M36) but neither had a path into the evidence ledger, so a validated content
credential and a verified recycled photograph could not appear as citations.

The two are deliberately narrow about what they claim:

  - **Provenance (Tier A)** attests that bytes were signed by an identifiable signer.
    It never says the depicted event happened. A signed photograph of a staged scene
    is a validly signed photograph of a staged scene, so the direction is always
    `CONTEXTUALIZES` — it adds provenance, it does not settle the claim.
  - **Media match (Tier B)** says this image was published earlier, by whom, and
    when. That *is* decisive against a claim that it depicts today's event, which is
    why it contradicts rather than contextualises — but only when a date and a
    citation exist. Without both there is no finding, only a resemblance.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.domain.claim import Claim
from app.domain.enums import EvidenceKind, Method, Relation, Tier
from app.media.matching import MatchResult
from app.media.provenance import ProvenanceReport
from app.observability.logging import event
from app.sources.base import SourceCandidate, SourceRelation, SourceSnapshot, insufficient

logger = logging.getLogger("factify.sources.media")

PROVENANCE_NAME = "provenance"
MEDIA_MATCH_NAME = "media_match"
VERSION = "2026.08.1"


class ProvenanceResolver:
    """Tier A — a validated content credential.

    The only Tier A producer. Tier A outranks everything else in the strength
    weighting precisely because a cryptographic signature is checkable without
    trusting us, so the bar for emitting one is a manifest that actually validated.
    """

    name = PROVENANCE_NAME
    version = VERSION
    allowed_domains: frozenset[str] = frozenset()

    tier = Tier.A
    kind = EvidenceKind.PROVENANCE
    method = Method.C2PA_VALIDATION

    def __init__(self, *, report: ProvenanceReport | None = None) -> None:
        self._report = report

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        """Only when a manifest validated.

        Absence produces no candidate rather than a negative one: almost nothing
        carries credentials, and a "no manifest" evidence row would turn the normal
        case into a finding.
        """
        del claim
        if self._report is None or not self._report.present or not self._report.valid:
            return []

        return [
            SourceCandidate(
                url=f"c2pa:{self._report.signer or 'unnamed'}",
                publisher=self._report.signer,
                title="Content credentials",
                published_at=self._report.created_at,
                proposed_by="c2pa_manifest",
                prior_score=1.0,
            )
        ]

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        """The manifest is its own snapshot — it was read from the asset itself."""
        if self._report is None:
            return None

        return SourceSnapshot(
            id=f"c2pa:{candidate.url}",
            url=candidate.url,
            final_url=candidate.url,
            content_hash=f"manifest:{self._report.signer or 'unnamed'}",
            fetched_at=self._report.created_at or datetime.now(UTC),
            text=self._report.summary,
            title="Content credentials",
            publisher=self._report.signer,
            published_at=self._report.created_at,
        )

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Always contextualises. There is no path here to supporting a claim.

        A valid manifest binds an assertion to an asset — it is evidence about the
        file, not about the world. Returning `SUPPORTS` would let a signed image of
        a staged scene read as confirmation that the scene was real.
        """
        del claim
        if self._report is None or not self._report.valid:
            return insufficient(PROVENANCE_NAME, VERSION, "no validated manifest")

        excerpt = self._report.summary
        event(
            logger,
            "provenance evidence emitted",
            module="sources.media",
            outcome="ok",
            tier=Tier.A.value,
            signer=self._report.signer,
        )

        return SourceRelation(
            relation=Relation.CONTEXTUALIZES,
            validator=PROVENANCE_NAME,
            validator_version=VERSION,
            excerpt=excerpt,
            anchor={"char_start": 0, "char_end": len(excerpt)},
            metric="c2pa_validation",
            # A signature either validates or it does not; there is no partial
            # credit, so the metric is binary and the threshold is the same.
            value=1.0,
            threshold=1.0,
        )


class MediaMatchResolver:
    """Tier B — this image was published earlier, by whom, and when.

    Emits evidence only when the match carries a date *and* a citation. A verified
    match to undated material establishes that the picture existed somewhere, which
    is not a finding; the finding is always about when and where.
    """

    name = MEDIA_MATCH_NAME
    version = VERSION
    allowed_domains: frozenset[str] = frozenset()

    tier = Tier.B
    kind = EvidenceKind.MEDIA_MATCH
    method = Method.NEAR_DUPLICATE_VERIFIED

    def __init__(self, *, result: MatchResult | None = None) -> None:
        self._result = result

    async def candidates(self, claim: Claim) -> list[SourceCandidate]:
        del claim
        if self._result is None or not self._result.is_citable:
            return []

        matched = self._result.matched
        assert matched is not None  # is_citable implies it

        return [
            SourceCandidate(
                url=matched.citation_url or "",
                publisher=matched.publisher,
                title="Earlier publication of this image",
                published_at=matched.source_date,
                proposed_by="local_media_corpus",
                prior_score=self._result.similarity,
            )
        ]

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None:
        if self._result is None or self._result.matched is None:
            return None

        matched = self._result.matched
        assert matched.source_date is not None  # is_citable was checked upstream

        return SourceSnapshot(
            id=f"media:{matched.id}",
            url=candidate.url,
            final_url=candidate.url,
            content_hash=matched.sha256,
            fetched_at=matched.source_date,
            text=self._describe(matched.publisher, matched.source_date),
            title="Earlier publication of this image",
            publisher=matched.publisher,
            published_at=matched.source_date,
        )

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation:
        """Contradicts a claim that this depicts something recent.

        The exact-hash case is reported with its own method, because byte-identity is
        proof on its own while a near-duplicate rests on a threshold, and the ledger
        should not describe the two as the same kind of finding.
        """
        del claim
        if self._result is None or not self._result.is_citable:
            return insufficient(MEDIA_MATCH_NAME, VERSION, "no dated media match")

        excerpt = snapshot.text
        event(
            logger,
            "media match evidence emitted",
            module="sources.media",
            outcome="ok",
            tier=Tier.B.value,
            method=self._result.method,
            similarity=round(self._result.similarity, 4),
        )

        return SourceRelation(
            relation=Relation.CONTRADICTS,
            validator=MEDIA_MATCH_NAME,
            validator_version=VERSION,
            excerpt=excerpt,
            anchor={"char_start": 0, "char_end": len(excerpt)},
            metric="clip_cosine" if self._result.method != "exact_hash" else "sha256",
            value=self._result.similarity,
            threshold=1.0 if self._result.method == "exact_hash" else 0.93,
        )

    @staticmethod
    def _describe(publisher: str | None, when: datetime | None) -> str:
        who = publisher or "an earlier source"
        date = when.strftime("%d %B %Y") if when else "an earlier date"
        return f"This image was published by {who} on {date}."


def exact_match_method(result: MatchResult) -> Method:
    """Which method a match should be recorded under.

    Byte-identity is proof by itself; a near-duplicate is a threshold judgement. Both
    can be decisive, but conflating them would hide which one actually happened.
    """
    return Method.EXACT_HASH if result.method == "exact_hash" else Method.NEAR_DUPLICATE_VERIFIED
