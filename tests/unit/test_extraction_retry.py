"""A model provider's one-off refusal no longer loses every claim (2026-10-01).

The AI-made "lithium in Antarctica" news graphic was refused once with a 400 and
accepted four times after; the one refusal came back "Unconfirmed". Held here: a 400
or 5xx from the provider is tried once more, a refusal that persists is reported with
the provider's own error code, and any other failure is not retried.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.extraction.llm import LLMExtractor, _worth_another_try
from app.extraction.model_wire import WireFormat
from app.security.fetcher import FetchFailure, FetchResult, _provider_error

pytestmark = pytest.mark.unit


def _ok() -> FetchResult:
    body = json.dumps({"choices": [{"message": {"content": json.dumps({"claims": []})}}]})
    return FetchResult(
        url="https://llm.example",
        final_url="https://llm.example",
        status_code=200,
        content_type="application/json",
        body=body.encode(),
        byte_count=len(body),
        fetched_at=datetime.now(UTC),
    )


_REFUSED = FetchFailure(
    url="https://llm.example",
    reason="provider returned 400 (content_filter: flagged)",
    kind="provider_error",
)


class _Fetcher:
    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.calls = 0

    async def post_json(self, *_: object, **__: object) -> object:
        self.calls += 1
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


class _Governor:
    async def acquire(self, provider: str) -> object:
        return object()


def _extractor(fetcher: _Fetcher) -> LLMExtractor:
    return LLMExtractor(
        fetcher=fetcher,  # type: ignore[arg-type]
        governor=_Governor(),  # type: ignore[arg-type]
        endpoint="https://llm.example",
        api_key="k",
        model_id="m",
        api_format=WireFormat.OPENAI,
    )


async def test_a_one_off_refusal_is_tried_once_more(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.extraction.llm.asyncio.sleep", _no_wait)
    fetcher = _Fetcher(_REFUSED, _ok())
    outcome = await _extractor(fetcher).extract_claims(
        "Massive lithium reserves discovered in Antarctica"
    )
    assert fetcher.calls == 2
    assert outcome.succeeded


async def test_a_refusal_that_persists_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.extraction.llm.asyncio.sleep", _no_wait)
    fetcher = _Fetcher(_REFUSED)
    outcome = await _extractor(fetcher).extract_claims(
        "Massive lithium reserves discovered in Antarctica"
    )
    assert not outcome.succeeded
    assert "content_filter" in (outcome.reason or "")


async def _no_wait(_: float) -> None:
    return None


@pytest.mark.parametrize(
    ("reason", "again"),
    [
        ("provider returned 400 (content_filter: x)", True),
        ("provider returned 503", True),
        ("request timed out", True),
        ("provider returned 401", False),
        ("provider returned 429", False),
        ("blocked destination", False),
    ],
)
def test_which_failures_are_worth_another_try(reason: str, again: bool) -> None:
    assert _worth_another_try(reason) is again


def test_the_providers_own_error_is_kept_briefly() -> None:
    body = json.dumps({"error": {"code": "content_filter", "message": "The response was filtered"}})
    assert _provider_error(body.encode()) == " (content_filter: The response was filtered)"
    assert _provider_error(b"<html>busy</html>") == ""
