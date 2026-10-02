"""What a post's footage is presented as is a claim of its own (re-test of 2026-10-02).

A Times Now reel of traffic lights burned in an Italian car fire, captioned with a real
European heatwave, and an X post about the real flydubai attack carrying a July 2025
easyJet clip, were each checked on their words alone: the words were largely true,
and the fact-checks of the footage had nothing to be weighed against. Told in prose
to add a claim for the footage, the extractor did not; asked as a field of its own, it
does. Words spoken in a video are put in the mouth the description shows speaking.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain import ClaimType, Importance, Severity
from app.extraction.claims import ClaimPipeline
from app.extraction.llm import (
    _RESPONSE_SCHEMA,
    _SYSTEM_INSTRUCTION,
    EXTRACTOR_VERSION,
    ExtractionOutcome,
    LLMExtractor,
)
from app.extraction.model_wire import WireFormat
from app.extraction.ocr import _DESCRIBE_INSTRUCTION, _VIDEO_INSTRUCTION, READER_VERSION
from app.security.fetcher import FetchResult

pytestmark = pytest.mark.unit

POST = (
    "Post text:\n"
    "Europe’s intense heatwave has pushed temperatures past 40°C in several countries, "
    "damaging roads and disrupting rail networks.\n\n"
    "What the video shows (described by Factify):\n"
    "Close-up views of traffic lights whose housings look melted, against a blue sky."
)
SENTENCE = (
    "Europe’s intense heatwave has pushed temperatures past 40°C in several countries, "
    "damaging roads and disrupting rail networks."
)
FOOTAGE = {
    "presented_as_event": True,
    "text": SENTENCE,
    "standalone_english": (
        "The video of drooping traffic lights was filmed in Europe's 40°C heatwave and "
        "shows its damage."
    ),
    "search_phrases": ["traffic lights video Europe heatwave fact check", "melted lights"],
}
CLAIM = {
    "text": SENTENCE,
    "claim_type": "EVENT",
    "severity": "HIGH",
    "importance": "HEADLINE",
    "standalone_english": SENTENCE,
}


def _answer(payload: dict[str, Any]) -> FetchResult:
    body = json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]})
    return FetchResult(
        url="https://llm.example",
        final_url="https://llm.example",
        status_code=200,
        content_type="application/json",
        body=body.encode(),
        byte_count=len(body),
        fetched_at=datetime.now(UTC),
    )


class _Fetcher:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.bodies: list[dict[str, Any]] = []

    async def post_json(self, url: str, body: dict[str, Any], **_: Any) -> FetchResult:
        self.bodies.append(body)
        return _answer(self.payload)


class _Governor:
    async def acquire(self, provider: str) -> object:
        return object()


async def _extracted(payload: dict[str, Any]) -> ExtractionOutcome:
    extractor = LLMExtractor(
        fetcher=_Fetcher(payload),  # type: ignore[arg-type]
        governor=_Governor(),  # type: ignore[arg-type]
        endpoint="https://llm.example",
        api_key="k",
        model_id="m",
        api_format=WireFormat.OPENAI,
    )
    return await extractor.extract_claims(POST)


class TestTheFootageClaim:
    async def test_footage_presented_as_the_event_is_a_claim(self) -> None:
        outcome = await _extracted({"claims": [CLAIM], "footage": FOOTAGE})

        assert len(outcome.claims) == 2
        footage = outcome.claims[-1]
        assert footage.claim_type is ClaimType.EVENT
        assert footage.importance is Importance.SUPPORTING_DETAIL
        assert footage.severity is Severity.HIGH
        assert footage.text == SENTENCE
        assert "traffic lights" in footage.standalone_english
        assert footage.search_phrases[0].endswith("fact check")

    async def test_anything_else_adds_nothing(self) -> None:
        none = {**FOOTAGE, "presented_as_event": False}

        outcome = await _extracted({"claims": [CLAIM], "footage": none})

        assert len(outcome.claims) == 1

    async def test_a_malformed_answer_loses_only_itself(self) -> None:
        outcome = await _extracted({"claims": [CLAIM], "footage": {"search_phrases": "x"}})

        assert outcome.succeeded
        assert len(outcome.claims) == 1

    async def test_an_answer_without_it_still_reads(self) -> None:
        outcome = await _extracted({"claims": [CLAIM]})

        assert [claim.text for claim in outcome.claims] == [SENTENCE]

    async def test_it_is_found_in_the_post_and_searched_as_the_footage(self) -> None:
        outcome = await _extracted({"claims": [CLAIM], "footage": FOOTAGE})

        class _Fixed:
            async def extract_claims(self, text: str) -> ExtractionOutcome:
                return outcome

        extracted = await ClaimPipeline(_Fixed()).extract(POST, content_hash="sha256:post")

        footage = extracted.claims[-1]
        assert footage.importance is Importance.SUPPORTING_DETAIL
        assert footage.english_text is not None and "traffic lights" in footage.english_text

    def test_the_model_is_asked_for_it(self) -> None:
        footage = _RESPONSE_SCHEMA["properties"]["footage"]

        assert "footage" in _RESPONSE_SCHEMA["required"]
        assert "presented_as_event" in footage["required"]
        assert "footage:" in _SYSTEM_INSTRUCTION
        assert "never HEADLINE, MAIN_THESIS or CRITICAL" in _SYSTEM_INSTRUCTION


class TestTheWordsOfAVideo:
    def test_a_quote_names_who_the_description_shows_speaking(self) -> None:
        assert "never 'the speaker in the video'" in _SYSTEM_INSTRUCTION
        assert "Benjamin Netanyahu said" in _SYSTEM_INSTRUCTION

    def test_a_count_that_sets_the_scene_is_split_off(self) -> None:
        assert "a count tacked onto an event to set the scene" in _SYSTEM_INSTRUCTION
        assert "the dead, the injured, the arrested - stays in it" in _SYSTEM_INSTRUCTION


def test_the_describer_says_what_tells_one_event_from_another() -> None:
    for instruction in (_VIDEO_INSTRUCTION, _DESCRIBE_INSTRUCTION):
        instruction = " ".join(instruction.split())
        assert "melted, burned, flooded, collapsed" in instruction
        assert "livery" in instruction


def test_the_versions_moved() -> None:
    assert EXTRACTOR_VERSION >= "2026.10.03.1"
    assert READER_VERSION >= "2026.10.03.3"
