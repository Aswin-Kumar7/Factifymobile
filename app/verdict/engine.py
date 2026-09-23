"""The verdict engine (M06). Pure function. No I/O of any kind.

This module implements codexplan.md §9. It imports nothing that can reach a network,
a database, a model or a filesystem, and that is checked by a test rather than left
to discipline — if the core is not pure, nothing downstream is trustworthy.

Its signature accepts `Evidence` only. `Advisory` is a different type with no shared
base, so Tier E cannot reach this code by any path that type-checks, and a runtime
guard catches the untyped caller as well.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.claim import Claim
from app.domain.enums import (
    Action,
    ClaimStatus,
    ClaimType,
    CoverageExpectation,
    Direction,
    EvidenceKind,
    Importance,
    Severity,
    SourceRisk,
    Tier,
)
from app.domain.evidence import Evidence
from app.domain.publishers import publishers_of

# Stamped on every verdict. A cached verdict produced under older rules is therefore
# identifiable, and the cache can refuse to serve it (M13).
RULE_VERSION = "2026.09.9"

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

    # Rule 5 — inside the developing-news window, silence is ambiguous. Checked
    # before support so a thin early corroboration cannot harden into SUPPORTED
    # while the story is still forming.
    if claim.within_developing_window:
        return Decision(
            status=ClaimStatus.UNVERIFIED,
            rule_id="rule.developing_window",
            reason="Too recent to corroborate; scheduled for re-check.",
        )

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

    if all(d.status is ClaimStatus.SUPPORTED for _, d in decisions):
        return CaseDecision(
            action=Action.SAFE_TO_SHARE,
            rule_id="rollup.all_supported",
            reason="Every checkable claim is supported by cited evidence.",
        )

    # Abstention is the designed destination, not a fallthrough. Source risk alone
    # can reach here but never any further: §3 rule 8 caps it at review.
    return CaseDecision(
        action=Action.SEND_TO_REVIEW,
        rule_id="rollup.abstain",
        reason="Not enough citable evidence to decide. Routed for human review.",
    )
