"""The two model wire formats build and parse the shapes each provider expects."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from app.extraction.model_wire import (
    MEDIA_RESOLUTION_LOW,
    WireFormat,
    build_call,
    response_text,
)

_SCHEMA = {"type": "object", "properties": {"claims": {"type": "array"}}, "required": ["claims"]}


def test_gemini_call_has_the_generate_content_shape() -> None:
    url, headers, body = build_call(
        fmt=WireFormat.GEMINI,
        endpoint="https://host/v1beta/models/{model}:generateContent",
        model_id="gemini-3-flash-preview",
        api_key="AIza-secret",
        system="extract claims",
        user_block="<<fenced document>>",
        response_schema=_SCHEMA,
    )

    assert url == "https://host/v1beta/models/gemini-3-flash-preview:generateContent"
    assert headers == {"x-goog-api-key": "AIza-secret"}
    # The document is in a data position, never in the system instruction.
    assert body["contents"][0]["parts"][0]["text"] == "<<fenced document>>"
    assert body["systemInstruction"]["parts"][0]["text"] == "extract claims"
    # The schema is transmitted, not merely referred to.
    assert body["generationConfig"]["responseSchema"] == _SCHEMA
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    # No deliberation knob unless asked.
    assert "thinkingConfig" not in body["generationConfig"]


def test_gemini_thinking_is_applied_only_when_requested() -> None:
    _, _, body = build_call(
        fmt=WireFormat.GEMINI,
        endpoint="e/{model}",
        model_id="m",
        api_key="k",
        system="s",
        user_block="u",
        response_schema=_SCHEMA,
        thinking="low",
    )
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


def test_openai_call_has_the_chat_completions_shape() -> None:
    url, headers, body = build_call(
        fmt=WireFormat.OPENAI,
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        model_id="openai/gpt-oss-120b",
        api_key="gsk-secret",
        system="extract claims",
        user_block="<<fenced document>>",
        response_schema=_SCHEMA,
    )

    # The model travels in the body here, so an endpoint with no {model} is returned
    # unchanged rather than erroring.
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert headers == {"authorization": "Bearer gsk-secret"}
    assert body["model"] == "openai/gpt-oss-120b"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    # The document stays in the user message, not the system one.
    assert body["messages"][1]["content"] == "<<fenced document>>"
    # The schema rides in the system message, since chat/completions has no schema
    # field; json-object mode needs the word "json" present, which the schema supplies.
    assert json.dumps(_SCHEMA) in body["messages"][0]["content"]
    assert body["response_format"] == {"type": "json_object"}


def test_openai_ignores_the_thinking_knob() -> None:
    # Not a portable field; it must not leak into a chat/completions body where some
    # providers would reject it.
    _, _, body = build_call(
        fmt=WireFormat.OPENAI,
        endpoint="e",
        model_id="m",
        api_key="k",
        system="s",
        user_block="u",
        response_schema=_SCHEMA,
        thinking="low",
    )
    assert "reasoning_effort" not in body
    assert "thinkingConfig" not in json.dumps(body)


def test_response_text_reads_each_envelope() -> None:
    gemini_envelope = {"candidates": [{"content": {"parts": [{"text": '{"claims": []}'}]}}]}
    openai_envelope = {"choices": [{"message": {"content": '{"claims": []}'}}]}

    assert response_text(WireFormat.GEMINI, gemini_envelope) == '{"claims": []}'
    assert response_text(WireFormat.OPENAI, openai_envelope) == '{"claims": []}'


def test_response_text_raises_on_a_malformed_envelope() -> None:
    # Both callers treat this as a schema failure: a provider that did not return the
    # expected shape has not returned a usable answer.
    with pytest.raises((KeyError, IndexError, TypeError)):
        response_text(WireFormat.GEMINI, {"choices": []})
    with pytest.raises((KeyError, IndexError, TypeError)):
        response_text(WireFormat.OPENAI, {"candidates": []})


@pytest.mark.parametrize("model", ["gpt-5.6-luna", "gpt-5.4-mini", "o4-mini"])
def test_a_reasoning_model_gets_no_temperature_and_room_to_think(model: str) -> None:
    """GPT-5 and the o-series refuse a set temperature and `max_tokens`."""
    _, _, body = build_call(
        fmt=WireFormat.OPENAI,
        endpoint="https://host/openai/v1/chat/completions",
        model_id=model,
        api_key="k",
        system="s",
        user_block="u",
        response_schema=_SCHEMA,
        max_output_tokens=600,
    )

    assert "temperature" not in body
    assert "max_tokens" not in body
    assert body["max_completion_tokens"] > 600
    assert body["reasoning_effort"] == "low"


def test_gpt_4_1_mini_keeps_its_settings() -> None:
    _, _, body = build_call(
        fmt=WireFormat.OPENAI,
        endpoint="https://host/openai/v1/chat/completions",
        model_id="gpt-4.1-mini",
        api_key="k",
        system="s",
        user_block="u",
        response_schema=_SCHEMA,
        max_output_tokens=600,
    )

    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 600
    assert "reasoning_effort" not in body


# ------------------------------------------------------------------------------ video

_YOUTUBE = "https://www.youtube.com/watch?v=4FiZyEb7Hh4"


def _video_call(fmt: WireFormat = WireFormat.GEMINI, **video: Any) -> dict[str, Any]:
    _, _, body = build_call(
        fmt=fmt,
        endpoint="https://host/v1beta/models/{model}:generateContent",
        model_id="gemini-3.8-flash",
        api_key="k",
        system="watch it",
        user_block="Watch this video.",
        response_schema=_SCHEMA,
        **video,
    )
    return body


class TestAVideoTravelsToGemini:
    def test_the_address_goes_first_bounded_and_the_text_after_it(self) -> None:
        body = _video_call(
            video_uri=_YOUTUBE,
            video_seconds=(0, 1800),
            media_resolution=MEDIA_RESOLUTION_LOW,
        )

        parts = body["contents"][0]["parts"]
        # The video before the text, the order Gemini reads video prompts best in.
        assert parts[0] == {
            "fileData": {"fileUri": _YOUTUBE},
            "videoMetadata": {"startOffset": "0s", "endOffset": "1800s"},
        }
        assert parts[1] == {"text": "Watch this video."}
        # Both in the user turn: the video is untrusted content, like a fetched page.
        assert body["contents"][0]["role"] == "user"
        assert _YOUTUBE not in json.dumps(body["systemInstruction"])
        assert body["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_LOW"

    def test_no_mime_type_is_sent_for_an_address(self) -> None:
        # Gemini works a YouTube page's type out itself; the documented REST requests
        # for one send none, and the live read (2026-10-02) succeeded without it.
        part = _video_call(video_uri=_YOUTUBE)["contents"][0]["parts"][0]

        assert "mimeType" not in part["fileData"]

    def test_without_a_window_the_whole_video_is_asked_for(self) -> None:
        part = _video_call(video_uri=_YOUTUBE)["contents"][0]["parts"][0]

        assert "videoMetadata" not in part

    def test_a_clips_bytes_go_inline_first(self) -> None:
        body = _video_call(video=(b"\x00\x00\x00\x18ftypmp42", "video/mp4"), video_seconds=(0, 90))

        part = body["contents"][0]["parts"][0]
        assert part["inlineData"]["mimeType"] == "video/mp4"
        assert base64.b64decode(part["inlineData"]["data"]) == b"\x00\x00\x00\x18ftypmp42"
        assert part["videoMetadata"] == {"startOffset": "0s", "endOffset": "90s"}

    def test_one_video_per_call(self) -> None:
        with pytest.raises(ValueError, match="one video"):
            _video_call(video_uri=_YOUTUBE, video=(b"mp4", "video/mp4"))

    def test_a_call_without_a_video_has_no_media_settings(self) -> None:
        body = _video_call()

        assert body["contents"][0]["parts"] == [{"text": "Watch this video."}]
        assert "mediaResolution" not in body["generationConfig"]


class TestAnOpenAIEndpointIsNeverHandedAVideo:
    """It takes no video, so the prompt alone would come back as a confident reading
    of a video nobody watched."""

    def test_an_address_raises(self) -> None:
        with pytest.raises(ValueError, match="only be read by a Gemini endpoint"):
            _video_call(WireFormat.OPENAI, video_uri=_YOUTUBE)

    def test_bytes_raise(self) -> None:
        with pytest.raises(ValueError, match="only be read by a Gemini endpoint"):
            _video_call(WireFormat.OPENAI, video=(b"mp4", "video/mp4"))

    def test_the_frame_resolution_is_not_sent(self) -> None:
        # Gemini's knob, like `thinking`: not guessed at for another provider.
        body = _video_call(WireFormat.OPENAI, media_resolution=MEDIA_RESOLUTION_LOW)

        assert "mediaResolution" not in json.dumps(body)


class TestThinkingIsTheModelsOwnKnob:
    def test_a_number_is_a_gemini_2_5_budget(self) -> None:
        body = _video_call(thinking="1024")

        assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 1024}

    def test_zero_turns_a_budget_off(self) -> None:
        body = _video_call(thinking="0")

        assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}

    def test_a_word_is_a_gemini_3_level(self) -> None:
        body = _video_call(thinking="low")

        assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}

    def test_a_blank_setting_is_no_setting(self) -> None:
        # Sent, Gemini refuses an empty level with a 400 on every call (2026-10-02).
        body = _video_call(thinking=" ")

        assert "thinkingConfig" not in body["generationConfig"]
