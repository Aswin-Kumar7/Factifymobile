"""M05 — the domain types, and the invariants they make structural."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain import (
    Advisory,
    ClaimAnchor,
    ClaimStatus,
    Evidence,
    MatchBasis,
    MatchQuality,
    Method,
    SourceAnchor,
    can_be_decisive,
    derive_match_quality,
)
from tests.unit.factories import evidence, moderate_basis, strong_basis, weak_basis

pytestmark = pytest.mark.unit


class TestEvidenceCannotExistWithoutACitation:
    """Invariant 4, enforced at construction so an invalid object cannot exist."""

    @pytest.mark.parametrize(
        "missing", ["citation_url", "snapshot_id", "source_excerpt", "source_anchor"]
    )
    def test_missing_required_provenance_field_is_rejected(self, missing: str) -> None:
        fields = {
            "id": "ev_1",
            "claim_id": "cl_1",
            "tier": "C",
            "kind": "fact_check",
            "direction": "contradicts",
            "method": "claim_review",
            "finding": "finding",
            "citation_url": "https://example.org/a",
            "snapshot_id": "snap_1",
            "source_excerpt": "excerpt",
            "source_anchor": SourceAnchor(paragraph_index=1),
            "match_basis": strong_basis(),
            "match_quality": MatchQuality.STRONG,
        }
        del fields[missing]

        with pytest.raises(ValidationError):
            Evidence(**fields)  # type: ignore[arg-type]

    @pytest.mark.parametrize("blank", ["citation_url", "snapshot_id", "source_excerpt"])
    def test_empty_string_does_not_satisfy_the_requirement(self, blank: str) -> None:
        """A blank citation is the same as no citation, and must fail the same way."""
        with pytest.raises(ValidationError):
            evidence(**{blank: ""})

    def test_evidence_has_no_confidence_field(self) -> None:
        """A free-text confidence has no defined author; the field must not exist."""
        assert "confidence" not in Evidence.model_fields

        with pytest.raises(ValidationError):
            evidence(confidence="high")


class TestMatchQualityIsDerived:
    """Invariant 5 — every ordinal field traces to a recorded metric."""

    def test_comfortable_margin_derives_strong(self) -> None:
        assert derive_match_quality(strong_basis()) is MatchQuality.STRONG

    def test_bare_pass_derives_moderate(self) -> None:
        assert derive_match_quality(moderate_basis()) is MatchQuality.MODERATE

    def test_below_threshold_derives_weak(self) -> None:
        assert derive_match_quality(weak_basis()) is MatchQuality.WEAK

    def test_asserted_quality_that_contradicts_the_metric_is_rejected(self) -> None:
        """A component cannot quietly upgrade its own evidence."""
        with pytest.raises(ValidationError, match="does not follow from match_basis"):
            Evidence(
                id="ev_1",
                claim_id="cl_1",
                tier="C",
                kind="fact_check",
                direction="contradicts",
                method="claim_review",
                finding="finding",
                citation_url="https://example.org/a",
                snapshot_id="snap_1",
                source_excerpt="excerpt",
                source_anchor=SourceAnchor(paragraph_index=1),
                match_basis=weak_basis(),
                match_quality=MatchQuality.STRONG,
            )

    def test_derivation_is_reproducible_by_a_reader(self) -> None:
        """The whole point: recompute from what was written down and agree."""
        item = evidence(basis=MatchBasis(metric="hamming", value=0.93, threshold=0.90))

        assert item.match_quality is derive_match_quality(item.match_basis)


class TestDecisiveMethods:
    """The validators table from §3, as code."""

    @pytest.mark.parametrize(
        "method",
        [Method.EMBEDDING_SIMILARITY, Method.SEARCH_SNIPPET, Method.DOMAIN_AGE],
    )
    def test_candidate_only_methods_can_never_decide(self, method: Method) -> None:
        assert not can_be_decisive(method)

    @pytest.mark.parametrize(
        "method",
        [Method.CLAIM_REVIEW, Method.EXACT_HASH, Method.OFFICIAL_SOURCE, Method.MATCHED_PAGE_DATE],
    )
    def test_anchored_methods_can_decide(self, method: Method) -> None:
        assert can_be_decisive(method)

    def test_a_weak_match_from_a_decisive_method_is_still_only_a_candidate(self) -> None:
        item = evidence(method=Method.CLAIM_REVIEW, basis=weak_basis())

        assert can_be_decisive(item.method)
        assert not item.is_decisive_capable


class TestAdvisoryIsNotEvidence:
    """Invariant 1 — no domain supertype exists that could accept both."""

    def test_neither_type_is_a_subclass_of_the_other(self) -> None:
        assert not issubclass(Advisory, Evidence)
        assert not issubclass(Evidence, Advisory)

    def test_they_share_no_domain_base(self) -> None:
        """Pydantic's BaseModel is a framework base, not a domain supertype.

        A parameter typed `BaseModel` would accept every model in the codebase and is
        not a realistic leak path. A shared *domain* base would be, and there is none.
        """
        from pydantic import BaseModel

        shared = set(Evidence.__mro__) & set(Advisory.__mro__)

        assert shared == {BaseModel, object}

    def test_advisory_has_no_citation_to_offer(self) -> None:
        """It cannot masquerade as evidence even by duck typing."""
        signal = Advisory(id="a", provider="p", signal="NO_SIGNAL", note="n")

        for attribute in ("citation_url", "snapshot_id", "source_excerpt", "match_basis"):
            assert not hasattr(signal, attribute)


class TestAnchors:
    def test_anchor_that_locates_nothing_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must locate the claim"):
            ClaimAnchor(input_kind="url", content_hash="sha256:x")

    def test_reversed_character_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="precedes"):
            SourceAnchor(char_start=100, char_end=20)


class TestStatuses:
    def test_the_three_decisive_statuses_are_marked(self) -> None:
        assert ClaimStatus.SUPPORTED.is_decisive
        assert ClaimStatus.CONTRADICTED.is_decisive
        assert ClaimStatus.MISLEADING_CONTEXT.is_decisive

    def test_unverified_is_not_decisive(self) -> None:
        """Abstention is the one status that needs no citation."""
        assert not ClaimStatus.UNVERIFIED.is_decisive
