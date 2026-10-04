"""A figure for the claim's own count far below the claim's is a contradiction.

"Millions of Koreans gathered in Gwanghwamun Square" was checked against Chosun's
"about 10,000 people" and Yonhap's "the party claimed some 200,000". Chosun was kept
as a narrower version and the claim read Unconfirmed (2026-10-03). A crowd a hundredth
of the size says the claim is wrong.
"""

from __future__ import annotations

import asyncio

from app.domain import Credibility, Direction, EvidenceKind, MatchBasis, Method, Tier
from app.domain.evidence import NARROWER_SCOPE, is_narrower_scope
from app.sources.reasoning import SourceCheck, SourceReading
from app.sources.verification import SourceVerification, far_below
from tests.unit.factories import claim, evidence

CLAIM = "Millions of Koreans gathered in Gwanghwamun Square on October 3, 2026, for rallies"


def _narrower(excerpt: str) -> object:
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.CONTEXTUALIZES,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=f"{NARROWER_SCOPE}: one rally", value=0.9, threshold=0.0),
        citation_url="https://www.chosun.com/rally",
        publisher="chosun.com",
        source_excerpt=excerpt,
    )


class _Checker:
    def __init__(self, *, far_smaller: bool, verdict: str = "PARTLY") -> None:
        self.far_smaller = far_smaller
        self.verdict = verdict

    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> SourceCheck:
        return SourceCheck(
            readings={
                i: SourceReading(
                    addresses_claim=True,
                    verdict=self.verdict,
                    reason="about 10,000 people, not millions",
                    smaller_version=True,
                    states_differently=True,
                    far_smaller_figure=self.far_smaller,
                )
                for i in range(len(sources))
            },
            explanation="",
        )


class _Ranker:
    def credibility(self, _url: str | None) -> Credibility:
        return Credibility.HIGH


def _verify(excerpt: str, *, far_smaller: bool = True, verdict: str = "PARTLY") -> object:
    return asyncio.run(
        SourceVerification(
            checker=_Checker(far_smaller=far_smaller, verdict=verdict), ranker=_Ranker()
        ).check(claim(text=CLAIM), [_narrower(excerpt)])  # type: ignore[list-item]
    )


class TestFarBelow:
    def test_tens_of_thousands_is_far_below_millions(self) -> None:
        assert far_below(CLAIM, "About 10,000 people gathered at a Seoul rally.")
        assert far_below(CLAIM, "The party claimed some 200,000 protesters joined.")
        assert far_below("2 lakh people attended", "About 15,000 attended")

    def test_a_figure_near_the_claim_is_not(self) -> None:
        assert not far_below(CLAIM, "Organisers said 1.5 million people joined.")
        assert not far_below("More than 30 people died", "Sewage caused 24 of the 36 deaths")

    def test_every_figure_must_be_far_below(self) -> None:
        assert not far_below(CLAIM, "Police counted 10,000; organisers said 2 million.")

    def test_money_percentages_years_and_dates_are_not_counts(self) -> None:
        assert not far_below(
            "Govt to pay Rs 5,000 a month to every woman", "Tamil Nadu pays Rs 1,000 a month"
        )
        assert not far_below("50,000 farmers marched", "turnout was up 20% on 2019")
        assert not far_below(CLAIM, "The rally was held on October 3, 2026.")


class TestTheSourceCheck:
    def test_a_far_smaller_crowd_is_kept_as_a_contradiction(self) -> None:
        verified = _verify("About 10,000 people gathered at the Seoul rally.")
        [kept] = verified.evidence  # type: ignore[attr-defined]
        assert kept.direction is Direction.CONTRADICTS
        assert not is_narrower_scope(kept.match_basis.metric)

    def test_without_the_checks_yes_it_stays_narrower(self) -> None:
        verified = _verify("About 10,000 people gathered.", far_smaller=False)
        [kept] = verified.evidence  # type: ignore[attr-defined]
        assert is_narrower_scope(kept.match_basis.metric)

    def test_the_numbers_must_bear_out_the_checks_yes(self) -> None:
        verified = _verify("Organisers said 1.5 million people joined.")
        [kept] = verified.evidence  # type: ignore[attr-defined]
        assert kept.direction is not Direction.CONTRADICTS

    def test_never_against_the_checks_true(self) -> None:
        verified = _verify("About 10,000 people gathered.", verdict="TRUE")
        [kept] = verified.evidence  # type: ignore[attr-defined]
        assert kept.direction is Direction.SUPPORTS
