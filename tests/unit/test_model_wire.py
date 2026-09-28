"""The two model wire formats build and parse the shapes each provider expects."""

from __future__ import annotations

import json

import pytest

from app.extraction.model_wire import WireFormat, build_call, response_text

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
