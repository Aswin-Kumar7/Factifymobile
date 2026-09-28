"""Sources about the claim, and only the claim (2026-09-28).

Found on the phone: a report of another match, or of another year's final, read as
support or contradiction for a claim about one particular final; and a shared
fact-check whose quoted viral post was checked as though the fact-check asserted it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.api.verify import _without_the_reviewed_claim
from app.domain.enums import Direction, EvidenceKind, Method, Tier
from app.extraction.claims import ExtractedClaims
from app.sources.verification import _other_occurrence
from tests.unit.factories import claim, evidence

pytestmark = pytest.mark.unit

FINAL = "India beat Australia in the 2024 T20 World Cup final."


def _report(excerpt: str, *, published: date | None = None, title: str | None = None) -> object:
    return evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.SUPPORTS,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        source_excerpt=excerpt,
        published_on=published,
        title=title,
    )


class TestAnotherOccurrence:
    def test_another_match_of_the_tournament_is_not_the_final(self) -> None:
        item = _report(
            "India beat Australia by 24 runs in the Super Eight match in St Lucia.",
            title="India beat Australia, India won by 24 runs",
        )
        assert _other_occurrence(item, claim(text=FINAL)) == "another match"  # type: ignore[arg-type]

    def test_a_report_of_the_final_that_mentions_the_semi_final_stays(self) -> None:
        item = _report("After beating England in the semi-final, India won the final.")
        assert _other_occurrence(item, claim(text=FINAL)) is None  # type: ignore[arg-type]

    def test_news_from_before_the_claimed_year_cannot_report_it(self) -> None:
        item = _report(
            "Indians are nursing broken hearts after the team lost to Australia in the "
            "World Cup final on Sunday.",
            published=date(2023, 11, 20),
        )
        assert _other_occurrence(item, claim(text=FINAL)) == "published before the event"  # type: ignore[arg-type]

    def test_an_earlier_report_naming_the_year_stays(self) -> None:
        item = _report(
            "ISRO plans to launch Gaganyaan's first crewed flight in 2027.",
            published=date(2025, 3, 1),
        )
        target = claim(text="ISRO will launch Gaganyaan's first crewed flight in 2027.")
        assert _other_occurrence(item, target) is None  # type: ignore[arg-type]

    def test_a_much_later_report_of_something_that_recurs_is_a_later_one(self) -> None:
        item = _report(
            "India won the T20 World Cup for a record third time, beating New Zealand.",
            published=date(2026, 3, 9),
        )
        target = claim(text="India won the 2024 T20 World Cup.")
        assert _other_occurrence(item, target) == "a later occurrence"  # type: ignore[arg-type]

    def test_a_later_look_back_at_a_one_off_event_stays(self) -> None:
        item = _report(
            "Two years after Chandrayaan-3 landed near the lunar south pole, ISRO is "
            "preparing Chandrayaan-4.",
            published=date(2025, 8, 23),
        )
        target = claim(text="Chandrayaan-3 landed near the Moon's south pole on 23 August 2023.")
        assert _other_occurrence(item, target) is None  # type: ignore[arg-type]

    def test_a_fact_check_is_never_set_aside_for_its_date(self) -> None:
        """An older debunk of the same video is exactly what answers a "today" claim."""
        item = evidence(source_excerpt="This video is from 2019.", published_on=date(2020, 1, 1))
        target = claim(text="This video shows floods in Assam in 2026.")
        assert _other_occurrence(item, target) is None


class TestASharedFactCheck:
    def test_the_viral_post_it_examines_is_set_aside_and_its_findings_kept(self) -> None:
        post = claim(
            claim_id="cl_1",
            text=(
                "एक्स यूजर ‘Promila’ ने 25 सितंबर 2026 को एक वीडियो शेयर करते हुए कैप्शन में "
                "लिखा कि वित्त मंत्री निर्मला सीतारमण सादगी से रहने वाले अपने पिता से मिलने पहुंचीं।"
            ),
        )
        finding = claim(
            claim_id="cl_2",
            text=(
                "वीडियो में दिख रहे बुजुर्ग व्यक्ति वित्त मंत्री निर्मला सीतारमण के पिता नहीं, "
                "बल्कि महाकवि सुब्रमण्यम भारती के भांजे केवी कृष्णन हैं।"
            ),
        )
        reviewed = ("सादगी से रहने वाले पिता से मिलने पहुंचीं वित्त मंत्री निर्मला सीतारमण।",)

        kept = _without_the_reviewed_claim(ExtractedClaims(claims=(post, finding)), reviewed)

        assert [c.id for c in kept.claims] == ["cl_2"]

    def test_nothing_is_set_aside_when_every_claim_would_be(self) -> None:
        only = claim(text="Sitharaman went to meet her father who lives simply.")
        kept = _without_the_reviewed_claim(
            ExtractedClaims(claims=(only,)), ("Sitharaman went to meet her father",)
        )
        assert kept.claims == (only,)
