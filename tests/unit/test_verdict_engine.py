"""M06 — every rule branch, both boundary cases, and every rollup row.

This is the module the plan says gets the most tests in the repository, because it is
the only place a verdict is decided and everything downstream inherits its answers.
"""

from __future__ import annotations

import pytest

from app.domain import (
    Action,
    ClaimStatus,
    ClaimType,
    Direction,
    EvidenceKind,
    Importance,
    Method,
    Severity,
    SourceRisk,
    Tier,
)
from app.verdict import AdvisoryLeakError, decide, roll_up
from app.verdict.engine import RULE_VERSION
from tests.unit.factories import advisory, claim, evidence, weak_basis

pytestmark = pytest.mark.unit


def _contradicting_factcheck() -> object:
    return evidence(kind=EvidenceKind.FACT_CHECK, direction=Direction.CONTRADICTS, tier=Tier.C)


def _supporting_source() -> object:
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.SUPPORTS,
        tier=Tier.D,
        method=Method.ORIGIN_CLUSTER_COUNT,
    )


class TestRuleBranches:
    """The eight ordered rules of §9."""

    def test_rule_1_factcheck_contradiction(self) -> None:
        decision = decide(claim(), [_contradicting_factcheck()])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.CONTRADICTED
        assert decision.rule_id == "rule.factcheck_contradiction"
        assert decision.supporting_evidence_ids

    def test_rule_2_dated_media_conflict_is_misleading_context(self) -> None:
        """The proposition survives; the framing does not."""
        item = evidence(
            kind=EvidenceKind.DATED_SOURCE,
            direction=Direction.CONTRADICTS,
            tier=Tier.B,
            method=Method.MATCHED_PAGE_DATE,
        )

        decision = decide(claim(), [item])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.MISLEADING_CONTEXT
        assert decision.rule_id == "rule.dated_media_conflict"

    def test_rule_3_attribution_contradiction(self) -> None:
        item = evidence(
            kind=EvidenceKind.ATTRIBUTION,
            direction=Direction.CONTRADICTS,
            tier=Tier.D,
            method=Method.OFFICIAL_SOURCE,
        )

        decision = decide(claim(), [item])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.CONTRADICTED
        assert decision.rule_id == "rule.attribution_contradiction"

    def test_rule_4_support_requires_independent_origins(self) -> None:
        decision = decide(
            claim(independent_origin_count=3, document_count=19),
            [_supporting_source()],  # type: ignore[list-item]
        )

        assert decision.status is ClaimStatus.SUPPORTED
        assert "3 independent origins across 19 documents" in decision.reason

    def test_rule_5_developing_window_abstains(self) -> None:
        decision = decide(
            claim(within_developing_window=True, independent_origin_count=5),
            [_supporting_source()],  # type: ignore[list-item]
        )

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.developing_window"

    def test_rule_6_source_risk_alone_abstains(self) -> None:
        item = evidence(
            kind=EvidenceKind.SOURCE_RISK,
            direction=Direction.RISK_SIGNAL,
            tier=Tier.D,
            method=Method.DOMAIN_AGE,
        )

        decision = decide(claim(), [item])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.source_risk_only"

    def test_rule_7_no_evidence_abstains(self) -> None:
        decision = decide(claim(), [])

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.no_evidence"

    def test_opinion_is_never_fact_checked(self) -> None:
        decision = decide(claim(claim_type=ClaimType.OPINION), [_contradicting_factcheck()])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.opinion_not_checked"


class TestHardDesignRules:
    def test_no_citation_means_no_decisive_status(self) -> None:
        """Hard rule 1, and the reason a Decision cannot be built without evidence."""
        for status in (ClaimStatus.SUPPORTED, ClaimStatus.CONTRADICTED):
            decision = decide(claim(), [])
            assert decision.status is not status

    def test_silence_alone_never_contradicts(self) -> None:
        """Hard rule 5. Absence of coverage is not a finding against the claim."""
        decision = decide(claim(coverage_expectation="HIGH", document_count=0), [])

        assert decision.status is not ClaimStatus.CONTRADICTED

    def test_conflicting_evidence_of_comparable_weight_is_surfaced_not_averaged(self) -> None:
        """Hard rule 7. A real disagreement is reported as one, not split down the middle.

        "Comparable" is the qualifier: two findings of the same evidence class pointing
        opposite ways is the case a human must look at.
        """
        decision = decide(
            claim(independent_origin_count=5),
            [  # type: ignore[list-item]
                evidence(
                    kind=EvidenceKind.CORROBORATION,
                    direction=Direction.CONTRADICTS,
                    tier=Tier.D,
                    method=Method.ORIGIN_CLUSTER_COUNT,
                ),
                _supporting_source(),
            ],
        )

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.conflicting_evidence"
        assert decision.conflicting

    def test_a_stronger_class_of_evidence_settles_a_disagreement(self) -> None:
        """A published adjudication outranks a page that merely reads as agreeing.

        Without this, one misread source — a model quoting the myth a page states in
        order to debunk it — could veto a fact-check and send everything to review.
        """
        decision = decide(
            claim(independent_origin_count=5),
            [_contradicting_factcheck(), _supporting_source()],  # type: ignore[list-item]
        )

        assert decision.status is ClaimStatus.CONTRADICTED
        assert decision.rule_id == "rule.factcheck_contradiction"
        # the dissent is not hidden: it is named in the reason and still cited
        assert "disagree" in decision.reason

    def test_only_the_protective_direction_is_resolved(self) -> None:
        """Weaker evidence contradicting stronger support stays a question for a human:
        the error that matters is telling someone a false claim is safe to share."""
        decision = decide(
            claim(independent_origin_count=5),
            [  # type: ignore[list-item]
                evidence(kind=EvidenceKind.FACT_CHECK, direction=Direction.SUPPORTS, tier=Tier.C),
                evidence(
                    kind=EvidenceKind.CORROBORATION,
                    direction=Direction.CONTRADICTS,
                    tier=Tier.D,
                    method=Method.PASSAGE_ENTAILMENT,
                ),
            ],
        )

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.conflicting_evidence"

    def test_weak_evidence_cannot_decide(self) -> None:
        item = evidence(basis=weak_basis())

        decision = decide(claim(), [item])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.UNVERIFIED

    def test_support_without_enough_origins_abstains(self) -> None:
        """One outlet is a source, not a corroboration."""
        decision = decide(claim(independent_origin_count=1), [_supporting_source()])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.insufficient_origins"


class TestAdvisoryCannotReachTheEngine:
    def test_passing_an_advisory_raises(self) -> None:
        with pytest.raises(AdvisoryLeakError, match="accepts Evidence only"):
            decide(claim(), [advisory()])  # type: ignore[list-item]

    def test_a_detector_score_cannot_be_smuggled_in_a_mixed_list(self) -> None:
        with pytest.raises(AdvisoryLeakError):
            decide(claim(), [_contradicting_factcheck(), advisory()])  # type: ignore[list-item]


class TestRuleVersioning:
    def test_every_decision_carries_the_rule_version(self) -> None:
        """A cached verdict from older rules must be identifiable."""
        assert decide(claim(), []).rule_version == RULE_VERSION

    def test_every_decision_names_the_rule_that_fired(self) -> None:
        assert decide(claim(), []).rule_id.startswith("rule.")


class TestCaseRollup:
    """Every row of the precedence table, top to bottom."""

    def test_contradicted_main_thesis_blocks_sharing(self) -> None:
        c = claim(importance=Importance.MAIN_THESIS, severity=Severity.MEDIUM)
        decision = decide(c, [_contradicting_factcheck()])  # type: ignore[list-item]

        case = roll_up([(c, decision)])

        assert case.action is Action.DO_NOT_SHARE
        assert case.rule_id == "rollup.contradicted_material"

    def test_contradicted_critical_detail_blocks_sharing(self) -> None:
        c = claim(importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL)
        decision = decide(c, [_contradicting_factcheck()])  # type: ignore[list-item]

        assert roll_up([(c, decision)]).action is Action.DO_NOT_SHARE

    def test_contradicted_high_severity_detail_blocks_sharing(self) -> None:
        c = claim(importance=Importance.SUPPORTING_DETAIL, severity=Severity.HIGH)
        decision = decide(c, [_contradicting_factcheck()])  # type: ignore[list-item]

        case = roll_up([(c, decision)])

        assert case.action is Action.DO_NOT_SHARE
        assert case.rule_id == "rollup.contradicted_high_severity"

    def test_misleading_material_claim_shares_with_context(self) -> None:
        c = claim(importance=Importance.HEADLINE, severity=Severity.HIGH)
        item = evidence(
            kind=EvidenceKind.MEDIA_MATCH,
            direction=Direction.CONTRADICTS,
            tier=Tier.B,
            method=Method.NEAR_DUPLICATE_VERIFIED,
        )
        decision = decide(c, [item])  # type: ignore[list-item]

        case = roll_up([(c, decision)])

        assert case.action is Action.SHARE_WITH_CONTEXT
        assert case.rule_id == "rollup.misleading_material"

    def test_minor_contradiction_shares_with_correction(self) -> None:
        c = claim(importance=Importance.BACKGROUND, severity=Severity.LOW)
        decision = decide(c, [_contradicting_factcheck()])  # type: ignore[list-item]

        case = roll_up([(c, decision)])

        assert case.action is Action.SHARE_WITH_CORRECTION
        assert case.rule_id == "rollup.minor_correction"

    def test_developing_claim_waits(self) -> None:
        c = claim(within_developing_window=True)
        decision = decide(c, [])

        assert roll_up([(c, decision)]).action is Action.WAIT_AND_RECHECK

    def test_unverified_on_a_risky_publisher_routes_to_review(self) -> None:
        c = claim()
        decision = decide(c, [])

        case = roll_up([(c, decision)], source_risk=SourceRisk.HIGH)

        assert case.action is Action.SEND_TO_REVIEW

    def test_all_supported_is_safe_to_share(self) -> None:
        c = claim(independent_origin_count=3, document_count=4)
        decision = decide(c, [_supporting_source()])  # type: ignore[list-item]

        assert roll_up([(c, decision)]).action is Action.SAFE_TO_SHARE

    def test_novel_claim_abstains_rather_than_accusing(self) -> None:
        """The demo beat: absence of evidence is never an accusation."""
        c = claim()
        decision = decide(c, [])

        case = roll_up([(c, decision)])

        assert case.action is Action.SEND_TO_REVIEW
        assert case.action is not Action.DO_NOT_SHARE

    def test_source_risk_alone_can_never_reach_do_not_share(self) -> None:
        """Hard rule 8. A negative assertion about a publisher is not a finding."""
        item = evidence(
            kind=EvidenceKind.SOURCE_RISK,
            direction=Direction.RISK_SIGNAL,
            tier=Tier.D,
            method=Method.DOMAIN_AGE,
        )
        c = claim(importance=Importance.HEADLINE, severity=Severity.CRITICAL)
        decision = decide(c, [item])  # type: ignore[list-item]

        case = roll_up([(c, decision)], source_risk=SourceRisk.HIGH)

        assert case.action is not Action.DO_NOT_SHARE
        assert case.action is Action.SEND_TO_REVIEW

    def test_supported_claims_never_raise_the_action(self) -> None:
        supported = claim(claim_id="cl_1", independent_origin_count=3)
        minor = claim(claim_id="cl_2", importance=Importance.BACKGROUND, severity=Severity.LOW)

        case = roll_up(
            [
                (supported, decide(supported, [_supporting_source()])),  # type: ignore[list-item]
                (minor, decide(minor, [_contradicting_factcheck()])),  # type: ignore[list-item]
            ]
        )

        assert case.action is Action.SHARE_WITH_CORRECTION

    def test_no_claims_routes_to_review(self) -> None:
        assert roll_up([]).action is Action.SEND_TO_REVIEW


class TestWorkedExample:
    """The §5A volcano article, reproduced exactly including the case action."""

    def test_volcano_article_resolves_as_documented(self) -> None:
        claim_b = claim(
            claim_id="cl_b",
            text="It occurred in China.",
            importance=Importance.MAIN_THESIS,
            severity=Severity.HIGH,
        )
        claim_c = claim(
            claim_id="cl_c",
            text="It occurred today.",
            importance=Importance.SUPPORTING_DETAIL,
            severity=Severity.MEDIUM,
        )
        claim_d = claim(
            claim_id="cl_d",
            text="Officials confirmed it.",
            importance=Importance.SUPPORTING_DETAIL,
            severity=Severity.LOW,
        )

        official_record = evidence(
            claim_id="cl_b",
            kind=EvidenceKind.ATTRIBUTION,
            direction=Direction.CONTRADICTS,
            tier=Tier.D,
            method=Method.OFFICIAL_SOURCE,
        )
        frame_match = evidence(
            claim_id="cl_c",
            kind=EvidenceKind.MEDIA_MATCH,
            direction=Direction.CONTRADICTS,
            tier=Tier.B,
            method=Method.NEAR_DUPLICATE_VERIFIED,
        )

        decision_b = decide(claim_b, [official_record])  # type: ignore[list-item]
        decision_c = decide(claim_c, [frame_match])  # type: ignore[list-item]
        decision_d = decide(claim_d, [])

        assert decision_b.status is ClaimStatus.CONTRADICTED
        assert decision_c.status is ClaimStatus.MISLEADING_CONTEXT
        assert decision_d.status is ClaimStatus.UNVERIFIED

        case = roll_up([(claim_b, decision_b), (claim_c, decision_c), (claim_d, decision_d)])

        assert case.action is Action.DO_NOT_SHARE
        assert case.rule_id == "rollup.contradicted_material"


class TestContradictionByIndependentPublishers:
    """Rule 3b: credible reporting may contradict, on the same terms support may carry.

    Before this rule, only a published fact-check, an attribution check or a dated-media
    conflict could contradict anything — so three outlets refuting a claim still left it
    UNVERIFIED, which a reader sees as "nothing found".
    """

    @staticmethod
    def _web(url: str, direction: Direction = Direction.CONTRADICTS) -> object:
        return evidence(
            kind=EvidenceKind.CORROBORATION,
            direction=direction,
            tier=Tier.D,
            method=Method.PASSAGE_ENTAILMENT,
            citation_url=url,
        )

    def test_two_independent_publishers_contradict(self) -> None:
        decision = decide(
            claim(),
            [  # type: ignore[list-item]
                self._web("https://www.bbc.com/news/article-1"),
                self._web("https://timesofindia.indiatimes.com/india/x/articleshow/2.cms"),
            ],
        )

        assert decision.status is ClaimStatus.CONTRADICTED
        assert decision.rule_id == "rule.independent_contradiction"
        assert decision.supporting_evidence_ids  # a decisive status always cites

    def test_one_publisher_is_not_enough(self) -> None:
        decision = decide(claim(), [self._web("https://www.bbc.com/news/article-1")])  # type: ignore[list-item]

        assert decision.status is ClaimStatus.UNVERIFIED

    def test_one_publisher_speaking_twice_is_still_one(self) -> None:
        """Subdomains of one masthead are one origin; counting them twice would
        manufacture the independence the rule is asking about."""
        decision = decide(
            claim(),
            [  # type: ignore[list-item]
                self._web("https://www.mayoclinic.org/diseases/x"),
                self._web("https://newsnetwork.mayoclinic.org/discussion/y"),
            ],
        )

        assert decision.status is ClaimStatus.UNVERIFIED

    def test_a_country_suffix_does_not_collapse_publishers(self) -> None:
        decision = decide(
            claim(),
            [  # type: ignore[list-item]
                self._web("https://www.bbc.co.uk/news/1"),
                self._web("https://www.theguardian.co.uk/news/2"),
            ],
        )

        assert decision.status is ClaimStatus.CONTRADICTED

    def test_support_gets_no_such_relaxation(self) -> None:
        """The asymmetry is deliberate: this path may withhold sharing, never bless it."""
        decision = decide(
            claim(independent_origin_count=0),
            [  # type: ignore[list-item]
                self._web("https://www.bbc.com/news/1", Direction.SUPPORTS),
                self._web("https://www.reuters.com/world/2", Direction.SUPPORTS),
            ],
        )

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.insufficient_origins"

    def test_a_disagreement_is_still_surfaced_not_resolved(self) -> None:
        decision = decide(
            claim(),
            [  # type: ignore[list-item]
                self._web("https://www.bbc.com/news/1"),
                self._web("https://www.reuters.com/world/2"),
                self._web("https://www.thehindu.com/news/3", Direction.SUPPORTS),
            ],
        )

        assert decision.rule_id == "rule.conflicting_evidence"
