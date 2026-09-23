"""OCR (M18).

Screenshots are the dominant Indian format, and the text inside one is usually the
whole claim. This is therefore not a side path — for a large share of real traffic it
is the only path to any claim at all.

Two rules shape the interface.

**Raw extraction and detected language are preserved before any normalisation.** The
original characters are what a claim anchor points at; normalising first would leave
offsets pointing into text that no longer exists.

**Nothing is translated silently.** Detection is a separate, recorded step, so a Hindi
screenshot is known to be Hindi rather than quietly becoming English on the way
through.

When no model is configured this returns nothing and the case proceeds on whatever
other evidence exists. There is no fallback that produces approximate text.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass

from app.extraction.language import Detection, detect
from app.governor.governor import Governor, ProviderUnavailable
from app.observability.logging import event
from app.security.fetcher import FetchResult, SecureFetcher

logger = logging.getLogger("factify.ocr")

PROVIDER = "llm"

_INSTRUCTION = (
    "Transcribe all text visible in this image exactly as it appears. Preserve the "
    "original script and wording. Do not translate, summarise, correct or explain. "
    "Return only the transcribed text. If there is no text, return an empty string."
)


@dataclass(frozen=True, slots=True)
class OcrRegion:
    """A block of transcribed text and where it sits in the image.

    Anchors are approximate by nature — this is the region of a screenshot a claim
    came from, not a character offset in a document — but a claim that can point at
    the top third of an image is still far more auditable than one that cannot point
    anywhere.
    """

    text: str
    index: int


@dataclass(frozen=True, slots=True)
class OcrOutcome:
    """Transcribed text, its language, or the reason there is none."""

    text: str = ""
    language: Detection | None = None
    regions: tuple[OcrRegion, ...] = ()
    model_id: str | None = None
    reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.reason is None

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


class OcrExtractor:
    """Transcription over a governed model call."""

    def __init__(
        self,
        *,
        fetcher: SecureFetcher,
        governor: Governor,
        endpoint: str,
        api_key: str,
        model_id: str,
    ) -> None:
        self._fetcher = fetcher
        self._governor = governor
        self._endpoint = endpoint
        self._api_key = api_key
        self._model_id = model_id

    async def transcribe(self, image: bytes, *, mime_type: str = "image/jpeg") -> OcrOutcome:
        try:
            await self._governor.acquire(PROVIDER)
        except ProviderUnavailable as unavailable:
            return OcrOutcome(reason=f"unavailable: {unavailable.reason.value}")

        response = await self._fetcher.post_json(
            self._endpoint.format(model=self._model_id),
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": _INSTRUCTION},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": base64.b64encode(image).decode("ascii"),
                                }
                            },
                        ],
                    }
                ],
                "generationConfig": {"temperature": 0.0},
            },
            provider=PROVIDER,
            headers={"x-goog-api-key": self._api_key},
        )

        if not isinstance(response, FetchResult):
            return OcrOutcome(reason=f"provider failed: {response.reason}")

        try:
            envelope = json.loads(response.text)
            text = envelope["candidates"][0]["content"]["parts"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            return OcrOutcome(reason=f"unreadable provider response: {type(exc).__name__}")

        # Transcribed text is external text: it came from an image an attacker chose,
        # so it carries exactly the same trust level as a fetched page and is fenced
        # by the caller before it reaches any further model call.
        language = detect(text)

        event(
            logger,
            "image transcribed",
            module="extraction.ocr",
            outcome="ok",
            provider=PROVIDER,
            model_id=self._model_id,
            character_count=len(text),
            language=str(language.language),
        )

        regions = tuple(
            OcrRegion(text=block.strip(), index=index)
            for index, block in enumerate(text.split("\n\n"))
            if block.strip()
        )

        return OcrOutcome(text=text, language=language, regions=regions, model_id=self._model_id)


class UnavailableOcr:
    """Used when no model is configured. Returns nothing rather than approximating."""

    async def transcribe(self, image: bytes, *, mime_type: str = "image/jpeg") -> OcrOutcome:
        del image, mime_type
        return OcrOutcome(reason="unavailable: no model configured")
