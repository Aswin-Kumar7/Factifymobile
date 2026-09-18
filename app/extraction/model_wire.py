"""The two model wire formats, in one place.

The extractor (`app/extraction/llm.py`) and the reasoner (`app/sources/reasoning.py`)
each make one JSON-returning completion call. They used to carry the request shape
inline, which meant the same Gemini-specific body and the same `candidates[…]` parse
lived in two files — and switching provider meant editing both.

This module holds both shapes so those two callers hold none:

  * **Gemini** — the Generative Language API's `:generateContent`, authenticated with
    an `x-goog-api-key` header, with the response schema in `generationConfig` and the
    answer under `candidates[0].content.parts[0].text`.
  * **OpenAI-compatible** — `chat/completions`, a bearer token, `messages`, and the
    answer under `choices[0].message.content`. This is what Groq, OpenRouter and
    (with the header noted below) Azure speak.

The format is **configuration, never code** (`FACIFY_LLM__API_FORMAT`), so moving off
Gemini to escape its rate limits is an environment change, not a rewrite. The design
law is unaffected either way: the model proposes claims and reads passages, and every
proposal is still schema-validated and every quote still verified against the source
before anything is believed. A faster or slower provider changes latency, not what
counts as evidence.

Not handled here, on purpose:

  * **Vision (OCR).** `app/extraction/ocr.py` stays Gemini — the OpenAI-compatible
    surfaces reached this way (Groq's free tier) expose no vision model, so vision is
    a separate provider block (`FACIFY_VISION__*`) that can differ from the text one.
  * **Azure's auth header.** Azure OpenAI authenticates with an `api-key` header and
    puts the deployment in the URL rather than the body. Bearer covers Groq and
    OpenRouter; Azure needs the small variant noted at `_openai_headers`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class WireFormat(StrEnum):
    """Which provider dialect an endpoint speaks."""

    GEMINI = "gemini"
    OPENAI = "openai"


def build_call(
    *,
    fmt: WireFormat,
    endpoint: str,
    model_id: str,
    api_key: str,
    system: str,
    user_block: str,
    response_schema: dict[str, Any],
    temperature: float = 0.0,
    thinking: str | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Assemble one JSON-returning completion as ``(url, headers, body)``.

    The external text always travels in the user position — a `contents` part for
    Gemini, a `user` message for OpenAI — never spliced into the system instruction.
    That placement is the injection boundary, and it is identical in both formats.

    `thinking` (e.g. "low") turns Gemini's deliberation down — the largest latency
    win in the reading path, and safe there because the task is classification, not
    composition. It is applied only to Gemini: it is not a portable knob, and the
    OpenAI-compatible models reached this way are already fast without one, so it is
    dropped rather than guessed at a per-provider equivalent that some would reject.
    """
    url = endpoint.format(model=model_id)

    if fmt is WireFormat.GEMINI:
        headers = {"x-goog-api-key": api_key}
        generation: dict[str, Any] = {
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
            "temperature": temperature,
        }
        if thinking is not None:
            generation["thinkingConfig"] = {"thinkingLevel": thinking}
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user_block}]}],
            "generationConfig": generation,
        }
        return url, headers, body

    # OpenAI-compatible. The schema is not a first-class field here as it is for
    # Gemini, so it is stated in the system message and the answer is constrained to
    # a JSON object. The word "json" must appear in the messages for that mode, which
    # the instruction and the embedded schema both satisfy.
    system_with_schema = (
        f"{system}\n\nReturn ONLY a JSON object matching this schema:\n"
        f"{json.dumps(response_schema)}"
    )
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_with_schema},
            {"role": "user", "content": user_block},
        ],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }
    return url, _openai_headers(api_key), body


def _openai_headers(api_key: str) -> dict[str, str]:
    """Bearer auth, which Groq and OpenRouter accept.

    Azure OpenAI instead wants ``{"api-key": api_key}`` and no "Bearer" — when Azure
    is wired, branch here on the endpoint host rather than teaching every caller two
    header shapes.
    """
    return {"authorization": f"Bearer {api_key}"}


def response_text(fmt: WireFormat, envelope: dict[str, Any]) -> str:
    """The model's text answer, from whichever envelope shape it arrived in.

    Raises `KeyError`/`IndexError`/`TypeError` on a malformed envelope, which both
    callers already treat as a schema failure — a provider that did not return the
    expected shape has not returned a usable answer.
    """
    if fmt is WireFormat.GEMINI:
        return str(envelope["candidates"][0]["content"]["parts"][0]["text"])
    return str(envelope["choices"][0]["message"]["content"])


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What one model call actually consumed, as the provider reported it.

    Estimating this from character counts was the alternative and it is not good
    enough to bill or budget against: the ratio varies by script, and a Devanagari
    claim tokenises very differently from the same claim in English.
    """

    prompt: int = 0
    completion: int = 0

    @property
    def total(self) -> int:
        return self.prompt + self.completion


def usage_of(fmt: WireFormat, envelope: dict[str, Any]) -> TokenUsage:
    """Token counts from a response envelope, or zeros if the provider omitted them.

    Never raises. A missing usage block is a reporting gap, not a failed call, and a
    verdict must not depend on whether the meter was readable.
    """
    try:
        if fmt is WireFormat.GEMINI:
            block = envelope.get("usageMetadata") or {}
            return TokenUsage(
                prompt=int(block.get("promptTokenCount") or 0),
                completion=int(block.get("candidatesTokenCount") or 0),
            )
        block = envelope.get("usage") or {}
        return TokenUsage(
            prompt=int(block.get("prompt_tokens") or 0),
            completion=int(block.get("completion_tokens") or 0),
        )
    except (AttributeError, TypeError, ValueError):
        return TokenUsage()
