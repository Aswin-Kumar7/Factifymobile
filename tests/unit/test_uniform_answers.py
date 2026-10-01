"""One question, one answer, wherever and however it is asked (2026-10-01).

"DMK won the 2026 Tamil Nadu election." read Unconfirmed on the website while "DMK
wins the 2026 Tamil Nadu elections." read False on the phone. Held here: trivial
differences in a pasted text are one cache entry; a page's table is read; one
malformed judgement no longer loses a page; a page dated in the claim's year is not
dropped as old news for a year it looks back to; and the same claim in other words
brings back the pages it was decided on, once the same-claim question agrees.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.cache.keys import text_hash
from app.knowledge.memory import EvidenceMemory
from app.sources.reasoning import _lenient_response, older_than_the_claim, split_passages

pytestmark = pytest.mark.unit


def test_case_spacing_and_end_punctuation_are_one_question() -> None:
    one = text_hash("DMK won the 2026 Tamil Nadu election.")
    assert text_hash("dmk won the 2026  tamil nadu election") == one
    assert text_hash("  “DMK won the 2026 Tamil Nadu election!”  ") == one
    assert text_hash("DMK lost the 2026 Tamil Nadu election.") != one


def test_a_results_table_is_read_under_its_caption() -> None:
    page = (
        "Tamil Nadu (Total AC : 234)\nTVK\n108\nParty Wise Results\n"
        "| Party | Won | Leading | Total |\n|---|---|---|---|\n"
        "| Tamilaga Vettri Kazhagam - TVK | 108 | 0 | 108 |\n"
        "| Dravida Munnetra Kazhagam - DMK | 59 | 0 | 59 |\n"
        "| All India Anna Dravida Munnetra Kazhagam - ADMK | 47 | 0 | 47 |\n"
        "| Total | 234 | 0 | 234 |\n"
    )
    passages = split_passages(page)
    assert len(passages) == 1
    text = passages[0].text
    assert text.startswith("Party Wise Results | Party | Won")
    assert "Tamilaga Vettri Kazhagam - TVK | 108" in text and "---" not in text


def test_a_long_table_is_split_with_its_header_on_every_part() -> None:
    rows = "".join(
        f"| Candidate number {n} | Constituency {n} | Party {n % 3} |\n" for n in range(80)
    )
    passages = split_passages("List of Winners\n| Candidate | Constituency | Party |\n" + rows)
    assert len(passages) > 1
    assert all(
        p.text.startswith("List of Winners | Candidate | Constituency | Party |") for p in passages
    )


def test_menus_are_still_not_passages() -> None:
    assert (
        split_passages(
            "Home | News | Kerala | Sports | Business | Opinion | Videos | Photos | Live TV"
        )
        == []
    )


def test_one_malformed_judgement_does_not_lose_the_page() -> None:
    good = {"passage_index": 0, "relation": "CONTRADICTS", "relevance": 1.2}
    bad = {"passage_index": -1, "relation": "SUPPORTS"}
    response = _lenient_response({"judgements": [good, bad, "nonsense"]})
    assert len(response.judgements) == 1
    assert response.judgements[0].relevance == 1.0


def test_a_page_from_the_claims_year_is_not_old_news_for_looking_back() -> None:
    claim = "DMK won the 2026 Tamil Nadu election."
    quote = "The DMK and AIADMK, who have alternated in power since 1967, both sit in opposition."
    assert not older_than_the_claim(claim, quote, date(2026, 5, 4))
    # Undated, the years in the quote still decide; dated earlier, the date does.
    assert older_than_the_claim(claim, quote, None)
    assert older_than_the_claim(claim, "results declared", date(2021, 5, 2))


class _Result:
    succeeded = True
    single = (0.1,) * 384


class _Embedder:
    def embed_one(self, text: str, language: Any = None) -> _Result:
        return _Result()


class _Cursor:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    async def fetchall(self) -> list[Any]:
        return self.rows


class _Conn:
    def __init__(self, db: _Database) -> None:
        self.db = db

    async def execute(self, sql: str, params: tuple[Any, ...]) -> _Cursor:
        if "embedding <=>" in sql:
            return _Cursor(
                [
                    {
                        "text": "DMK wins the 2026 Tamil Nadu elections.",
                        "normalized_text": "dmk wins elections",
                        "near": 0.98,
                    },
                    {
                        "text": "DMK wins the 2021 Tamil Nadu election.",
                        "normalized_text": "dmk 2021",
                        "near": 0.95,
                    },
                    {"text": "Rain in Chennai", "normalized_text": "rain", "near": 0.40},
                ]
            )
        self.db.asked_for = list(params[0])
        return _Cursor(
            [
                {
                    "citation_url": "https://indianexpress.com/tn",
                    "publisher": "indianexpress.com",
                    "title": None,
                }
            ]
        )


class _Database:
    def __init__(self) -> None:
        self.asked_for: list[str] = []

    def connection(self) -> Any:
        db = self

        class _Ctx:
            async def __aenter__(self) -> _Conn:
                return _Conn(db)

            async def __aexit__(self, *args: object) -> None:
                return None

        return _Ctx()


async def test_the_same_claim_in_other_words_brings_back_its_pages() -> None:
    asked: list[str] = []

    async def same_claim(claim: str, other: str) -> bool | None:
        asked.append(other)
        return "2026" in other

    db = _Database()
    memory = EvidenceMemory(db, embedder=_Embedder(), same_claim=same_claim)
    pages = await memory.pages("dmk won election", text="DMK won the 2026 Tamil Nadu election.")

    assert [p.url for p in pages] == ["https://indianexpress.com/tn"]
    # Too far in meaning is never asked about; a near neighbour the check refuses is not used.
    assert "Rain in Chennai" not in asked
    assert db.asked_for == ["dmk won election", "dmk wins elections"]


async def test_without_an_embedder_only_the_same_wording_is_remembered() -> None:
    db = _Database()
    await EvidenceMemory(db).pages("dmk won election", text="DMK won the 2026 Tamil Nadu election.")
    assert db.asked_for == ["dmk won election"]
