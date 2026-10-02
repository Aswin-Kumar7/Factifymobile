"""A debunk calling a picture AI-made contradicts "these people are pictured" (media-4).

An AI selfie of the BRICS leaders - the late Ebrahim Raisi among them - was read as
"figures who appear to be Putin, Modi, Xi, Lula, Erdogan and Ramaphosa are pictured in
front of a BRICS Summit 2026 backdrop". Read literally, a fake does picture them, so
the first reader read France 24's "Viral Putin, Modi and Xi selfie at BRICS summit is
AI-generated" as support and The Quint's and the Guardian Nigeria's debunks as
narrower versions; the source check said FALSE and about this claim for all of them,
and every one was thrown away. The case came back Unconfirmed (2026-10-02).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.domain import ClaimType, Credibility, Direction, EvidenceKind, MatchBasis, Method, Tier
from app.domain.evidence import NARROWER_SCOPE
from app.sources.reasoning import SourceCheck, SourceReading
from app.sources.verification import SourceVerification, depicts
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit

PICTURED = (
    "Figures who appear to be Putin, Modi, Xi, Lula, Erdogan and Ramaphosa are pictured "
    "with several other men in front of a BRICS Summit 2026 backdrop."
)
DEBUNK = "Viral Putin, Modi and Xi selfie at BRICS summit is AI-generated"


def _read(read: str, *, title: str = DEBUNK, excerpt: str = "The selfie is not real.") -> Any:
    direction, metric = {
        "supports": (Direction.SUPPORTS, "passage_entailment: r"),
        "narrower": (Direction.CONTEXTUALIZES, f"{NARROWER_SCOPE}: r"),
        "contradicts": (Direction.CONTRADICTS, "passage_entailment: r"),
    }[read]
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=direction,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=metric, value=0.9, threshold=0.5),
        citation_url="https://www.france24.com/en/viral-brics-selfie",
        publisher="france24.com",
        title=title,
        source_excerpt=excerpt,
    )


class _Checker:
    def __init__(self, verdict: str, **reading: Any) -> None:
        self.verdict = verdict
        self.reading = {"addresses_claim": True, **reading}

    async def check_sources(self, claim_text: str, sources: list[tuple[str, str]]) -> Any:
        return SourceCheck(
            readings={
                i: SourceReading(
                    verdict=self.verdict, reason="the image is AI-made", **self.reading
                )
                for i in range(len(sources))
            },
            explanation="",
        )


class _Ranker:
    def credibility(self, _url: str | None) -> Credibility:
        return Credibility.HIGH


def _kept(checker: _Checker, item: Any, text: str = PICTURED) -> list[Any]:
    subject = claim(text=text, claim_type=ClaimType.IDENTITY)
    verified = asyncio.run(
        SourceVerification(checker=checker, ranker=_Ranker()).check(subject, [item])
    )
    return list(verified.evidence)


@pytest.mark.parametrize("read", ["supports", "narrower"])
def test_a_debunk_of_the_picture_itself_contradicts_who_it_shows(read: str) -> None:
    [kept] = _kept(_Checker("FALSE"), _read(read))

    assert kept.direction is Direction.CONTRADICTS


def test_not_for_a_claim_about_an_event() -> None:
    """Only a claim about what a picture shows: elsewhere the step never turns a
    source to the other side."""
    event = "The BRICS 2026 summit was held at Bharat Mandapam in New Delhi."

    assert _kept(_Checker("FALSE"), _read("supports"), text=event) == []


def test_not_when_the_check_finds_it_about_something_else() -> None:
    assert _kept(_Checker("FALSE", addresses_claim=False), _read("supports")) == []


def test_not_when_the_debunk_does_not_call_the_picture_made() -> None:
    plain = _read("supports", title="BRICS leaders meet in Delhi", excerpt="They met on Friday.")

    assert _kept(_Checker("FALSE"), plain) == []


def test_not_when_the_check_does_not_say_false() -> None:
    """A page saying the picture is NOT AI-generated is read TRUE, and stays support."""
    [kept] = _kept(_Checker("TRUE"), _read("supports", title="The selfie is not AI-generated"))

    assert kept.direction is Direction.SUPPORTS


def test_not_when_the_debunk_rules_a_fake_out() -> None:
    """ "Authentic - not AI-generated or digitally altered - but from 2019" says the
    picture is real: never turned into a contradiction of who it shows."""
    real = _read(
        "supports",
        title="Old photo of the leaders shared as BRICS 2026",
        excerpt="The photo is authentic, not AI-generated or digitally altered, but is from 2019.",
    )

    assert _kept(_Checker("FALSE"), real) == []


def test_a_contradiction_stays_one() -> None:
    [kept] = _kept(_Checker("FALSE"), _read("contradicts"))

    assert kept.direction is Direction.CONTRADICTS


@pytest.mark.parametrize(
    ("text", "about_a_picture"),
    [
        (PICTURED, True),
        ("Putin, Modi and Xi took a selfie together at the BRICS 2026 summit.", True),
        ("The video of drooping traffic lights was filmed in Europe's heatwave.", True),
        ("The RBI kept the repo rate unchanged at 5.25%.", False),
    ],
)
def test_what_counts_as_a_claim_about_a_picture(text: str, about_a_picture: bool) -> None:
    assert depicts(claim(text=text)) is about_a_picture
