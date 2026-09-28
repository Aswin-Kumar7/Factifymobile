"""The verdict fixes of 2026-09-28, each for a failure seen live.

Held here: the reader names sentences by number and the words are copied from the
page, so a rupee sign, a Hindi danda or a curly quote arrives exactly as published;
a run of more than three sentences is not evidence; the fact-check API is asked
unless one of our records is a close match; and a narrower source both readings
agree on is kept even when the check also says it is "not about the claim".
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.domain import Credibility, Direction, EvidenceKind, MatchBasis, Method, Tier
from app.domain.evidence import NARROWER_SCOPE, is_narrower_scope
from app.sources.factcheck import FactCheckRecord, FactCheckResolver
from app.sources.reasoning import (
    _RESPONSE_SCHEMA,
    Passage,
    PassageReasoner,
    SourceCheck,
    SourceReading,
    _ReasoningResponse,
    sentence_spans,
)
from app.sources.verification import SourceVerification
from tests.unit.factories import claim, evidence

PAGE = (
    "Chief Minister M.K. Stalin on Friday announced a bonanza, crediting ₹7,000 each "
    "to 1.31 crore women. The amount includes ₹1,000 as the monthly grant. "
    "हर महिला को पैसे "
    "मिलेंगे। It is a state scheme."
)


def _read(**judgement: Any) -> Any:
    reasoner = PassageReasoner.__new__(PassageReasoner)
    reasoner._model_id = "test"
    response = _ReasoningResponse.model_validate(
        {
            "judgements": [
                {
                    "passage_index": 0,
                    "relation": "CONTEXTUALIZES",
                    "reason": "a state scheme",
                    "relevance": 0.9,
                    **judgement,
                }
            ]
        }
    )
    passages = [Passage(index=0, text=PAGE, char_start=500, char_end=500 + len(PAGE))]
    return reasoner._verify(response, passages)


class TestPointDontCopy:
    def test_sentences_split_where_sentences_end_and_not_after_initials(self) -> None:
        sentences = [PAGE[a:b] for a, b in sentence_spans(PAGE)]
        assert sentences[0].startswith("Chief Minister M.K. Stalin")
        assert sentences[2].endswith("।")
        assert len(sentences) == 4

    def test_the_cited_words_are_the_page_own_rupee_signs_and_all(self) -> None:
        [judgement] = _read(first_sentence=2, last_sentence=2).judgements
        assert judgement.quote == "The amount includes ₹1,000 as the monthly grant."
        assert PAGE[judgement.char_start - 500 : judgement.char_end - 500] == judgement.quote

    def test_a_run_of_sentences_is_one_citation(self) -> None:
        [judgement] = _read(first_sentence=1, last_sentence=2).judgements
        assert judgement.quote.startswith("Chief Minister")
        assert judgement.quote.endswith("monthly grant.")

    def test_more_than_three_sentences_or_a_missing_one_is_not_evidence(self) -> None:
        assert _read(first_sentence=1, last_sentence=4).judgements == ()
        assert _read(first_sentence=9, last_sentence=9).judgements == ()

    def test_a_typed_quote_is_still_checked_when_no_numbers_are_given(self) -> None:
        assert _read(quote="The amount includes ₹1,000 as the monthly grant.").judgements
        assert _read(quote="The amount includes ₹2,000 as the monthly grant.").judgements == ()

    def test_the_model_is_asked_for_numbers_not_words(self) -> None:
        item = _RESPONSE_SCHEMA["properties"]["judgements"]["items"]
        assert "first_sentence" in item["required"] and "quote" not in item["required"]


def _record(text: str, url: str) -> FactCheckRecord:
    return FactCheckRecord(
        claim_text=text,
        normalized_text=text.lower(),
        url=url,
        rating="False",
        publisher="PIB Fact Check",
    )


class _Governor:
    async def try_acquire(self, _provider: str) -> object:
        return object()


class _Resolver(FactCheckResolver):
    def __init__(self, records: list[FactCheckRecord]) -> None:
        super().__init__(records=records, governor=_Governor(), api_available=True)
        self._api_available = True
        self.asked = 0

    async def _query_api(self, _claim: Any) -> list[FactCheckRecord]:
        self.asked += 1
        return [_record("Govt to pay Rs 5000 a month to every woman is fake", "https://api/1")]


class TestFactCheckLookup:
    def test_a_loose_local_match_no_longer_stops_the_api(self) -> None:
        resolver = _Resolver([_record("Rs 5000 scholarship for every student", "https://ours/1")])
        found = asyncio.run(
            resolver.candidates(claim(text="Govt to pay Rs 5000 a month to every woman"))
        )
        assert resolver.asked == 1
        assert {c.url for c in found} == {"https://api/1", "https://ours/1"}

    def test_a_close_local_match_answers_without_the_api(self) -> None:
        resolver = _Resolver(
            [_record("Govt to pay Rs 5000 a month to every woman", "https://ours/2")]
        )
        found = asyncio.run(
            resolver.candidates(claim(text="Govt to pay Rs 5000 a month to every woman"))
        )
        assert resolver.asked == 0
        assert [c.url for c in found] == ["https://ours/2"]


class _Checker:
    async def check_sources(self, _claim: str, sources: list[tuple[str, str]]) -> SourceCheck:
        return SourceCheck(
            readings={
                i: SourceReading(
                    addresses_claim=False,
                    verdict="PARTLY",
                    reason="one state",
                    smaller_version=True,
                    states_differently=True,
                )
                for i in range(len(sources))
            },
            explanation="",
        )


class _Ranker:
    def credibility(self, _url: str | None) -> Credibility:
        return Credibility.HIGH


def test_a_narrower_source_both_readings_agree_on_is_kept() -> None:
    narrower = evidence(
        kind=EvidenceKind.CORROBORATION,
        direction=Direction.CONTEXTUALIZES,
        tier=Tier.D,
        method=Method.PASSAGE_ENTAILMENT,
        basis=MatchBasis(metric=f"{NARROWER_SCOPE}: one state", value=0.9, threshold=0.5),
        citation_url="https://www.indiatoday.in/story",
        publisher="India Today",
    )
    verified = asyncio.run(
        SourceVerification(checker=_Checker(), ranker=_Ranker()).check(
            claim(text="Govt to pay Rs 5000 a month to every woman"), [narrower]
        )
    )
    [kept] = verified.evidence
    assert is_narrower_scope(kept.match_basis.metric)


def test_sentence_numbers_run_through_the_page_and_name_their_passage() -> None:
    reasoner = PassageReasoner.__new__(PassageReasoner)
    reasoner._model_id = "test"
    first = "The scheme was announced on Friday. It pays Rs 5,000 once."
    second = "Only Tamil Nadu residents are eligible for the payment. Applications close soon."
    passages = [
        Passage(index=0, text=first, char_start=0, char_end=len(first)),
        Passage(index=4, text=second, char_start=100, char_end=100 + len(second)),
    ]

    def judge(first_sentence: int, last_sentence: int, passage_index: int = 0) -> Any:
        response = _ReasoningResponse.model_validate(
            {
                "judgements": [
                    {
                        "passage_index": passage_index,
                        "first_sentence": first_sentence,
                        "last_sentence": last_sentence,
                        "relation": "CONTEXTUALIZES",
                        "reason": "eligibility",
                        "relevance": 0.8,
                    }
                ]
            }
        )
        return reasoner._verify(response, passages).judgements

    # Sentence 3 is the first sentence of the second passage, whatever index is given.
    [cited] = judge(3, 3, passage_index=0)
    assert cited.quote == "Only Tamil Nadu residents are eligible for the payment."
    assert cited.passage_index == 4
    # A run may not cross from one passage into the next.
    assert judge(2, 3) == ()
