"""The explanation under a verdict, written from its evidence (step 1).

Held here: it names the most authoritative source that carries the verdict and quotes
its own sentence; a fact-check leads over a news report; other sources are counted,
not named; it is in Hindi for a Hindi claim; an undecided claim with a narrower
version reported says so; and nothing is written when nothing carries the verdict.
"""

from __future__ import annotations

from app.domain import ClaimStatus, Credibility, Direction, EvidenceKind, MatchBasis, Method, Tier
from app.domain.evidence import NARROWER_SCOPE
from app.verdict.explain import explain, narrower_note
from tests.unit.factories import evidence


def _web(publisher: str, direction: Direction, quote: str, **extra: object) -> object:
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=direction,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric="passage_entailment: r", value=0.8, threshold=0.5),
        citation_url=f"https://www.{publisher.lower().replace(' ', '')}.in/story",
        publisher=publisher,
        source_excerpt=quote,
        **extra,
    )


def test_a_fact_check_leads_and_is_quoted() -> None:
    news = _web("NDTV", Direction.CONTRADICTS, "The ministry denied the report on Friday.")
    check = evidence(
        publisher="PIB Fact Check",
        source_excerpt="No such scheme has been announced by the Government of India.",
    )
    items = [news, check]
    line = explain(
        ClaimStatus.CONTRADICTED,
        items,  # type: ignore[arg-type]
        tuple(e.id for e in items),  # type: ignore[attr-defined]
        language="en",
    )
    assert line == (
        "PIB Fact Check has fact-checked this and found it false: “No such scheme has been "
        "announced by the Government of India.” 1 other source says the same."
    )


def test_support_names_the_most_credible_source() -> None:
    items = [
        _web("Some Blog", Direction.SUPPORTS, "It was confirmed.", credibility=Credibility.MEDIUM),
        _web(
            "The Hindu",
            Direction.SUPPORTS,
            "RBI kept the repo rate at 6.5%.",
            credibility=Credibility.HIGH,
        ),
    ]
    line = explain(ClaimStatus.SUPPORTED, items, tuple(e.id for e in items), language="en")  # type: ignore[arg-type, attr-defined]
    assert line is not None and line.startswith("The Hindu confirms it: “RBI kept")


def test_in_hindi_for_a_hindi_claim() -> None:
    items = [_web("BOOM", Direction.CONTRADICTS, "The video is from 2019.")]
    line = explain(ClaimStatus.CONTRADICTED, items, (items[0].id,), language="hi")  # type: ignore[arg-type, attr-defined]
    assert line is not None and line.startswith("BOOM की रिपोर्ट कुछ और कहती है")


def test_nothing_carrying_it_means_no_explanation() -> None:
    assert explain(ClaimStatus.CONTRADICTED, [], (), language="en") is None
    assert explain(ClaimStatus.UNVERIFIED, [], (), language="en") is None


def test_an_undecided_claim_with_a_narrower_version_says_so() -> None:
    narrower = evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.CONTEXTUALIZES,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=f"{NARROWER_SCOPE}: one state", value=0.8, threshold=0.5),
        publisher="India Today",
        source_excerpt="Tamil Nadu credited Rs 5,000 each to about 1.31 crore women.",
    )
    note = narrower_note([narrower], language="en")  # type: ignore[list-item]
    assert note == (
        "Only a narrower version of this is reported. India Today: “Tamil Nadu credited "
        "Rs 5,000 each to about 1.31 crore women.”"
    )
    assert narrower_note([], language="en") is None
