"""Evidence strength (M07) — a deterministic explanation index, not a probability.

The brief asks for an explainable authenticity score. A softmax output is a number
without an explanation, so this is the inverse: a score assembled from components,
each of which names the citations that produced it. A reader can recompute it.

What it is not, stated because the distinction is the product:

  - not a probability that the claim is true;
  - not a global authenticity score conflating provenance with truth;
  - not influenced by any advisory signal. Advisory items are reported *beside* the
    calculation and explicitly excluded from it, and a test asserts that maximising
    every one of them moves the score by exactly zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import Direction, EvidenceKind, MatchQuality, SourceRisk, Tier
from app.domain.evidence import Advisory, Evidence
from app.verdict.engine import AdvisoryLeakError

STRENGTH_VERSION = "2026.08.1"

# Tier weights. A cryptographic manifest outranks a dated source outranks an
# adjudicated fact-check outranks corroboration — but only within their own claims:
# Tier A speaks to provenance, Tier C to the claim. The weight orders confidence in
# the finding, not the scope of what it establishes.
_TIER_WEIGHT = {Tier.A: 1.00, Tier.B: 0.90, Tier.C: 0.95, Tier.D: 0.70}

_QUALITY_WEIGHT = {
    MatchQuality.STRONG: 1.00,
    MatchQuality.MODERATE: 0.65,
    MatchQuality.WEAK: 0.25,
}

_RISK_TRANSPARENCY = {
    SourceRisk.LOW: 1.00,
    SourceRisk.MEDIUM: 0.60,
    SourceRisk.HIGH: 0.20,
    SourceRisk.UNKNOWN: 0.50,
}

# Origins beyond this add nothing. Three genuinely independent sources is a real
# corroboration; thirty is the same fact, and pretending otherwise would let a
# syndication wave outweigh a cryptographic manifest.
_ORIGIN_SATURATION = 3


class Band(str):
    """Human-readable strength label."""

    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    CONCLUSIVE = "conclusive"


@dataclass(frozen=True, slots=True)
class Component:
    """One term of the score, with the citations that produced it."""

    name: str
    value: float
    detail: str
    citations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExcludedSignal:
    """An advisory signal, reported beside the score and not part of it."""

    provider: str
    signal: str
    score: float | None
    note: str = "Not used in this verdict or score."


@dataclass(frozen=True, slots=True)
class Strength:
    """The score, its components, and what was deliberately left out."""

    score: float
    band: str
    components: tuple[Component, ...]
    advisory_excluded: tuple[ExcludedSignal, ...] = ()
    version: str = STRENGTH_VERSION
    citations: tuple[str, ...] = field(default=())


def _band(score: float) -> str:
    if score <= 0.0:
        return Band.NONE
    if score < 0.35:
        return Band.WEAK
    if score < 0.60:
        return Band.MODERATE
    if score < 0.85:
        return Band.STRONG
    return Band.CONCLUSIVE


def _tier_composition(evidence: list[Evidence]) -> Component:
    """Best available tier, weighted by how well each item's match held up."""
    if not evidence:
        return Component(name="tier_composition", value=0.0, detail="no evidence")

    scored = [
        (_TIER_WEIGHT[item.tier] * _QUALITY_WEIGHT[item.match_quality], item) for item in evidence
    ]
    best_value, _ = max(scored, key=lambda pair: pair[0])

    counts: dict[str, int] = {}
    for item in evidence:
        counts[item.tier.value] = counts.get(item.tier.value, 0) + 1
    detail = ", ".join(f"{count}×{tier}" for tier, count in sorted(counts.items()))

    return Component(
        name="tier_composition",
        value=round(best_value, 4),
        detail=detail,
        citations=tuple(item.citation_url for item in evidence),
    )


def _independent_origins(origin_count: int, document_count: int) -> Component:
    """Origins, not documents — the distinction corroboration rests on."""
    value = min(origin_count, _ORIGIN_SATURATION) / _ORIGIN_SATURATION
    detail = f"{origin_count} distinct origin(s) across {document_count} document(s)"
    return Component(name="independent_origins", value=round(value, 4), detail=detail)


def _temporal_confidence(evidence: list[Evidence]) -> Component:
    """How well the dating of the strongest temporal finding is established."""
    temporal = [
        item
        for item in evidence
        if item.kind in {EvidenceKind.DATED_SOURCE, EvidenceKind.MEDIA_MATCH}
    ]
    if not temporal:
        return Component(name="temporal_confidence", value=0.0, detail="no dated evidence")

    value = max(_QUALITY_WEIGHT[item.match_quality] for item in temporal)
    return Component(
        name="temporal_confidence",
        value=round(value, 4),
        detail=f"{len(temporal)} dated finding(s)",
        citations=tuple(item.citation_url for item in temporal),
    )


def _source_transparency(source_risk: SourceRisk) -> Component:
    value = _RISK_TRANSPARENCY[source_risk]
    return Component(
        name="source_transparency",
        value=value,
        detail=f"publisher risk {source_risk.value}",
    )


def _conflict_penalty(evidence: list[Evidence]) -> Component:
    """Evidence pointing both ways lowers the score rather than cancelling out.

    Averaging opposing findings would produce a middling number that looks like
    moderate confidence when what actually exists is a disagreement.
    """
    supports = sum(1 for item in evidence if item.direction is Direction.SUPPORTS)
    contradicts = sum(1 for item in evidence if item.direction is Direction.CONTRADICTS)

    if not (supports and contradicts):
        return Component(name="conflict_penalty", value=0.0, detail="no conflict")

    return Component(
        name="conflict_penalty",
        value=-0.30,
        detail=f"{supports} supporting and {contradicts} contradicting finding(s)",
    )


def evidence_strength(
    evidence: list[Evidence],
    advisory: list[Advisory] | None = None,
    *,
    independent_origin_count: int = 0,
    document_count: int = 0,
    source_risk: SourceRisk = SourceRisk.UNKNOWN,
) -> Strength:
    """Compute the explainable score.

    `advisory` is accepted only so it can be reported as excluded. It is never read
    for its value, and a caller that passes evidence in that position is rejected
    rather than quietly counted.
    """
    for item in evidence:
        if not isinstance(item, Evidence):
            raise AdvisoryLeakError(
                f"evidence_strength received {type(item).__name__} as evidence; "
                "advisory signals belong in the advisory argument, where they are "
                "reported but not counted"
            )

    tier = _tier_composition(evidence)
    origins = _independent_origins(independent_origin_count, document_count)
    temporal = _temporal_confidence(evidence)
    transparency = _source_transparency(source_risk)
    penalty = _conflict_penalty(evidence)

    components = (tier, origins, temporal, transparency, penalty)

    if not evidence:
        score = 0.0
    else:
        # Tier composition dominates: one cryptographic or adjudicated finding is
        # worth more than a wide but shallow spread of weak corroboration.
        weighted = (
            0.45 * tier.value
            + 0.25 * origins.value
            + 0.20 * temporal.value
            + 0.10 * transparency.value
        )
        score = max(0.0, min(1.0, weighted + penalty.value))

    excluded = tuple(
        ExcludedSignal(provider=item.provider, signal=item.signal.value, score=item.score)
        for item in (advisory or [])
    )

    return Strength(
        score=round(score, 4),
        band=_band(score),
        components=components,
        advisory_excluded=excluded,
        citations=tuple(dict.fromkeys(item.citation_url for item in evidence)),
    )
