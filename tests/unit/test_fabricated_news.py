"""An AI-made picture or video dressed as news, of an event nobody reports: FALSE.

"Massive lithium reserves discovered in Antarctica", on a BREAKING NEWS graphic the
detector read as 100% AI-made, came back Unconfirmed after 17 trusted pages said
nothing of it (2026-10-01). Held here: that case is FALSE at no more than 70%, and
the rule stays out of every case it was not built for - a real picture, too few
pages read, anything in the piece confirmed, a forecast, fresh news, a case already
decided - and asks the picture's checks nothing when no claim could need them.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.domain import ClaimStatus, ClaimType, Direction, Importance, Severity, Verdict
from app.domain.enums import Action, CoverageExpectation
from app.orchestration.pipeline import Orchestrator
from app.verdict.engine import FABRICATED_CAP, FABRICATED_RULE, CaseDecision, fabricated_news
from tests.unit.factories import claim

pytestmark = pytest.mark.unit

_LITHIUM = "Massive lithium reserves were discovered in Antarctica."


def _outcome(
    *,
    status: ClaimStatus = ClaimStatus.UNVERIFIED,
    claim_type: ClaimType = ClaimType.EVENT,
    importance: Importance = Importance.HEADLINE,
    severity: Severity = Severity.HIGH,
    coverage: CoverageExpectation = CoverageExpectation.HIGH,
    looked: int = 17,
    search: str = "searched",
    fresh: bool = False,
    evidence: list[Any] | None = None,
) -> Any:
    return SimpleNamespace(
        claim=claim(
            text=_LITHIUM,
            claim_type=claim_type,
            importance=importance,
            severity=severity,
            coverage_expectation=coverage,
            within_developing_window=fresh,
        ),
        decision=SimpleNamespace(status=status, conflicting=False),
        evidence=evidence or [],
        search=search,
        looked_at=looked,
    )


_UNCONFIRMED = CaseDecision(
    action=Action.SEND_TO_REVIEW, rule_id="rollup.abstain", reason="", verdict=Verdict.UNCONFIRMED
)


class _Asked:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.times = 0

    async def __call__(self) -> bool:
        self.times += 1
        return self.answer


async def _decide(
    outcomes: list[Any], made_by_ai: bool = True, case: CaseDecision = _UNCONFIRMED
) -> tuple[CaseDecision | None, int]:
    asked = _Asked(made_by_ai)
    decided = await Orchestrator._fabricated(object(), outcomes, case, asked)  # type: ignore[arg-type]
    return decided, asked.times


async def test_an_ai_made_news_picture_of_an_unreported_world_event_is_false() -> None:
    decided, asked = await _decide([_outcome()])
    assert asked == 1
    assert decided is not None
    assert decided.verdict is Verdict.FALSE
    assert decided.action is Action.DO_NOT_SHARE
    assert decided.rule_id == FABRICATED_RULE
    assert decided.confidence == FABRICATED_CAP
    assert "lithium reserves were discovered in Antarctica" in decided.reason
    assert "17 pages" in decided.reason


async def test_a_real_picture_is_left_unconfirmed() -> None:
    decided, asked = await _decide([_outcome()], made_by_ai=False)
    assert decided is None and asked == 1


@pytest.mark.parametrize(
    "outcome",
    [
        _outcome(looked=3),
        _outcome(search="unavailable"),
        _outcome(search="timed_out"),
        _outcome(claim_type=ClaimType.PREDICTION),
        _outcome(claim_type=ClaimType.OPINION),
        _outcome(coverage=CoverageExpectation.LOCAL),
        _outcome(importance=Importance.BACKGROUND),
        _outcome(fresh=True),
        _outcome(evidence=[SimpleNamespace(direction=Direction.SUPPORTS)]),
    ],
)
async def test_the_rule_stays_out_and_asks_nothing(outcome: Any) -> None:
    decided, asked = await _decide([outcome])
    assert decided is None
    assert asked == 0


async def test_a_critical_event_below_the_headline_counts() -> None:
    """The unreported world event typed a CRITICAL detail under a caption headline: it
    can still decide the case (`is_central`), as it did before an unconfirmed
    critical detail stopped holding back a reported story (2026-10-02)."""
    event = _outcome(importance=Importance.SUPPORTING_DETAIL, severity=Severity.CRITICAL)
    decided, asked = await _decide([event])
    assert asked == 1
    assert decided is not None and decided.verdict is Verdict.FALSE


async def test_an_ordinary_detail_does_not() -> None:
    decided, asked = await _decide([_outcome(importance=Importance.SUPPORTING_DETAIL)])
    assert decided is None and asked == 0


async def test_anything_confirmed_in_the_piece_keeps_it_out() -> None:
    decided, asked = await _decide([_outcome(), _outcome(status=ClaimStatus.SUPPORTED)])
    assert decided is None and asked == 0


async def test_a_case_already_decided_is_not_touched() -> None:
    false = CaseDecision(
        action=Action.DO_NOT_SHARE,
        rule_id="rollup.contradicted_material",
        reason="",
        verdict=Verdict.FALSE,
    )
    decided, asked = await _decide([_outcome()], case=false)
    assert decided is None and asked == 0


async def test_without_the_picture_checks_nothing_changes() -> None:
    decided = await Orchestrator._fabricated(object(), [_outcome()], _UNCONFIRMED, None)  # type: ignore[arg-type]
    assert decided is None


def test_the_reason_quotes_the_claim_and_says_how_much_was_read() -> None:
    decided = fabricated_news(_LITHIUM, 17)
    assert decided.reason.startswith("This picture was likely made by AI and presented as news")
    assert "We read 17 pages from trusted news and fact-checkers" in decided.reason


async def test_who_is_pictured_together_counts() -> None:
    """media-4: an AI selfie of the BRICS leaders, read as "figures who appear to be
    Putin, Modi, Xi ... are pictured at the BRICS Summit 2026" - an IDENTITY claim -
    with 20 trusted pages read and none carrying it (2026-10-02)."""
    decided, asked = await _decide([_outcome(claim_type=ClaimType.IDENTITY, looked=20)])
    assert asked == 1
    assert decided is not None
    assert decided.verdict is Verdict.FALSE
    assert decided.rule_id == FABRICATED_RULE
    assert decided.confidence == FABRICATED_CAP


async def test_but_not_when_confirmed_or_the_picture_is_real() -> None:
    supported = _outcome(
        claim_type=ClaimType.IDENTITY, evidence=[SimpleNamespace(direction=Direction.SUPPORTS)]
    )
    assert await _decide([supported]) == (None, 0)
    real, asked = await _decide([_outcome(claim_type=ClaimType.IDENTITY)], made_by_ai=False)
    assert real is None and asked == 1


@pytest.mark.parametrize("claim_type", [ClaimType.QUOTE, ClaimType.ATTRIBUTION])
async def test_a_quote_is_answered_by_its_denials_not_by_silence(claim_type: ClaimType) -> None:
    decided, asked = await _decide([_outcome(claim_type=claim_type)])
    assert decided is None and asked == 0
