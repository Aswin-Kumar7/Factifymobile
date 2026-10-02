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
    CoverageExpectation,
    Credibility,
    Direction,
    EvidenceKind,
    Importance,
    Method,
    Severity,
    SourceRisk,
    Tier,
    Verdict,
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

    def test_contradicted_high_severity_detail_is_a_correction_not_false(self) -> None:
        """One wrong detail does not make the piece false: a BOOM fact-check of a
        deepfake read FALSE because two side details drew contradictions. The
        headline, main thesis and CRITICAL claims still decide FALSE (above)."""
        headline = claim(claim_id="cl_h", independent_origin_count=3, document_count=4)
        c = claim(claim_id="cl_d", importance=Importance.SUPPORTING_DETAIL, severity=Severity.HIGH)

        case = roll_up(
            [
                (headline, decide(headline, [_supporting_source()])),  # type: ignore[list-item]
                (c, decide(c, [_contradicting_factcheck()])),  # type: ignore[list-item]
            ]
        )

        assert case.action is Action.SHARE_WITH_CORRECTION
        assert case.rule_id == "rollup.minor_correction"
        assert case.verdict is Verdict.PARTLY_TRUE

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

    def test_a_wrong_detail_with_nothing_confirmed_is_misleading_not_partly_true(self) -> None:
        """Partly true says some of it is true. With nothing confirmed, a wrong detail
        makes the piece misleading, not partly true."""
        c = claim(importance=Importance.BACKGROUND, severity=Severity.LOW)
        decision = decide(c, [_contradicting_factcheck()])  # type: ignore[list-item]

        case = roll_up([(c, decision)])

        assert case.action is Action.SHARE_WITH_CONTEXT
        assert case.rule_id == "rollup.wrong_detail"
        assert case.verdict is Verdict.MISLEADING


class TestPartlyTrue:
    """Some of it right, some of it wrong: said as that (contract 1.4, 2026-09-28)."""

    def test_a_confirmed_claim_beside_a_contradicted_one_is_partly_true(self) -> None:
        headline = claim(claim_id="cl_1", independent_origin_count=3, document_count=4)
        thesis = claim(claim_id="cl_2", importance=Importance.MAIN_THESIS)

        case = roll_up(
            [
                (headline, decide(headline, [_supporting_source()])),  # type: ignore[list-item]
                (thesis, decide(thesis, [_contradicting_factcheck()])),  # type: ignore[list-item]
            ]
        )

        assert case.rule_id == "rollup.mixed"
        assert case.action is Action.SHARE_WITH_CORRECTION
        assert case.verdict is Verdict.PARTLY_TRUE

    def test_a_true_aside_under_a_false_headline_leaves_it_false(self) -> None:
        headline = claim(claim_id="cl_1")
        aside = claim(
            claim_id="cl_2",
            importance=Importance.BACKGROUND,
            independent_origin_count=3,
            document_count=4,
        )

        case = roll_up(
            [
                (headline, decide(headline, [_contradicting_factcheck()])),  # type: ignore[list-item]
                (aside, decide(aside, [_supporting_source()])),  # type: ignore[list-item]
            ]
        )

        assert case.action is Action.DO_NOT_SHARE
        assert case.verdict is Verdict.FALSE

    def test_a_real_thing_inflated_is_partly_true(self) -> None:
        """Govt pays every woman Rs 5,000 a month, where sources report one state's
        one-time payment: partly true, not misleading media."""
        from tests.unit.test_scope import CLAIM, _narrower

        c = claim(text=CLAIM)
        found = [_narrower("thenewsminute.com"), _narrower("indiatoday.in")]
        decision = decide(c, found)  # type: ignore[arg-type]

        case = roll_up([(c, decision)])

        assert decision.status is ClaimStatus.MISLEADING_CONTEXT
        assert case.rule_id == "rollup.partly_true"
        assert case.verdict is Verdict.PARTLY_TRUE

    def test_media_out_of_context_is_still_misleading(self) -> None:
        c = claim(importance=Importance.HEADLINE, severity=Severity.HIGH)
        item = evidence(
            kind=EvidenceKind.MEDIA_MATCH,
            direction=Direction.CONTRADICTS,
            tier=Tier.B,
            method=Method.NEAR_DUPLICATE_VERIFIED,
        )

        case = roll_up([(c, decide(c, [item]))])  # type: ignore[list-item]

        assert case.verdict is Verdict.MISLEADING

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


class TestAPredictionIsNotCheckable:
    """No evidence settles a statement about something that has not happened.

    This was a live false positive: "India will win the 2027 Cricket World Cup" came
    back SAFE_TO_SHARE, carried by two outlets writing about India's prospects. The
    extractor had typed it PREDICTION correctly and nothing downstream used that. With
    search snippets it had never gathered enough support to reach a verdict, so richer
    retrieval is what exposed the gap rather than caused it.
    """

    def test_a_prediction_is_never_supported_however_much_coverage_it_has(self) -> None:
        decision = decide(
            claim(claim_type=ClaimType.PREDICTION),
            [
                evidence(
                    direction=Direction.SUPPORTS, tier=Tier.B, kind=EvidenceKind.CORROBORATION
                ),
                evidence(
                    direction=Direction.SUPPORTS, tier=Tier.B, kind=EvidenceKind.CORROBORATION
                ),
            ],
        )

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.prediction_not_checked"

    def test_a_forecast_whose_outcome_is_reported_otherwise_is_false(self) -> None:
        """ "DMK wins the 2026 Tamil Nadu elections", read as a prediction, under four
        outlets reporting that TVK won: the event it is, and false (2026-10-01)."""
        against = [
            evidence(
                direction=Direction.CONTRADICTS,
                tier=Tier.D,
                kind=EvidenceKind.CORROBORATION,
                method=Method.PASSAGE_ENTAILMENT,
                citation_url=f"https://{site}/tn-results",
            )
            for site in ("indiatoday.in", "indianexpress.com")
        ]
        decision = decide(claim(claim_type=ClaimType.PREDICTION), against)

        assert decision.status is ClaimStatus.CONTRADICTED
        assert decision.rule_id == "rule.independent_contradiction"

    def test_the_reason_says_why_rather_than_calling_it_an_opinion(self) -> None:
        """A forecast is not an opinion, and telling a user it was read as one is wrong."""
        decision = decide(claim(claim_type=ClaimType.PREDICTION), [])

        assert "has not happened yet" in decision.reason
        assert "opinion" not in decision.reason.lower()

    def test_an_opinion_still_reports_as_an_opinion(self) -> None:
        decision = decide(claim(claim_type=ClaimType.OPINION), [])

        assert decision.rule_id == "rule.opinion_not_checked"

    def test_an_ordinary_event_claim_is_unaffected(self) -> None:
        decision = decide(
            claim(claim_type=ClaimType.EVENT),
            [evidence(direction=Direction.CONTRADICTS, tier=Tier.C, kind=EvidenceKind.FACT_CHECK)],
        )

        assert decision.status is ClaimStatus.CONTRADICTED


class TestSilenceIsReportedWhenItMeansSomething:
    """`coverage_expectation` was captured at extraction and read by nothing.

    Its own docstring says why it exists: corroboration cannot interpret silence
    without it, because a national claim absent from every source is meaningful and a
    local one is not. For an invented disaster, "no source reports this" is the honest
    thing to say — and saying nothing left the user to infer it from a citation about
    a different disaster.
    """

    def test_a_high_coverage_claim_nothing_reports_says_so(self) -> None:
        from app.verdict.engine import _silence_clause

        assert "no source found reports it" in _silence_clause(
            claim(coverage_expectation=CoverageExpectation.HIGH), []
        )

    def test_a_source_that_disagrees_has_reported_the_event(self) -> None:
        """Three outlets contradicted a flydubai post's passenger count by reporting
        the flight with another figure, and the reason still said no source reports
        it (2026-10-02)."""
        for direction in (Direction.CONTRADICTS, Direction.CONTEXTUALIZES):
            decision = decide(
                claim(coverage_expectation=CoverageExpectation.HIGH),
                [evidence(direction=direction, tier=Tier.D, kind=EvidenceKind.CORROBORATION)],
            )

            assert "no source found reports it" not in decision.reason, direction

        contradicted = decide(
            claim(coverage_expectation=CoverageExpectation.HIGH),
            [
                evidence(
                    direction=Direction.CONTRADICTS,
                    tier=Tier.D,
                    kind=EvidenceKind.CORROBORATION,
                    citation_url=f"https://{host}/flydubai",
                )
                for host in ("timesofindia.com", "indiatoday.in", "ynetnews.com")
            ],
        )
        assert contradicted.status is ClaimStatus.CONTRADICTED
        assert "no source found reports it" not in contradicted.reason

    def test_an_opinion_is_never_called_unreported(self) -> None:
        from app.verdict.engine import _silence_clause

        opinion = claim(coverage_expectation=CoverageExpectation.HIGH, claim_type=ClaimType.OPINION)

        assert _silence_clause(opinion, []) == ""

    def test_a_local_claim_stays_silent_about_silence(self) -> None:
        """A district event missing from national sources means nothing at all."""
        decision = decide(
            claim(coverage_expectation=CoverageExpectation.LOCAL),
            [
                evidence(
                    direction=Direction.CONTRADICTS, tier=Tier.D, kind=EvidenceKind.CORROBORATION
                )
            ],
        )

        assert "no source found reports it" not in decision.reason

    def test_a_supported_claim_is_not_told_it_is_unreported(self) -> None:
        decision = decide(
            claim(coverage_expectation=CoverageExpectation.HIGH),
            [evidence(direction=Direction.SUPPORTS, tier=Tier.A, kind=EvidenceKind.PROVENANCE)],
        )

        assert "no source found reports it" not in decision.reason

    def test_it_changes_the_explanation_and_never_the_status(self) -> None:
        """A no-evidence assertion is a fact-checker's move, and doing it soundly needs
        provenance we have not built. So: a sentence, not a verdict."""
        loud = decide(claim(coverage_expectation=CoverageExpectation.HIGH), [])
        quiet = decide(claim(coverage_expectation=CoverageExpectation.LOCAL), [])

        assert loud.status is quiet.status
        assert loud.rule_id == quiet.rule_id


class TestAnOfficialDomainIsNotAnAuthorityOnEverything:
    """One citation on a government domain is not corroboration for any claim.

    A rule here once said it was, and it cleared a scam. "Applications are open for
    the National Sports Scholarship 2026-27" — a flyer PIB had already called fake —
    came back SAFE_TO_SHARE on one quote from scholarships.gov.in reading "students
    may apply for one merit-based scholarship scheme and one or more welfare-based
    scholarship schemes". The real portal, saying something true and general, matched
    to an invented scheme.

    A scam impersonates a real programme. That is what makes it a scam, and it is
    exactly when a generic page from the impersonated body reads as support.
    """

    def test_one_government_citation_is_not_enough(self) -> None:
        decision = decide(
            claim(independent_origin_count=1, document_count=1),
            [
                evidence(
                    direction=Direction.SUPPORTS,
                    tier=Tier.D,
                    citation_url="https://scholarships.gov.in",
                )
            ],
        )

        assert decision.status is ClaimStatus.UNVERIFIED
        assert decision.rule_id == "rule.insufficient_origins"

    def test_two_origins_still_support(self) -> None:
        """The bar did not move for anyone else."""
        decision = decide(
            claim(independent_origin_count=2, document_count=2),
            [
                evidence(direction=Direction.SUPPORTS, tier=Tier.D, citation_url="https://a.com/1"),
                evidence(direction=Direction.SUPPORTS, tier=Tier.D, citation_url="https://b.com/2"),
            ],
        )

        assert decision.status is ClaimStatus.SUPPORTED


class TestAMinorDetailDoesNotSinkTheCase:
    """The clearance rule asked for every claim to be supported. Articles fail that.

    An Economic Times commentary produced seven claims. Three were searched and
    supported, with thirteen citations between them; the other four sat below the
    cap that decides how many claims are worth an open-web search, so nothing ever
    looked at them. The case came back "not enough evidence to decide" on the
    strength of four claims nobody had checked — and the longer and better sourced
    the article, the more certain that outcome became.
    """

    @staticmethod
    def _supported():  # type: ignore[no-untyped-def]
        return decide(
            claim(independent_origin_count=2, document_count=2),
            [
                evidence(direction=Direction.SUPPORTS, tier=Tier.D, citation_url="https://a.com/1"),
                evidence(direction=Direction.SUPPORTS, tier=Tier.D, citation_url="https://b.com/2"),
            ],
        )

    @staticmethod
    def _unverified():  # type: ignore[no-untyped-def]
        return decide(claim(), [])

    def test_a_background_claim_nobody_checked_does_not_block(self) -> None:
        minor = claim(claim_id="cl_2", importance=Importance.BACKGROUND, severity=Severity.LOW)

        outcome = roll_up(
            [
                (claim(independent_origin_count=2, document_count=2), self._supported()),
                (minor, self._unverified()),
            ]
        )

        assert outcome.action is Action.SAFE_TO_SHARE
        assert "minor detail" in outcome.reason

    def test_an_unconfirmed_high_severity_detail_does_not_outvote_the_article(self) -> None:
        """A Hindu analysis: three claims confirmed by NDTV, The Hindu and TOI, one
        background sentence ("a dharna a month earlier") with no coverage, rated HIGH
        by the extractor as most political claims are. It came back Unconfirmed."""
        aside = claim(
            claim_id="cl_2", importance=Importance.SUPPORTING_DETAIL, severity=Severity.HIGH
        )

        outcome = roll_up(
            [
                (claim(independent_origin_count=2, document_count=2), self._supported()),
                (aside, self._unverified()),
            ]
        )

        assert outcome.action is Action.SAFE_TO_SHARE
        assert "could not be checked" in outcome.reason

    def test_an_unverified_thesis_still_abstains(self) -> None:
        """The bar is not lowered for the claims that carry the document."""
        outcome = roll_up(
            [
                (claim(independent_origin_count=2, document_count=2), self._supported()),
                (claim(claim_id="cl_2", importance=Importance.MAIN_THESIS), self._unverified()),
            ]
        )

        assert outcome.action is Action.SEND_TO_REVIEW

    def test_an_unconfirmed_critical_detail_does_not_outvote_the_headline(self) -> None:
        """NDTV on death sentences for the 2013 Jhiram Ghati attack: the headline was
        carried by three outlets, four background details were rated CRITICAL by the
        extractor, and the case came back Unconfirmed because they were not separately
        reported (2026-10-02). Severity says what a claim is about, not what the piece
        rests on."""
        for importance in (Importance.SUPPORTING_DETAIL, Importance.BACKGROUND):
            severe = claim(claim_id="cl_2", importance=importance, severity=Severity.CRITICAL)

            outcome = roll_up(
                [
                    (claim(independent_origin_count=2, document_count=2), self._supported()),
                    (severe, self._unverified()),
                ]
            )

            assert outcome.action is Action.SAFE_TO_SHARE, importance
            assert "could not be checked" in outcome.reason

    def test_a_contradicted_critical_detail_still_sinks_the_case(self) -> None:
        severe = claim(
            claim_id="cl_2", importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL
        )
        contradicted = decide(
            severe,
            [
                evidence(
                    direction=Direction.CONTRADICTS,
                    tier=Tier.C,
                    kind=EvidenceKind.FACT_CHECK,
                    citation_url="https://www.boomlive.in/fact-check/x",
                )
            ],
        )

        headline = claim(independent_origin_count=2, document_count=2)
        supported = decide(
            headline,
            [
                evidence(direction=Direction.SUPPORTS, tier=Tier.D, citation_url="https://a.com/1"),
                evidence(direction=Direction.SUPPORTS, tier=Tier.D, citation_url="https://b.com/2"),
            ],
        )

        outcome = roll_up([(headline, supported), (severe, contradicted)])

        assert outcome.action is not Action.SAFE_TO_SHARE

    def test_silence_about_everything_is_not_a_clearance(self) -> None:
        """At least one claim has to be positively supported."""
        outcome = roll_up(
            [
                (
                    claim(importance=Importance.BACKGROUND, severity=Severity.LOW),
                    self._unverified(),
                ),
                (
                    claim(
                        claim_id="cl_2",
                        importance=Importance.BACKGROUND,
                        severity=Severity.LOW,
                    ),
                    self._unverified(),
                ),
            ]
        )

        assert outcome.action is not Action.SAFE_TO_SHARE


class TestOneAuthoritativeRefutationIsEnough:
    """PIB-debunked scams abstained because rule 3b wanted two publishers to agree.

    "Banks were told to stock ATMs ahead of UPI fees", the free-laptop scheme and the
    National Sports Scholarship were all debunked by the government's own fact-check
    unit, and all came back "not enough evidence to decide".
    """

    @staticmethod
    def _against(url: str, credibility: Credibility | None):  # type: ignore[no-untyped-def]
        return evidence(
            kind=EvidenceKind.CORROBORATION,
            direction=Direction.CONTRADICTS,
            tier=Tier.D,
            citation_url=url,
        ).model_copy(update={"credibility": credibility})

    def test_one_highly_credible_refutation_decides(self) -> None:
        decision = decide(
            claim(), [self._against("https://factcheck.pib.gov.in/1", Credibility.HIGH)]
        )

        assert decision.status is ClaimStatus.CONTRADICTED
        assert decision.rule_id == "rule.authoritative_contradiction"

    def test_one_ordinary_newspaper_does_not(self) -> None:
        decision = decide(claim(), [self._against("https://thehindu.com/1", Credibility.MEDIUM)])

        assert decision.status is ClaimStatus.UNVERIFIED

    def test_a_source_nobody_weighed_does_not(self) -> None:
        """Credibility is only set after the relevance check. Unchecked is not enough."""
        decision = decide(claim(), [self._against("https://apnews.com/1", None)])

        assert decision.status is ClaimStatus.UNVERIFIED

    def test_support_still_needs_two_independent_origins(self) -> None:
        """The asymmetry is the point: clearing a false claim is the costlier error."""
        support = evidence(
            kind=EvidenceKind.CORROBORATION,
            direction=Direction.SUPPORTS,
            tier=Tier.D,
            citation_url="https://apnews.com/1",
        ).model_copy(update={"credibility": Credibility.HIGH})

        decision = decide(claim(independent_origin_count=1, document_count=1), [support])

        assert decision.status is ClaimStatus.UNVERIFIED


class TestConfidenceIsArithmeticOnTheSources:
    @staticmethod
    def _side(direction: Direction, *urls: str, kind: EvidenceKind = EvidenceKind.CORROBORATION):  # type: ignore[no-untyped-def]
        return [
            evidence(kind=kind, direction=direction, tier=Tier.D, citation_url=u).model_copy(
                update={"credibility": Credibility.HIGH}
            )
            for u in urls
        ]

    def test_one_credible_refutation_is_fairly_sure(self) -> None:
        decision = decide(claim(), self._side(Direction.CONTRADICTS, "https://apnews.com/1"))

        assert decision.confidence == 78

    def test_more_independent_sources_raise_it(self) -> None:
        decision = decide(
            claim(),
            self._side(Direction.CONTRADICTS, "https://apnews.com/1", "https://bbc.com/2"),
        )

        assert decision.confidence == 89

    def test_a_published_fact_check_is_at_least_88(self) -> None:
        decision = decide(
            claim(),
            self._side(Direction.CONTRADICTS, "https://altnews.in/1", kind=EvidenceKind.FACT_CHECK),
        )

        assert decision.confidence is not None and decision.confidence >= 88

    def test_no_verdict_means_no_confidence(self) -> None:
        assert decide(claim(), []).confidence is None

    def test_it_never_reaches_certainty(self) -> None:
        urls = [f"https://outlet{i}.com/x" for i in range(12)]
        decision = decide(claim(), self._side(Direction.CONTRADICTS, *urls))

        assert decision.confidence == 97


class TestTheVerdictAPersonReads:
    def test_a_refuted_central_claim_reads_false_with_its_confidence(self) -> None:
        refuted = decide(
            claim(),
            [
                evidence(
                    direction=Direction.CONTRADICTS,
                    tier=Tier.D,
                    citation_url="https://apnews.com/1",
                ).model_copy(update={"credibility": Credibility.HIGH})
            ],
        )

        case = roll_up([(claim(), refuted)])

        assert case.verdict is Verdict.FALSE
        assert case.confidence == refuted.confidence

    def test_nothing_decided_reads_unconfirmed_and_is_not_sent_to_anyone(self) -> None:
        case = roll_up([(claim(), decide(claim(), []))])

        assert case.verdict is Verdict.UNCONFIRMED
        assert case.confidence is None
        assert "review" not in case.reason.lower()
