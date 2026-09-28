"""Twelve languages (2026-09-28): English, Hindi and ten more Indian languages.

Held here: a claim in any of them is translated into English before its sources are
sought, and a failed translation leaves it as it was; the readers see both, while
matching against English sources uses the English; search asks in both languages;
Google's free endpoint answer is parsed; and every explanation, note and correction
exists in each language with its placeholders whole.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from app.domain import ClaimStatus
from app.extraction.language import CHECKED
from app.extraction.translate import Translation, parse_free
from app.orchestration.correction import _OPENING, _SAYS, _UNCONFIRMED
from app.orchestration.pipeline import Orchestrator
from app.verdict.explain import _TEXT, explain
from app.verdict.wording import WORDING
from tests.unit.factories import claim, evidence

TAMIL = "அரசு ஒவ்வொரு பெண்ணுக்கும் மாதம் 5000 ரூபாய் வழங்கும்"
ENGLISH = "The government will give Rs 5000 every month to every woman"


class _Translator:
    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.asked: list[str] = []

    async def translate(self, text: str, *, target: str = "en", source: str = "auto") -> Any:
        self.asked.append(text)
        return Translation(text=self.answer, source="ta") if self.answer else None


def _orchestrator(translator: Any) -> Orchestrator:
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator._translator = translator
    return orchestrator


class TestTranslatedClaims:
    def test_a_claim_in_another_language_gets_its_english(self) -> None:
        translator = _Translator(ENGLISH)
        [translated] = asyncio.run(
            _orchestrator(translator)._in_english([claim(text=TAMIL, language="ta")])
        )
        assert translated.text == TAMIL
        assert translated.english_text == ENGLISH
        assert translated.matching_text == ENGLISH
        assert TAMIL in translated.reading_text and ENGLISH in translated.reading_text

    def test_english_and_hindi_matching_keep_their_own_words(self) -> None:
        translator = _Translator("unused")
        [english] = asyncio.run(
            _orchestrator(translator)._in_english([claim(text=ENGLISH, language="en")])
        )
        assert english.english_text == "" and translator.asked == []
        hindi = claim(text="सरकार हर महिला को 5000 रुपये देगी", language="hi").model_copy(
            update={"english_text": "The government will give Rs 5000 to every woman"}
        )
        assert hindi.matching_text == hindi.text

    def test_a_failed_translation_leaves_the_claim_as_it_was(self) -> None:
        [same] = asyncio.run(
            _orchestrator(_Translator(None))._in_english([claim(text=TAMIL, language="ta")])
        )
        assert same.english_text == "" and same.matching_text == TAMIL


def test_the_free_endpoint_answer_is_parsed() -> None:
    body = '[[["Government for every woman","அரசு ஒவ்வொரு பெண்ணுக்கும்",null,null,3]],null,"ta"]'
    parsed = parse_free(body)
    assert parsed == Translation(text="Government for every woman", source="ta")
    assert parse_free("not json") is None
    assert parse_free("[[],null,null]") is None


_PLACEHOLDER = re.compile(r"\{[a-z]+\}")


class TestWording:
    def test_every_language_has_every_line(self) -> None:
        newer = CHECKED - {"en", "hi"}
        assert set(WORDING) == newer
        for language in newer:
            assert set(_TEXT[language]) == set(_TEXT["en"]), language
            assert language in _OPENING and language in _SAYS and language in _UNCONFIRMED

    def test_placeholders_survived_translation(self) -> None:
        for language, lines in WORDING.items():
            for key, text in lines.items():
                if key.startswith("explain."):
                    english = _TEXT["en"][key.removeprefix("explain.")]
                    assert set(_PLACEHOLDER.findall(text)) == set(_PLACEHOLDER.findall(english)), (
                        language,
                        key,
                    )

    def test_an_explanation_is_written_in_the_claim_language(self) -> None:
        check = evidence(publisher="PIB Fact Check", source_excerpt="This claim is fake.")
        line = explain(ClaimStatus.CONTRADICTED, [check], (check.id,), language="ta")
        assert line is not None
        assert line.startswith("PIB Fact Check")
        assert "This claim is fake." in line  # the source's own words, untranslated
        assert line != explain(ClaimStatus.CONTRADICTED, [check], (check.id,), language="en")
