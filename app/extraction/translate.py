"""Translation for the ten Indian languages beyond English and Hindi.

What it is for: finding sources, not writing answers. A Tamil forward is searched in
Tamil and, translated, in English - where PIB Fact Check, BOOM, Factly and the
national press mostly publish - and compared with English fact-checks and corpus
articles in English. The words shown to a person are never machine-translated: an
explanation is a template written for their language, and a cited sentence stays in
the words its page used.

Google Translate, two ways (FACTIFY_TRANSLATION):
  - `google_free`: the endpoint Google's own web widgets call. No key and no bill,
    and not a documented API: its terms do not cover this use, and it can be
    rate-limited or refused without notice. Chosen for now by the product owner
    (2026-09-28), knowing that.
  - `google_cloud`: the official Cloud Translation API (v2), free for the first
    500,000 characters a month once billing is on; FACTIFY_TRANSLATION_KEY.

Either way a translation is a help, never a dependency: a refusal, a timeout or the
rate limit returns None, and the check goes on in the claim's own language. Text
sent here is the claim, the same text already sent to the search provider; it is
logged by length and language only.
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from app.observability.logging import event
from app.security.fetcher import FetchResult

logger = logging.getLogger("factify.extraction.translate")

PROVIDER = "translate"
FREE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
CLOUD_ENDPOINT = "https://translation.googleapis.com/language/translate/v2"

# The endpoint takes the text in the URL; a claim is far shorter than this.
MOST_CHARACTERS = 1800


@dataclass(frozen=True, slots=True)
class Translation:
    text: str
    source: str  # the language Google detected, e.g. "ta"


class GoogleTranslator:
    """Google Translate with a small memory and a per-minute ceiling."""

    def __init__(
        self,
        *,
        fetcher: Any,
        api_key: str | None = None,
        per_minute: int = 60,
        remember: int = 2000,
    ) -> None:
        self._fetcher = fetcher
        self._api_key = api_key
        self._per_minute = per_minute
        self._calls: list[float] = []
        self._memory: OrderedDict[tuple[str, str, str], Translation] = OrderedDict()
        self._remember = remember

    async def translate(
        self, text: str, *, target: str = "en", source: str = "auto"
    ) -> Translation | None:
        text = " ".join(text.split())[:MOST_CHARACTERS]
        if not text:
            return None
        key = (source, target, text)
        if key in self._memory:
            self._memory.move_to_end(key)
            return self._memory[key]
        if not self._allowed():
            event(
                logger,
                "translation skipped",
                module="extraction.translate",
                outcome="skipped",
                provider=PROVIDER,
                failure_reason="per-minute limit",
            )
            return None

        started = time.perf_counter()
        try:
            translated = await (
                self._cloud(text, target, source)
                if self._api_key
                else self._free(text, target, source)
            )
        except Exception:
            logger.exception("translation failed; the check goes on untranslated")
            translated = None
        event(
            logger,
            "text translated",
            module="extraction.translate",
            outcome="ok" if translated else "degraded",
            provider=PROVIDER,
            model_id="google_cloud" if self._api_key else "google_free",
            latency_ms=round((time.perf_counter() - started) * 1000),
            characters=len(text),
            source=translated.source if translated else source,
            target=target,
        )
        if translated is not None:
            self._memory[key] = translated
            while len(self._memory) > self._remember:
                self._memory.popitem(last=False)
        return translated

    def _allowed(self) -> bool:
        now = time.monotonic()
        self._calls = [t for t in self._calls if now - t < 60]
        if len(self._calls) >= self._per_minute:
            return False
        self._calls.append(now)
        return True

    async def _free(self, text: str, target: str, source: str) -> Translation | None:
        query = urlencode({"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text})
        result = await self._fetcher.fetch(f"{FREE_ENDPOINT}?{query}", provider=PROVIDER)
        if not isinstance(result, FetchResult) or result.status_code != 200:
            return None
        return parse_free(result.text)

    async def _cloud(self, text: str, target: str, source: str) -> Translation | None:
        payload: dict[str, Any] = {"q": text, "target": target, "format": "text"}
        if source != "auto":
            payload["source"] = source
        result = await self._fetcher.post_json(
            f"{CLOUD_ENDPOINT}?{urlencode({'key': self._api_key})}", payload, provider=PROVIDER
        )
        if not isinstance(result, FetchResult) or result.status_code != 200:
            return None
        try:
            item = json.loads(result.text)["data"]["translations"][0]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            return None
        return Translation(
            text=str(item["translatedText"]),
            source=str(item.get("detectedSourceLanguage") or source),
        )


def parse_free(body: str) -> Translation | None:
    """The free endpoint's answer: [[[translated, original, ...], ...], null, "ta", ...]."""
    try:
        data = json.loads(body)
        text = "".join(str(segment[0]) for segment in data[0] if segment and segment[0])
        source = str(data[2]) if len(data) > 2 and data[2] else "auto"
    except (json.JSONDecodeError, TypeError, IndexError):
        return None
    return Translation(text=text.strip(), source=source) if text.strip() else None
