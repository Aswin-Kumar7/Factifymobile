"""Every evidence tier, end to end.

How tiers are actually verified, in four independent places — this file exercises
all of them:

1. **A producer declares its tier.** Each resolver carries `tier`/`kind`/`method` as
   class attributes, so nothing downstream chooses. An assembler free to pick the
   tier per item could promote a weak finding into a strong one, which is precisely
   the judgement the tier system exists to remove from any single component.
2. **The method decides whether a tier can ever be decisive.** `can_be_decisive`
   gates on `Method`, not on tier — embedding similarity is candidate generation
   however good the tier looks.
3. **`match_quality` is derived, never asserted.** Evidence validates that the
   quality follows from the recorded metric and threshold, so a Tier A row with a
   forged quality cannot be constructed.
4. **Tier weight feeds the strength score.** A → 1.00, C → 0.95, B → 0.90, D → 0.70,
   multiplied by match quality.

The ordering in (4) is deliberate and worth stating: **C outranks B**. A published
adjudication by a named fact-checker is stronger than a dated page, because someone
staked their reputation on the conclusion rather than merely publishing on a date.
Only A beats it, because a signature is checkable without trusting anybody.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.enums import (
    Direction,
    EvidenceKind,
    Method,
    Relation,
    Tier,
)
from app.domain.evidence import can_be_decisive, derive_match_quality
from app.media.matching import MatchResult, StoredMedia
from app.media.provenance import ProvenanceReport
from app.sources.attribution import AttributionResolver, QuoteResolver
from app.sources.base import build_evidence
from app.sources.corroboration import CorroborationResolver
from app.sources.factcheck import FactCheckResolver
from app.sources.media import MediaMatchResolver, ProvenanceResolver
from app.sources.temporal import TemporalResolver
from app.verdict.strength import evidence_strength
from tests.unit import factories

pytestmark = pytest.mark.unit


# Every resolver in the system, with the tier it is responsible for. A new producer
# that forgets to declare one fails this file rather than silently defaulting.
ALL_RESOLVERS = [
    (ProvenanceResolver, Tier.A, EvidenceKind.PROVENANCE, Method.C2PA_VALIDATION),
    (MediaMatchResolver, Tier.B, EvidenceKind.MEDIA_MATCH, Method.NEAR_DUPLICATE_VERIFIED),
    (TemporalResolver, Tier.B, EvidenceKind.DATED_SOURCE, Method.MATCHED_PAGE_DATE),
    (FactCheckResolver, Tier.C, EvidenceKind.FACT_CHECK, Method.CLAIM_REVIEW),
    (CorroborationResolver, Tier.D, EvidenceKind.CORROBORATION, Method.ORIGIN_CLUSTER_COUNT),
    (AttributionResolver, Tier.D, EvidenceKind.ATTRIBUTION, Method.OFFICIAL_SOURCE),
    (QuoteResolver, Tier.D, EvidenceKind.QUOTE, Method.OFFICIAL_SOURCE),
]


class TestEveryTierHasAProducer:
    """The check that caught the real gap: Tier A had nobody producing it."""

    @pytest.mark.parametrize("tier", list(Tier))
    def test_each_tier_is_produced_by_something(self, tier: Tier) -> None:
        producers = [cls.__name__ for cls, t, _, _ in ALL_RESOLVERS if t is tier]

        assert producers, (
            f"Tier {tier.value} has no producer. A tier nothing can emit is a tier "
            "the ledger can never show, and the strength weighting silently assumes "
            "it exists."
        )

    @pytest.mark.parametrize(("resolver", "tier", "kind", "method"), ALL_RESOLVERS)
    def test_a_resolver_declares_its_own_tier(
        self, resolver: type, tier: Tier, kind: EvidenceKind, method: Method
    ) -> None:
        assert resolver.tier is tier
        assert resolver.kind is kind
        assert resolver.method is method

    def test_tier_e_is_not_in_the_tier_enum(self) -> None:
        """Advisory signals are a different type, not a weaker tier."""
        assert {t.value for t in Tier} == {"A", "B", "C", "D"}
        assert not hasattr(Tier, "E")


class TestWhichTiersCanBeDecisive:
    """Decisiveness is a property of the method, not of the tier."""

    @pytest.mark.parametrize(("_resolver", "_tier", "_kind", "method"), ALL_RESOLVERS)
    def test_every_producer_uses_a_decisive_capable_method(
        self, _resolver: type, _tier: Tier, _kind: EvidenceKind, method: Method
    ) -> None:
        """A producer whose method can never be decisive would emit rows that look
        like evidence and can never settle anything."""
        assert can_be_decisive(method)

    @pytest.mark.parametrize(
        "method",
        [Method.EMBEDDING_SIMILARITY, Method.SEARCH_SNIPPET, Method.DOMAIN_AGE],
    )
    def test_candidate_generation_methods_are_never_decisive(self, method: Method) -> None:
        """Embedding similarity is retrieval. A search snippet is not a fetched page.
        Domain age is a fact about a publisher, never about a claim."""
        assert not can_be_decisive(method)

    def test_a_high_tier_does_not_rescue_a_non_decisive_method(self) -> None:
        """Tier A with embedding similarity is still not decisive."""
        assert not can_be_decisive(Method.EMBEDDING_SIMILARITY)


class TestTierWeighting:
    """Tier weight drives the strength score, so the ordering is asserted."""

    @staticmethod
    def _score(tier: Tier) -> float:
        evidence = [factories.evidence(tier=tier, basis=factories.strong_basis())]
        return evidence_strength(evidence).score

    def test_a_outranks_everything(self) -> None:
        assert self._score(Tier.A) > self._score(Tier.C)
        assert self._score(Tier.A) > self._score(Tier.B)
        assert self._score(Tier.A) > self._score(Tier.D)

    def test_an_adjudication_outranks_a_dated_page(self) -> None:
        """C over B: someone staked their name on the conclusion, not just the date."""
        assert self._score(Tier.C) > self._score(Tier.B)

    def test_corroboration_is_the_weakest_tier(self) -> None:
        assert self._score(Tier.D) < self._score(Tier.B)

    def test_the_full_ordering_holds(self) -> None:
        assert self._score(Tier.A) > self._score(Tier.C) > self._score(Tier.B) > self._score(Tier.D)

    @pytest.mark.parametrize("tier", list(Tier))
    def test_a_weak_match_scores_below_a_strong_one_at_the_same_tier(self, tier: Tier) -> None:
        """Tier is not a free pass: a barely-cleared threshold scores lower."""
        strong = evidence_strength(
            [factories.evidence(tier=tier, basis=factories.strong_basis())]
        ).score
        weak = evidence_strength(
            [factories.evidence(tier=tier, basis=factories.weak_basis())]
        ).score

        assert weak < strong

    def test_a_weak_tier_a_can_score_below_a_strong_tier_d(self) -> None:
        """Quality is not decorative — it can invert the tier ordering, which is the
        point of multiplying rather than ranking."""
        weak_a = evidence_strength(
            [factories.evidence(tier=Tier.A, basis=factories.weak_basis())]
        ).score
        strong_d = evidence_strength(
            [factories.evidence(tier=Tier.D, basis=factories.strong_basis())]
        ).score

        assert weak_a < strong_d


class TestMatchQualityIsDerivedAtEveryTier:
    """Invariant 5, checked per tier rather than once."""

    @pytest.mark.parametrize("tier", list(Tier))
    def test_quality_follows_the_metric_not_the_tier(self, tier: Tier) -> None:
        strong = factories.evidence(tier=tier, basis=factories.strong_basis())
        weak = factories.evidence(tier=tier, basis=factories.weak_basis())

        assert strong.match_quality is derive_match_quality(strong.match_basis)
        assert weak.match_quality is derive_match_quality(weak.match_basis)
        assert strong.match_quality is not weak.match_quality

    @pytest.mark.parametrize("tier", list(Tier))
    def test_a_forged_quality_is_rejected(self, tier: Tier) -> None:
        """A component cannot upgrade its own evidence, whatever tier it claims."""
        from app.domain.enums import MatchQuality
        from app.domain.evidence import Evidence

        with pytest.raises(ValueError, match="does not follow from"):
            Evidence(
                id="ev:forged",
                claim_id="cl_1",
                tier=tier,
                kind=EvidenceKind.FACT_CHECK,
                direction=Direction.CONTRADICTS,
                method=Method.CLAIM_REVIEW,
                finding="a finding",
                citation_url="https://example.org/x",
                snapshot_id="snap:1",
                source_excerpt="quoted text",
                source_anchor=factories.evidence().source_anchor,
                match_basis=factories.weak_basis(),
                match_quality=MatchQuality.STRONG,
            )


# ------------------------------------------------------- producers, tier by tier


def _snapshot(**overrides: Any):
    from app.sources.base import SourceSnapshot

    base: dict[str, Any] = {
        "id": "snap:1",
        "url": "https://example.org/story",
        "final_url": "https://example.org/story",
        "content_hash": "sha256:abc123def456",
        "fetched_at": datetime(2019, 3, 14, tzinfo=UTC),
        "text": "the quoted passage",
        "title": "A story",
        "publisher": "Example Wire",
        "published_at": datetime(2019, 3, 14, tzinfo=UTC),
    }
    base.update(overrides)
    return SourceSnapshot(**base)


class TestTierAProvenance:
    """The tier that had no producer until now."""

    @pytest.mark.anyio
    async def test_a_validated_manifest_produces_tier_a_evidence(self) -> None:
        resolver = ProvenanceResolver(
            report=ProvenanceReport(present=True, valid=True, signer="Example CA")
        )
        claim = factories.claim()

        candidates = await resolver.candidates(claim)
        assert candidates

        snapshot = await resolver.snapshot(candidates[0])
        assert snapshot is not None

        relation = await resolver.relate(claim, snapshot)
        evidence = build_evidence(
            resolver=resolver, claim_id=claim.id, snapshot=snapshot, relation=relation
        )

        assert evidence is not None
        assert evidence.tier is Tier.A
        assert evidence.method is Method.C2PA_VALIDATION

    @pytest.mark.anyio
    async def test_provenance_never_supports_a_claim(self) -> None:
        """A signed photograph of a staged scene is a signed photograph of a staged
        scene. Supporting would turn provenance into a statement about the world."""
        resolver = ProvenanceResolver(
            report=ProvenanceReport(present=True, valid=True, signer="Example CA")
        )
        claim = factories.claim()
        snapshot = await resolver.snapshot((await resolver.candidates(claim))[0])
        assert snapshot is not None

        relation = await resolver.relate(claim, snapshot)

        assert relation.relation is Relation.CONTEXTUALIZES
        evidence = build_evidence(
            resolver=resolver, claim_id=claim.id, snapshot=snapshot, relation=relation
        )
        assert evidence is not None
        assert evidence.direction is Direction.CONTEXTUALIZES

    @pytest.mark.anyio
    async def test_a_missing_manifest_produces_nothing(self) -> None:
        """Absence is the normal case and must not become a negative finding."""
        resolver = ProvenanceResolver(report=ProvenanceReport(present=False))

        assert await resolver.candidates(factories.claim()) == []

    @pytest.mark.anyio
    async def test_an_invalid_manifest_produces_nothing(self) -> None:
        resolver = ProvenanceResolver(
            report=ProvenanceReport(present=True, valid=False, validation_errors=("signing",))
        )

        assert await resolver.candidates(factories.claim()) == []

    @pytest.mark.anyio
    async def test_no_report_at_all_produces_nothing(self) -> None:
        assert await ProvenanceResolver().candidates(factories.claim()) == []


class TestTierBMediaMatch:
    """The other tier that had no path into the ledger."""

    @staticmethod
    def _match(*, dated: bool = True) -> MatchResult:
        return MatchResult(
            matched=StoredMedia(
                id="media:1",
                sha256="sha256:original",
                source_date=datetime(2019, 3, 14, tzinfo=UTC) if dated else None,
                citation_url="https://example.org/2019/story" if dated else None,
                publisher="Example Wire",
            ),
            method="near_duplicate_verified",
            similarity=0.97,
        )

    @pytest.mark.anyio
    async def test_a_dated_match_produces_tier_b_evidence(self) -> None:
        resolver = MediaMatchResolver(result=self._match())
        claim = factories.claim()

        candidates = await resolver.candidates(claim)
        assert candidates

        snapshot = await resolver.snapshot(candidates[0])
        assert snapshot is not None

        relation = await resolver.relate(claim, snapshot)
        evidence = build_evidence(
            resolver=resolver, claim_id=claim.id, snapshot=snapshot, relation=relation
        )

        assert evidence is not None
        assert evidence.tier is Tier.B
        assert evidence.direction is Direction.CONTRADICTS
        assert "2019" in evidence.source_excerpt
        assert "Example Wire" in evidence.source_excerpt

    @pytest.mark.anyio
    async def test_an_undated_match_produces_nothing(self) -> None:
        """'We have seen this image' is not a finding. When and where is."""
        resolver = MediaMatchResolver(result=self._match(dated=False))

        assert await resolver.candidates(factories.claim()) == []

    @pytest.mark.anyio
    async def test_a_miss_produces_nothing(self) -> None:
        resolver = MediaMatchResolver(result=MatchResult(reason="no candidate in range"))

        assert await resolver.candidates(factories.claim()) == []

    @pytest.mark.anyio
    async def test_the_citation_points_at_the_earlier_publication(self) -> None:
        resolver = MediaMatchResolver(result=self._match())
        claim = factories.claim()
        snapshot = await resolver.snapshot((await resolver.candidates(claim))[0])
        assert snapshot is not None

        evidence = build_evidence(
            resolver=resolver,
            claim_id=claim.id,
            snapshot=snapshot,
            relation=await resolver.relate(claim, snapshot),
        )

        assert evidence is not None
        assert evidence.citation_url == "https://example.org/2019/story"
        assert evidence.publisher == "Example Wire"


class TestBuildEvidenceAcrossTiers:
    """The assembler applies the resolver's declared tier and nothing else."""

    @pytest.mark.parametrize(("resolver_cls", "tier", "kind", "method"), ALL_RESOLVERS)
    def test_the_declared_tier_reaches_the_evidence(
        self, resolver_cls: type, tier: Tier, kind: EvidenceKind, method: Method
    ) -> None:
        from app.sources.base import SourceRelation

        class _Stub:
            name = "stub"
            version = "v"
            allowed_domains: frozenset[str] = frozenset()

        stub = _Stub()
        stub.tier = tier  # type: ignore[attr-defined]
        stub.kind = kind  # type: ignore[attr-defined]
        stub.method = method  # type: ignore[attr-defined]

        evidence = build_evidence(
            resolver=stub,  # type: ignore[arg-type]
            claim_id="cl_1",
            snapshot=_snapshot(),
            relation=SourceRelation(
                relation=Relation.CONTRADICTS,
                validator="stub",
                validator_version="v",
                excerpt="the quoted passage",
                anchor={"char_start": 0, "char_end": 18},
                metric="overlap",
                value=0.9,
                threshold=0.5,
            ),
        )

        assert evidence is not None
        assert evidence.tier is tier
        assert evidence.kind is kind
        assert evidence.method is method

    def test_an_insufficient_relation_produces_no_evidence_at_any_tier(self) -> None:
        from app.sources.base import insufficient

        class _Stub:
            name = "stub"
            version = "v"
            allowed_domains: frozenset[str] = frozenset()
            tier = Tier.A
            kind = EvidenceKind.PROVENANCE
            method = Method.C2PA_VALIDATION

        assert (
            build_evidence(
                resolver=_Stub(),  # type: ignore[arg-type]
                claim_id="cl_1",
                snapshot=_snapshot(),
                relation=insufficient("stub", "v", "could not anchor"),
            )
            is None
        )

    def test_a_not_relevant_relation_produces_no_evidence(self) -> None:
        from app.sources.base import SourceRelation

        class _Stub:
            name = "stub"
            version = "v"
            allowed_domains: frozenset[str] = frozenset()
            tier = Tier.C
            kind = EvidenceKind.FACT_CHECK
            method = Method.CLAIM_REVIEW

        assert (
            build_evidence(
                resolver=_Stub(),  # type: ignore[arg-type]
                claim_id="cl_1",
                snapshot=_snapshot(),
                relation=SourceRelation(
                    relation=Relation.NOT_RELEVANT,
                    validator="stub",
                    validator_version="v",
                    excerpt="unrelated text",
                    metric="overlap",
                    value=0.1,
                    threshold=0.5,
                ),
            )
            is None
        )


class TestMixedTierSets:
    """What happens when several tiers speak at once."""

    def test_the_best_tier_dominates_the_score(self) -> None:
        weak_only = evidence_strength([factories.evidence(tier=Tier.D)])
        with_strong = evidence_strength(
            [factories.evidence(tier=Tier.D), factories.evidence(tier=Tier.A)]
        )

        assert with_strong.score > weak_only.score

    def test_every_tier_is_cited_in_the_output(self) -> None:
        evidence = [factories.evidence(tier=tier) for tier in Tier]
        strength = evidence_strength(evidence)

        assert len(strength.citations) == len(evidence)

    def test_a_conflict_across_tiers_is_penalised(self) -> None:
        from app.domain.enums import Direction as D

        agreeing = evidence_strength(
            [
                factories.evidence(tier=Tier.C, direction=D.CONTRADICTS),
                factories.evidence(tier=Tier.B, direction=D.CONTRADICTS),
            ]
        )
        conflicting = evidence_strength(
            [
                factories.evidence(tier=Tier.C, direction=D.CONTRADICTS),
                factories.evidence(tier=Tier.B, direction=D.SUPPORTS),
            ]
        )

        assert conflicting.score < agreeing.score
