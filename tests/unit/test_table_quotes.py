"""A quote from a table is located for its citation (2026-10-02).

A table is read in parts, each with the table's caption and header row in front of
its rows, so every part reads on its own. In the page the caption and header stand
apart from the rows - the separator line, or the earlier rows, lies between - so a
quote that took them in was not one run of the page's text. The citation step could
not find it, and PIB's own GST factsheet was thrown away twelve times in one check as
"judged quote not located for citation". Held here: such a quote is located by its two
parts, and a quote that is in the page neither whole nor in those two parts is still
refused.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.enums import Relation
from app.sources.base import SourceSnapshot, locate_excerpt
from app.sources.corpus import CorpusResolver
from app.sources.reasoning import (
    PassageJudgement,
    PassageReasoner,
    ReasoningOutcome,
    _ReasoningResponse,
    locate_quote,
    numbered_sentences,
    split_passages,
)
from app.sources.websearch import WebSearchResolver
from tests.unit.factories import claim

pytestmark = pytest.mark.unit

ROW = (
    "| Key Takeaways * Gross GST collections in October 2025 amount to ₹1,95,936 crores, "
    "a growth of 4.6% over October 2024. * Net GST revenue stood at ₹1,69,002 crores. |"
)
# PIB's factsheet as the page reader writes it: a caption, an empty header row, the
# separator line under it, then the rows.
FACTSHEET = (
    "PIB Delhi\nGST collections in October 2025\n| |\n|---|\n"
    f"{ROW}\n"
    "| * Domestic revenue grew 2% while import revenue rose 12.8% in October 2025. |\n"
)


def _judged(page: str, *, sentence: int = 1, quote: str = "") -> ReasoningOutcome:
    """What the reader's own checks make of a judgement citing [sentence] (or typing
    [quote]) of the page's first passage."""
    passages = split_passages(page)
    response = _ReasoningResponse.model_validate(
        {
            "judgements": [
                {
                    "passage_index": 0,
                    "relation": "SUPPORTS",
                    "first_sentence": 0 if quote else sentence,
                    "last_sentence": 0 if quote else sentence,
                    "quote": quote,
                    "reason": "r",
                    "relevance": 0.9,
                }
            ]
        }
    )
    reasoner = PassageReasoner.__new__(PassageReasoner)
    reasoner._model_id = "test"
    return reasoner._verify(response, passages, claim_text="GST collections rose.")


class TestATablePartKnowsItsLead:
    def test_the_caption_and_header_are_marked(self) -> None:
        (passage,) = split_passages(FACTSHEET)

        assert passage.text[: passage.lead] == "PIB Delhi GST collections in October 2025 | | "
        assert passage.text[passage.lead :].startswith("| Key Takeaways")

    def test_every_part_of_a_long_table_carries_one(self) -> None:
        rows = "".join(
            f"| Candidate number {n} | Constituency {n} | Party {n % 3} |\n" for n in range(80)
        )
        passages = split_passages("List of Winners\n| Candidate | Constituency | Party |\n" + rows)

        assert len(passages) > 1
        for passage in passages:
            assert passage.text[: passage.lead] == (
                "List of Winners | Candidate | Constituency | Party | "
            )

    def test_a_paragraph_has_none(self) -> None:
        paragraph = (
            "The finance ministry said gross GST collections in October 2025 amounted to "
            "Rs 1.96 lakh crore, a growth of 4.6 per cent over the same month last year."
        )
        (passage,) = split_passages(paragraph)

        assert passage.lead == 0


class TestTheFactsheetQuoteIsLocated:
    def test_the_quote_takes_in_the_lead_and_is_not_one_run_of_the_page(self) -> None:
        (judged,) = _judged(FACTSHEET).judgements

        assert judged.quote.startswith("PIB Delhi GST collections in October 2025 | | | Key")
        assert judged.lead == len("PIB Delhi GST collections in October 2025 | | ")
        # The failure as it was: the whole quote is not in the page.
        assert locate_excerpt(FACTSHEET, judged.quote) == ("", {})

    def test_it_is_located_by_its_two_parts_and_points_at_the_rows(self) -> None:
        (judged,) = _judged(FACTSHEET).judgements

        window, anchor = locate_quote(FACTSHEET, judged)

        assert window
        _, rows = locate_excerpt(FACTSHEET, judged.quote[judged.lead :])
        assert anchor == rows

    def test_a_quote_inside_the_rows_is_located_as_before(self) -> None:
        passages = split_passages(FACTSHEET)
        numbered = numbered_sentences(passages)
        second = next(n for n, (_, start, _) in numbered.items() if start > passages[0].lead)

        (judged,) = _judged(FACTSHEET, sentence=second).judgements

        assert judged.lead == 0
        assert locate_quote(FACTSHEET, judged) == locate_excerpt(FACTSHEET, judged.quote)
        assert locate_quote(FACTSHEET, judged)[0]

    def test_a_later_part_of_a_long_table_is_located_too(self) -> None:
        """Its rows are far from the header in the page: the earlier rows lie between."""
        rows = "".join(
            f"| Candidate number {n} won {n + 1000} votes | Constituency {n} | Party {n % 3} |\n"
            for n in range(80)
        )
        page = "List of Winners\n| Candidate | Constituency | Party |\n" + rows
        passages = split_passages(page)
        last = passages[-1]
        numbered = numbered_sentences(passages)
        first_of_last = min(n for n, (index, _, _) in numbered.items() if index == last.index)
        response = _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": last.index,
                        "relation": "SUPPORTS",
                        "first_sentence": first_of_last,
                        "last_sentence": first_of_last,
                        "reason": "r",
                        "relevance": 0.9,
                    }
                ]
            }
        )
        reasoner = PassageReasoner.__new__(PassageReasoner)
        reasoner._model_id = "test"

        (judged,) = reasoner._verify(response, passages).judgements

        assert judged.lead > 0
        assert locate_excerpt(page, judged.quote) == ("", {})
        assert locate_quote(page, judged)[0]

    def test_a_typed_quote_is_taken_from_the_page_so_its_lead_is_known(self) -> None:
        typed = (
            "PIB Delhi GST collections in October 2025 | | | Key Takeaways * Gross GST "
            "collections in October 2025 amount to ₹1,95,936 crores"
        )

        (judged,) = _judged(FACTSHEET, quote=typed).judgements

        assert judged.lead == len("PIB Delhi GST collections in October 2025 | | ")
        assert locate_quote(FACTSHEET, judged)[0]


def _judgement(quote: str, lead: int) -> PassageJudgement:
    return PassageJudgement(
        relation=Relation.SUPPORTS,
        quote=quote,
        reason="r",
        relevance=0.9,
        passage_index=0,
        lead=lead,
    )


class TestNothingElseGetsThrough:
    def test_rows_that_are_not_in_the_page_are_refused(self) -> None:
        lead = "PIB Delhi GST collections in October 2025 | | "
        judged = _judgement(lead + "| Gross GST collections fell 20% in October 2025. |", len(lead))

        assert locate_quote(FACTSHEET, judged) == ("", {})

    def test_a_lead_that_is_not_in_the_page_is_refused(self) -> None:
        lead = "Ministry of Finance | Revenue | "
        judged = _judgement(lead + ROW, len(lead))

        assert locate_quote(FACTSHEET, judged) == ("", {})

    def test_a_quote_without_a_lead_is_located_whole_or_not_at_all(self) -> None:
        stitched = "PIB Delhi GST collections in October 2025 " + ROW

        assert locate_quote(FACTSHEET, _judgement(stitched, 0)) == ("", {})

    def test_a_lead_with_nothing_after_it_is_refused(self) -> None:
        lead = "Some caption that is not there | "
        assert locate_quote(FACTSHEET, _judgement(lead, len(lead))) == ("", {})


def _snapshot(text: str) -> SourceSnapshot:
    return SourceSnapshot(
        id="web:test",
        url="https://www.pib.gov.in/factsheet",
        final_url="https://www.pib.gov.in/factsheet",
        content_hash="sha256:test",
        fetched_at=datetime.now(UTC),
        text=text,
        title="GST collections in October 2025",
        extraction_route="web.fetched",
    )


class _Reader:
    """The reader, answering with what its own checks made of a factsheet citation."""

    async def judge(self, *_args: Any, **_kwargs: Any) -> ReasoningOutcome:
        return _judged(FACTSHEET)


class TestTheSupportReachesTheCitation:
    def test_web_search_keeps_the_official_support(self) -> None:
        resolver = WebSearchResolver(
            fetcher=None,  # type: ignore[arg-type]
            reasoner=_Reader(),  # type: ignore[arg-type]
            provider="tavily",
            endpoint="https://example.invalid/search",
            api_key="k",
        )

        relation = asyncio.run(resolver.relate(claim(), _snapshot(FACTSHEET)))

        assert relation.relation is Relation.SUPPORTS
        assert relation.anchor
        # The quote shown is what was read: the rows under their caption and header.
        assert relation.excerpt.startswith("PIB Delhi GST collections in October 2025")

    def test_the_corpus_keeps_it_too(self) -> None:
        resolver = CorpusResolver.__new__(CorpusResolver)
        resolver._reasoner = _Reader()  # type: ignore[assignment]

        relation = asyncio.run(resolver._reason(claim(), _snapshot(FACTSHEET)))

        assert relation is not None
        assert relation.relation is Relation.SUPPORTS
        assert relation.anchor
