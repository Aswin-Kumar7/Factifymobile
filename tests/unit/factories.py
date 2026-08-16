"""Builders for pure-core tests.

Deliberately not fixtures in `conftest`: the pure core needs no fixtures at all, and
keeping these importable-but-explicit means a test that reaches for infrastructure is
visibly doing something the core should not need.
"""

from __future__ import annotations

from itertools import count
from typing import Any

from app.domain import (
    Advisory,
    Claim,
    ClaimAnchor,
    ClaimType,
    Direction,
    Evidence,
    EvidenceKind,
    Importance,
    MatchBasis,
    Method,
    Severity,
    SourceAnchor,
    SyntheticSignal,
    Tier,
)

_ids = count(1)


def strong_basis() -> MatchBasis:
    """A metric comfortably past its threshold — derives to STRONG."""
    return MatchBasis(metric="clip_cosine", value=0.96, threshold=0.90)


def moderate_basis() -> MatchBasis:
    """A bare pass — derives to MODERATE."""
    return MatchBasis(metric="clip_cosine", value=0.91, threshold=0.90)


def weak_basis() -> MatchBasis:
    """Short of the threshold — derives to WEAK and can never be decisive."""
    return MatchBasis(metric="clip_cosine", value=0.71, threshold=0.90)


def evidence(
    *,
    kind: EvidenceKind = EvidenceKind.FACT_CHECK,
    direction: Direction = Direction.CONTRADICTS,
    tier: Tier = Tier.C,
    method: Method = Method.CLAIM_REVIEW,
    basis: MatchBasis | None = None,
    claim_id: str = "cl_1",
    **overrides: Any,
) -> Evidence:
    index = next(_ids)
    fields: dict[str, Any] = {
        "id": f"ev_{index}",
        "claim_id": claim_id,
        "tier": tier,
        "kind": kind,
        "direction": direction,
        "method": method,
        "finding": "A published fact-check rated this claim False.",
        "citation_url": f"https://factchecker.example/{index}",
        "snapshot_id": f"snap_{index}",
        "source_excerpt": "rated False on 2 June 2024",
        "source_anchor": SourceAnchor(paragraph_index=2),
        "publisher": "Factchecker",
    }
    fields.update(overrides)
    return Evidence.build(match_basis=basis or strong_basis(), **fields)


def advisory(*, score: float | None = 0.78, **overrides: Any) -> Advisory:
    index = next(_ids)
    fields: dict[str, Any] = {
        "id": f"adv_{index}",
        "provider": "noise_inconsistency",
        "signal": SyntheticSignal.ADVISORY_SUSPICION,
        "note": "Forensic signal — not used in this verdict.",
        "score": score,
    }
    fields.update(overrides)
    return Advisory(**fields)


def claim(
    *,
    claim_type: ClaimType = ClaimType.EVENT,
    severity: Severity = Severity.HIGH,
    importance: Importance = Importance.MAIN_THESIS,
    claim_id: str = "cl_1",
    **overrides: Any,
) -> Claim:
    fields: dict[str, Any] = {
        "id": claim_id,
        "text": "The eruption happened in China on 14 August.",
        "claim_type": claim_type,
        "severity": severity,
        "importance": importance,
        "anchor": ClaimAnchor(input_kind="url", content_hash="sha256:fixture", paragraph_index=3),
    }
    fields.update(overrides)
    return Claim(**fields)
