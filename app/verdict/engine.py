"""The verdict engine (M06). Pure function. No I/O of any kind.

This module implements codexplan.md §9. It imports nothing that can reach a network,
a database, a model or a filesystem, and that is checked by a test rather than left
to discipline — if the core is not pure, nothing downstream is trustworthy.

Its signature accepts `Evidence` only. `Advisory` is a different type with no shared
base, so Tier E cannot reach this code by any path that type-checks, and a runtime
guard catches the untyped caller as well.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from app.domain.claim import Claim
from app.domain.enums import (
    Action,
    ClaimStatus,
    ClaimType,
    CoverageExpectation,
    Credibility,
    Direction,
    EvidenceKind,
    Importance,
    Severity,
    SourceRisk,
    Tier,
    Verdict,
)
from app.domain.evidence import Evidence
from app.domain.publishers import publishers_of

# Stamped on every verdict. A cached verdict produced under older rules is therefore
# identifiable, and the cache can refuse to serve it (M13).
RULE_VERSION = "2026.09.13"

# Default number of genuinely independent origins required before corroboration can
# support a claim. Tenant-configurable later; never below two, because one origin is
# a source rather than a corroboration.
DEFAULT_MIN_ORIGINS = 2


class AdvisoryLeakError(TypeError):
    """Something that is not `Evidence` was passed to the verdict engine.

    Raised loudly rather than filtered silently: a caller trying to hand a detector
    score to the engine is a defect in that caller, and quietly dropping it would
    hide the defect while appearing to work.
    """


@dataclass(frozen=True, slots=True)
class Decision:
    """A claim status, the rule that produced it, and what satisfied that rule."""

    status: ClaimStatus
    rule_id: str
    reason: str
    rule_version: str = RULE_VERSION
    supporting_evidence_ids: tuple[str, ...] = ()
    conflicting: bool = False
    # 50-97 for a decisive status, None otherwise. Computed from the cited sources by
    # `_confidence`, never supplied by a caller.
    confidence: int | None = None

    def __post_init__(self) -> None:
        if self.status.is_decisive and not self.supporting_evidence_ids:
            raise ValueError(
                f"decisive status {self.status} produced with no supporting evidence; "
                "this is the ledger-completeness invariant and must never happen"
            )


@dataclass(frozen=True, slots=True)
class CaseDecision:
    """The per-case action, rolled up from every claim decision."""

    action: Action
    rule_id: str
    reason: str
    rule_version: str = RULE_VERSION
    verdict: Verdict = Verdict.UNCONFIRMED
    confidence: int | None = None


def _reject_non_evidence(items: list[Evidence]) -> None:
    for item in items:
        if not isinstance(item, Evidence):
            raise AdvisoryLeakError(
                f"verdict engine received {type(item).__name__}; it accepts Evidence "
                "only. Tier E signals belong in the advisory list."
            )


def _decisive(
    evidence: list[Evidence], *, kind: EvidenceKind, direction: Direction
) -> list[Evidence]:
    """Items of a given kind and direction that are strong enough to conclude."""
    return [
        item
        for item in evidence
        if item.kind is kind and item.direction is direction and item.is_decisive_capable
    ]


# How much authority a tier carries about a claim, mirroring the weights the strength
# score uses. Consulted only to resolve a disagreement between classes of evidence:
# a published adjudication (C) outranks corroborating reporting (D).
_TIER_AUTHORITY = {Tier.A: 1.00, Tier.B: 0.90, Tier.C: 0.95, Tier.D: 0.70}


# Second-level domains that are themselves suffixes, so `bbc.co.uk` collapses to
# itself rather than to `co.uk`. Enough for counting publishers; this module stays
# pure and takes no dependency on a public-suffix list.
def _publishers(evidence: list[Evidence]) -> set[str]:
    """The distinct publishers behind a set of citations.

    Shared with the corroboration count, so the rules and the origin count cannot
    drift apart on what "a different publisher" means.
    """
    return publishers_of([item.citation_url for item in evidence])


def _silence_clause(claim: Claim, supporting: list[Evidence]) -> str:
    """What it means that nothing supports a claim this big.

    `coverage_expectation` has been captured at extraction, written to the ledger and
    read by nothing since. Its own docstring says why it exists: "corroboration cannot
    interpret silence without it — a national claim absent from the corpus is
    meaningful, a local one is not."

    This is the smallest honest use of it. For an event that would certainly be
    reported, the absence of any source reporting it *is* a finding, and a reader
    deserves to be told that rather than left to infer it. It is added to the
    explanation, never to the decision: professional fact-checkers refute roughly 7% of
    false claims this way, but doing so soundly requires knowing that the sources
    searched are ones that would have carried it, and that is the provenance work this
    system has not built yet.

    So: a sentence, not a verdict.
    """
    if supporting or claim.coverage_expectation is not CoverageExpectation.HIGH:
        return ""
    return " An event like this would be widely reported, and no source found reports it."


def decide(
    claim: Claim,
    evidence: list[Evidence],
    *,
    min_origins: int = DEFAULT_MIN_ORIGINS,
) -> Decision:
    """Resolve one claim against its evidence, with a confidence when it is decided."""
    decision = _decide_status(claim, evidence, min_origins=min_origins)
    return replace(decision, confidence=_confidence(decision, evidence))


# How much one publisher's word weighs, by credibility. A source nobody has weighed —
# evidence from before the relevance check, or from a caller that runs without one —
# counts as a middling source rather than as nothing, so older paths keep their meaning.
_WEIGHT = {
    Credibility.HIGH: 1.0,
    Credibility.MEDIUM: 0.6,
    Credibility.LOW: 0.3,
    None: 0.5,
}


def _side_weight(items: list[Evidence]) -> float:
    """Total weight of the publishers on one side, each counted once at its best."""
    best: dict[str, float] = {}
    for item in items:
        publisher = next(iter(publishers_of([item.citation_url])), item.citation_url)
        best[publisher] = max(best.get(publisher, 0.0), _WEIGHT[item.credibility])
    return sum(best.values())


def _confidence(decision: Decision, evidence: list[Evidence]) -> int | None:
    """How sure the verdict is, from 50 to 97, or None when there is no verdict.

    Arithmetic on the sources the verdict cites, so two people with the same evidence
    get the same number and nobody's opinion — a model's included — sets it:

      - more independent, more credible sources on the winning side raise it, with
        diminishing returns: one highly credible source gives 78, two give 89, three
        give 94; one ordinary newsroom gives 70 and two give 81;
      - a published fact-check on the winning side lifts it to at least 88, because
        someone has already done this work and put their name to it;
      - credible sources on the other side pull it down in proportion to their share.

    It never reaches 100 and never falls below 50. A verdict is never certain, and a
    verdict we are less than even about is not a verdict — that is `UNCONFIRMED`.
    """
    if not decision.status.is_decisive:
        return None
    cited = [e for e in evidence if e.id in decision.supporting_evidence_ids]
    if not cited:
        return None

    winning = cited[0].direction
    opposing_direction = (
        Direction.CONTRADICTS if winning is Direction.SUPPORTS else Direction.SUPPORTS
    )
    opposing = [
        e for e in evidence if e.direction is opposing_direction and e.is_decisive_capable
    ]

    ours = _side_weight(cited)
    theirs = _side_weight(opposing)

    score = 50.0 + 47.0 * (1.0 - math.exp(-0.9 * ours))
    if any(e.kind is EvidenceKind.FACT_CHECK for e in cited):
        score = max(score, 88.0)
    if theirs:
        score -= 30.0 * theirs / (ours + theirs)
    return round(min(97.0, max(50.0, score)))


def _decide_status(
    claim: Claim,
    evidence: list[Evidence],
    *,
    min_origins: int = DEFAULT_MIN_ORIGINS,
) -> Decision:
    """Resolve one claim against its evidence.

    Rules are evaluated in the order given in §9 and the first match wins. Every
    branch either cites the evidence that satisfied it or returns `UNVERIFIED` —
    there is no path to a decisive status without a citation.
    """
    _reject_non_evidence(evidence)

    if not claim.is_checkable:
        prediction = claim.claim_type is ClaimType.PREDICTION
        return Decision(
            status=ClaimStatus.UNVERIFIED,
            rule_id="rule.prediction_not_checked" if prediction else "rule.opinion_not_checked",
            reason=(
                "This is a claim about something that has not happened yet, so no "
                "source can confirm or refute it."
                if prediction
                else "Labelled as opinion; opinions are not fact-checked."
            ),
        )

    # Rule 7 (hoisted): no citable evidence means no verdict. Checked first because
    # every decisive branch below assumes at least one citation exists.
    if not evidence:
        return Decision(
            status=ClaimStatus.UNVERIFIED,
            rule_id="rule.no_evidence",
            reason="No citable evidence was found for this claim.",
        )

    # Rule 7 (conflict): evidence pointing both ways is surfaced, never averaged.
    # Checked before the decisive rules so a contradiction cannot win simply by
    # being earlier in the list than the support that opposes it.
    supporting = [
        e for e in evidence if e.direction is Direction.SUPPORTS and e.is_decisive_capable
    ]
    contradicting = [
        e for e in evidence if e.direction is Direction.CONTRADICTS and e.is_decisive_capable
    ]
    outranked = 0
    if supporting and contradicting:
        strongest_for = max(_TIER_AUTHORITY[e.tier] for e in supporting)
        strongest_against = max(_TIER_AUTHORITY[e.tier] for e in contradicting)
        if strongest_against > strongest_for:
            # A stronger class of evidence contradicts. Resolved rather than averaged:
            # a published adjudication outranks a page that merely reads as agreeing,
            # and a model that misreads one source — quoting a myth a page states in
            # order to debunk it — should not be able to veto a fact-check.
            #
            # Only ever in this direction. Weaker evidence contradicting stronger
            # support stays a genuine disagreement and goes to a human, because the
            # error that matters is telling someone a false claim is safe to share.
            outranked = len(supporting)
            supporting = []
        else:
            return Decision(
                status=ClaimStatus.UNVERIFIED,
                rule_id="rule.conflicting_evidence",
                reason=(
                    f"Evidence conflicts: {len(supporting)} decisive item(s) support this "
                    f"claim and {len(contradicting)} contradict it."
                ),
                conflicting=True,
            )

    decision = _decide_rules(
        claim,
        evidence,
        supporting=supporting,
        contradicting=contradicting,
        min_origins=min_origins,
    )
    if outranked and decision.status.is_decisive:
        # Said plainly, because the dissenting citation is attached to the claim and a
        # reader will see it: the verdict rests on the stronger class of evidence.
        return replace(
            decision,
            reason=(
                f"{decision.reason} {outranked} source(s) of weaker evidence appear to "
                "disagree and are cited alongside."
            ),
        )
    return decision


def _decide_rules(
    claim: Claim,
    evidence: list[Evidence],
    *,
    supporting: list[Evidence],
    contradicting: list[Evidence],
    min_origins: int,
) -> Decision:
    """The rule ladder in the fixed §9 order; the first match wins."""
    # Rule 1 — an adjudicated contradiction. The strongest claim-level finding
    # available, because someone has already done the work and published it.
    factcheck_against = _decisive(
        evidence, kind=EvidenceKind.FACT_CHECK, direction=Direction.CONTRADICTS
    )
    if factcheck_against:
        return Decision(
            status=ClaimStatus.CONTRADICTED,
            rule_id="rule.factcheck_contradiction",
            reason="A published fact-check contradicts this claim.",
            supporting_evidence_ids=tuple(e.id for e in factcheck_against),
        )

    # Rule 3 — the cited source does not carry what was attributed to it. This is a
    # narrower finding than "the claim is false", and the reason says so.
    attribution_against = _decisive(
        evidence, kind=EvidenceKind.ATTRIBUTION, direction=Direction.CONTRADICTS
    )
    if attribution_against:
        return Decision(
            status=ClaimStatus.CONTRADICTED,
            rule_id="rule.attribution_contradiction",
            reason="The cited source does not carry the statement attributed to it.",
            supporting_evidence_ids=tuple(e.id for e in attribution_against),
        )

    # Rule 2 — the media is genuine but its framing is not. This is the boundary in
    # §9: the proposition survives, the date or place around it does not.
    context_conflict = [
        item
        for item in evidence
        if item.kind in {EvidenceKind.DATED_SOURCE, EvidenceKind.MEDIA_MATCH}
        and item.direction is Direction.CONTRADICTS
        and item.is_decisive_capable
    ]
    if context_conflict:
        return Decision(
            status=ClaimStatus.MISLEADING_CONTEXT,
            rule_id="rule.dated_media_conflict",
            reason=(
                "The media is genuine but predates or otherwise conflicts with the "
                "asserted date or place."
            ),
            supporting_evidence_ids=tuple(e.id for e in context_conflict),
        )

    # Rule 3b — a contradiction carried by several independent publishers.
    #
    # Until this existed, only a published fact-check, an attribution check or a
    # dated-media conflict could contradict anything. Credible reporting could not,
    # at any volume: three outlets refuting a claim left it UNVERIFIED, which reads to
    # a user as "we found nothing" when what was found was a refutation. Support has
    # always been allowed to rest on independent origins (rule 4); this is the same
    # standard applied to the other direction.
    #
    # The remaining asymmetry is deliberate. This path can reach CONTRADICTED, which
    # withholds sharing, but there is no matching relaxation toward SUPPORTED:
    # wrongly assuring someone that a false claim is safe to share is the costlier
    # error, and syndication makes a count of publishers a weaker guarantee of
    # independence than the corroboration signal rule 4 requires.
    against_origins = _publishers(contradicting)
    if len(against_origins) >= min_origins:
        return Decision(
            status=ClaimStatus.CONTRADICTED,
            rule_id="rule.independent_contradiction",
            reason=(
                f"{len(against_origins)} independent sources contradict this claim: "
                f"{', '.join(sorted(against_origins))}.{_silence_clause(claim, supporting)}"
            ),
            supporting_evidence_ids=tuple(e.id for e in contradicting),
        )

    # Rule 3c — one highly credible source that has been checked against this exact
    # claim is enough to call it false.
    #
    # Rule 3b asks two publishers to agree, and for a viral scam there is usually one:
    # PIB's fact-check, or a single wire refutation. "Banks were told to stock ATMs
    # ahead of UPI fees", "free laptops under the National Student Laptop Scheme" and
    # "the National Sports Scholarship 2026-27" were all debunked by the government's
    # own fact-check unit and all came back "not enough evidence to decide" — on the
    # exact category of forward this product exists for.
    #
    # Only in this direction, and only on HIGH credibility, which is a property of the
    # publisher and never a model's opinion. Support still needs two independent
    # origins: wrongly telling someone a false claim is safe to share is the costlier
    # mistake, and a scam is built to look like a real programme, so a single genuine
    # page about the programme is exactly what a scam would be cleared on. Credibility
    # is only ever set on a source that passed the relevance check, so an unweighed
    # source cannot reach this rule.
    authoritative_against = [e for e in contradicting if e.credibility is Credibility.HIGH]
    if authoritative_against:
        names = ", ".join(sorted(_publishers(authoritative_against)))
        return Decision(
            status=ClaimStatus.CONTRADICTED,
            rule_id="rule.authoritative_contradiction",
            reason=f"Contradicted by a highly credible source: {names}.",
            supporting_evidence_ids=tuple(e.id for e in authoritative_against),
        )

    # Rule 5 — inside the developing-news window, silence is ambiguous. Checked
    # before support so a thin early corroboration cannot harden into SUPPORTED
    # while the story is still forming.
    if claim.within_developing_window:
        return Decision(
            status=ClaimStatus.UNVERIFIED,
            rule_id="rule.developing_window",
            reason="Too recent to corroborate; scheduled for re-check.",
        )

    # Rule 4a is deliberately absent. It was here and it cleared a scam.
    #
    # "A government source is authoritative" is right about a ministry reporting its
    # own actions, and it was implemented as "one citation on an official domain is
    # enough". Those are not the same rule. "Applications are open for the National
    # Sports Scholarship 2026-27" — a flyer PIB had already called fake — came back
    # SAFE_TO_SHARE on a single quote from scholarships.gov.in reading "students may
    # apply for one merit-based scholarship scheme and one or more welfare-based
    # scholarship schemes". That is the real National Scholarship Portal saying
    # something true and general, matched to a specific invented scheme, and the
    # domain suffix did the rest.
    #
    # A scam impersonates a real programme; that is what makes it a scam, and it is
    # exactly the case where a generic page from the impersonated body looks like
    # corroboration. Two independent origins caught it before and catches it now.
    #
    # The idea is still worth having. It needs the official source to address the
    # specific claim rather than its subject, which is a question for the reader, not
    # for a list of domain suffixes.

    # Rule 4 — support requires genuinely independent origins, not documents. Twenty
    # outlets carrying one wire copy is one origin wearing twenty mastheads.
    if supporting and claim.independent_origin_count >= min_origins:
        return Decision(
            status=ClaimStatus.SUPPORTED,
            rule_id="rule.independent_corroboration",
            reason=(
                f"{claim.independent_origin_count} independent origins across "
                f"{claim.document_count} documents support this claim."
            ),
            supporting_evidence_ids=tuple(e.id for e in supporting),
        )

    # Rule 6 — source risk is context about a publisher, never a finding about a
    # claim. Its ceiling is abstention, and the action rollup caps it at review.
    if any(e.kind is EvidenceKind.SOURCE_RISK for e in evidence):
        return Decision(
            status=ClaimStatus.UNVERIFIED,
            rule_id="rule.source_risk_only",
            reason=(
                "Only source-risk signals were found. These describe the publisher, not this claim."
            ),
        )

    # Rule 7 — everything else abstains, including the case where support exists but
    # too few independent origins carry it.
    if supporting:
        return Decision(
            status=ClaimStatus.UNVERIFIED,
            rule_id="rule.insufficient_origins",
            reason=(
                f"Only {claim.independent_origin_count} independent origin(s) found; "
                f"{min_origins} are required to support a claim."
            ),
        )

    return Decision(
        status=ClaimStatus.UNVERIFIED,
        rule_id="rule.no_qualifying_evidence",
        reason="No evidence strong enough to decide this claim."
        + _silence_clause(claim, supporting),
    )


def roll_up(
    decisions: list[tuple[Claim, Decision]],
    *,
    source_risk: SourceRisk = SourceRisk.UNKNOWN,
) -> CaseDecision:
    """The case action, and the verdict and confidence a person is shown."""
    case = _roll_up_action(decisions, source_risk=source_risk)
    verdict = _VERDICT_OF[case.action]
    return replace(case, verdict=verdict, confidence=_case_confidence(verdict, decisions))


# One verdict per action, so the words a person reads can never disagree with what
# the rules decided. Both "wait and re-check" and the old review route are
# UNCONFIRMED: neither is waiting on a human any more.
_VERDICT_OF = {
    Action.SAFE_TO_SHARE: Verdict.TRUE,
    Action.DO_NOT_SHARE: Verdict.FALSE,
    Action.SHARE_WITH_CORRECTION: Verdict.MISLEADING,
    Action.SHARE_WITH_CONTEXT: Verdict.MISLEADING,
    Action.WAIT_AND_RECHECK: Verdict.UNCONFIRMED,
    Action.SEND_TO_REVIEW: Verdict.UNCONFIRMED,
}


def verdict_for(action: Action) -> Verdict:
    """The verdict a person reads for a case action."""
    return _VERDICT_OF[action]


def _case_confidence(verdict: Verdict, decisions: list[tuple[Claim, Decision]]) -> int | None:
    return case_confidence(verdict, [(d.status, d.confidence) for _, d in decisions])


def case_confidence(verdict: Verdict, claims: list[tuple[ClaimStatus, int | None]]) -> int | None:
    """The case's confidence, from the claims that decided it.

    TRUE takes the weakest of the supported claims, because the whole piece is only
    as sound as its least-supported central claim. FALSE and MISLEADING take the
    strongest finding against it, because one well-sourced refutation is enough to
    make a piece unsafe to share.
    """
    if verdict is Verdict.UNCONFIRMED:
        return None
    if verdict is Verdict.TRUE:
        scores = [c for s, c in claims if s is ClaimStatus.SUPPORTED and c is not None]
        return min(scores) if scores else None
    against = {ClaimStatus.CONTRADICTED, ClaimStatus.MISLEADING_CONTEXT}
    scores = [c for s, c in claims if s in against and c is not None]
    return max(scores) if scores else None


def _roll_up_action(
    decisions: list[tuple[Claim, Decision]],
    *,
    source_risk: SourceRisk = SourceRisk.UNKNOWN,
) -> CaseDecision:
    """Combine per-claim statuses into the one action the user reads.

    Precedence is evaluated top to bottom and the first match wins, exactly as
    tabulated in §9. A `SUPPORTED` claim never raises the action; only contradiction
    and uncertainty move it.
    """
    if not decisions:
        return CaseDecision(
            action=Action.SEND_TO_REVIEW,
            rule_id="rollup.no_claims",
            reason="No checkable claims were extracted from this input.",
        )

    contradicted = [(c, d) for c, d in decisions if d.status is ClaimStatus.CONTRADICTED]
    misleading = [(c, d) for c, d in decisions if d.status is ClaimStatus.MISLEADING_CONTEXT]
    unverified = [(c, d) for c, d in decisions if d.status is ClaimStatus.UNVERIFIED]

    for claim, _ in contradicted:
        if claim.importance in {Importance.HEADLINE, Importance.MAIN_THESIS} or (
            claim.severity is Severity.CRITICAL
        ):
            return CaseDecision(
                action=Action.DO_NOT_SHARE,
                rule_id="rollup.contradicted_material",
                reason="A central claim in this content is contradicted by cited evidence.",
            )

    for claim, _ in contradicted:
        if claim.severity is Severity.HIGH:
            return CaseDecision(
                action=Action.DO_NOT_SHARE,
                rule_id="rollup.contradicted_high_severity",
                reason="A high-severity claim in this content is contradicted by cited evidence.",
            )

    for claim, _ in misleading:
        if claim.is_material:
            return CaseDecision(
                action=Action.SHARE_WITH_CONTEXT,
                rule_id="rollup.misleading_material",
                reason=(
                    "The media is genuine but its framing is misleading. Share only with context."
                ),
            )

    if contradicted or misleading:
        return CaseDecision(
            action=Action.SHARE_WITH_CORRECTION,
            rule_id="rollup.minor_correction",
            reason="A supporting detail is inaccurate. Share only with a correction.",
        )

    if any(claim.within_developing_window for claim, _ in unverified):
        return CaseDecision(
            action=Action.WAIT_AND_RECHECK,
            rule_id="rollup.developing",
            reason="This is too recent to corroborate. Wait for coverage to develop.",
        )

    if unverified and source_risk is SourceRisk.HIGH:
        return CaseDecision(
            action=Action.SEND_TO_REVIEW,
            rule_id="rollup.unverified_high_risk",
            reason="Nothing could be verified, and the publisher carries risk signals.",
        )

    # Every claim that carries the document must be supported. The rest may be
    # unverified without sinking the case.
    #
    # This asked for *every* claim to be supported, which a real article can almost
    # never manage. An Economic Times commentary produced seven claims; three were
    # searched and supported with thirteen citations between them, and the other four
    # were below the cap that decides how many claims are worth an open-web search,
    # so they were never searched at all. The case came back "not enough evidence to
    # decide" — on the strength of four claims nobody had looked at. The longer and
    # better-sourced the article, the more certain that outcome became.
    #
    # `is_material` is the same test the contradiction rules above already use: a
    # headline or main thesis, or anything severe enough that being wrong about it
    # matters wherever it sits. It is also what decides which claims get the
    # expensive search, so the claims that were checked are the claims that count.
    #
    # The bar is not lowered. A material claim that is unverified still abstains, a
    # contradiction anywhere still wins, and at least one claim must be positively
    # supported — silence about everything is not a clearance. What changes is that a
    # background detail nobody could confirm no longer outvotes the thesis.
    supported = [decision for _, decision in decisions if decision.status is ClaimStatus.SUPPORTED]
    unchecked = [claim for claim, _ in unverified if not claim.is_material]

    if supported and not any(claim.is_material for claim, _ in unverified):
        return CaseDecision(
            action=Action.SAFE_TO_SHARE,
            rule_id="rollup.material_supported" if unchecked else "rollup.all_supported",
            reason=(
                "Every central claim is supported by cited evidence. "
                f"{len(unchecked)} minor detail(s) could not be checked."
                if unchecked
                else "Every checkable claim is supported by cited evidence."
            ),
        )

    # Abstention is the designed destination, not a fallthrough. Source risk alone
    # can reach here but never any further: §3 rule 8 caps it at review.
    return CaseDecision(
        action=Action.SEND_TO_REVIEW,
        rule_id="rollup.abstain",
        reason="The sources we could find do not confirm or rule this out yet.",
    )
