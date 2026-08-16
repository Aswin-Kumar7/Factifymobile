"""The pure core: verdict engine (M06) and evidence strength (M07).

Nothing in this package performs I/O. The import-purity test in tests/unit asserts
that, because a core that can reach the network is a core nobody can trust.
"""

from app.verdict.engine import (
    DEFAULT_MIN_ORIGINS,
    RULE_VERSION,
    AdvisoryLeakError,
    CaseDecision,
    Decision,
    decide,
    roll_up,
)
from app.verdict.strength import (
    STRENGTH_VERSION,
    Band,
    Component,
    ExcludedSignal,
    Strength,
    evidence_strength,
)

__all__ = [
    "DEFAULT_MIN_ORIGINS",
    "RULE_VERSION",
    "STRENGTH_VERSION",
    "AdvisoryLeakError",
    "Band",
    "CaseDecision",
    "Component",
    "Decision",
    "ExcludedSignal",
    "Strength",
    "decide",
    "evidence_strength",
    "roll_up",
]
