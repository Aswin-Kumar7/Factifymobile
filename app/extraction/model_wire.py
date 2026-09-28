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

The format is **configuration, never code** (`FACTIFY_LLM__API_FORMAT`), so moving off
Gemini to escape its rate limits is an environment change, not a rewrite. The design
law is unaffected either way: the model proposes claims and reads passages, and every
proposal is still schema-validated and every quote still verified against the source
before anything is believed. A faster or slower provider changes latency, not what
counts as evidence.

Not handled here, on purpose:

  * **Images.** Both shapes also carry one image beside the text (`image=`): an
    `image_url` data URL for OpenAI, an `inlineData` part for Gemini. Reading a
    picture is the same JSON-returning call with a picture in the user position, so
    `app/extraction/ocr.py` uses this rather than a third request shape of its own.
  * **Azure's auth header.** Azure OpenAI authenticates with an `api-key` header and
    puts the deployment in the URL rather than the body. Bearer covers Groq and
    OpenRouter; Azure needs the small variant noted at `_openai_headers`.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class WireFormat(StrEnum):
    """Which provider dialect an endpoint speaks."""

    GEMINI = "gemini"
    OPENAI = "openai"


# A document sent in place of a picture (`build_call`'s `image`).
PDF_MIME = "application/pdf"


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
    image: tuple[bytes, str] | None = None,
    max_output_tokens: int | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Assemble one JSON-returning completion as ``(url, headers, body)``.

    `image` is ``(bytes, mime type)``: a picture sent beside the user text, for a
    model that reads images - or a PDF (`PDF_MIME`), which it reads page by page. It
    travels in the user position too, which is where untrusted content belongs.

    The external text always travels in the user position — a `contents` part for
    Gemini, a `user` message for OpenAI — never spliced into the system instruction.
    That placement is the injection boundary, and it is identical in both formats.

    `thinking` (e.g. "low") turns Gemini's deliberation down — the largest latency
    win in the reading path, and safe there because the task is classification, not
    composition. It is applied only to Gemini: it is not a portable knob, and the
    OpenAI-compatible models reached this way are already fast without one, so it is
    dropped rather than guessed at a per-provider equivalent that some would reject.

    `max_output_tokens` stops an answer that has lost its way. Without it a model
    that starts repeating itself runs to its own maximum - tens of thousands of
    tokens, minutes of waiting - and `was_cut_off` then says the answer is partial.
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
        if max_output_tokens is not None:
            generation["maxOutputTokens"] = max_output_tokens
        parts: list[dict[str, Any]] = [{"text": user_block}]
        if image is not None:
            parts.append({"inlineData": {"mimeType": image[1], "data": _base64(image[0])}})
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
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
    user_content: str | list[dict[str, Any]] = user_block
    if image is not None and image[1] == PDF_MIME:
        # A PDF goes as a file, which the provider reads page by page as a person
        # sees it - the way to read a Hindi PDF whose own text layer is scrambled.
        user_content = [
            {"type": "text", "text": user_block},
            {
                "type": "file",
                "file": {
                    "filename": "document.pdf",
                    "file_data": f"data:{PDF_MIME};base64,{_base64(image[0])}",
                },
            },
        ]
    elif image is not None:
        user_content = [
            {"type": "text", "text": user_block},
            {
                "type": "image_url",
                # "high": the text in a forwarded screenshot is small, and a low-
                # detail read of it is where invented words come from.
                "image_url": {
                    "url": f"data:{image[1]};base64,{_base64(image[0])}",
                    "detail": "high",
                },
            },
        ]
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_with_schema},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
    }
    if reasoning_model(model_id):
        # GPT-5 and the o-series think before they answer. They refuse a set
        # temperature and `max_tokens`; the cap is `max_completion_tokens`, and it
        # counts the thinking too, so it is given room for that. The effort is low:
        # every call here classifies or copies, none composes.
        body["reasoning_effort"] = "low"
        if max_output_tokens is not None:
            body["max_completion_tokens"] = max_output_tokens + _REASONING_ROOM
    else:
        body["temperature"] = temperature
        if max_output_tokens is not None:
            body["max_tokens"] = max_output_tokens
    return url, _openai_headers(api_key), body


# Tokens a reasoning model may spend thinking on top of its answer's own cap.
_REASONING_ROOM = 4_000


def reasoning_model(model_id: str) -> bool:
    """Whether a deployment is a reasoning model (GPT-5, o1/o3/o4), by its name.

    On Azure the model is reached by its deployment's name, so the deployment must be
    named after the model ("gpt-5.6-luna"), as the setup instructions say.
    """
    name = model_id.strip().casefold()
    return name.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


def _base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


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


def was_cut_off(fmt: WireFormat, envelope: dict[str, Any]) -> bool:
    """Whether the answer stopped at the output limit rather than where it ended.

    Never raises: an envelope without a stop reason is taken as complete.
    """
    try:
        if fmt is WireFormat.GEMINI:
            return str(envelope["candidates"][0].get("finishReason")) == "MAX_TOKENS"
        return str(envelope["choices"][0].get("finish_reason")) == "length"
    except (KeyError, IndexError, TypeError, AttributeError):
        return False


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
