"""Reading an uploaded image: its text, and what it shows, then checking the text.

An uploaded screenshot used to be fingerprinted and checked for nothing: a forward
announcing a ban on ₹500 notes came back "Unconfirmed" without a word of it read.
These tests hold the three halves of the fix - the picture travels to the model in
the provider's own shape, the reading is parsed and bounded, and the text becomes
claims checked like a pasted message, with what was read shown in the response.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from PIL import Image

from app.extraction.claims import ExtractedClaims
from app.extraction.language import detect
from app.extraction.model_wire import WireFormat, build_call
from app.extraction.ocr import OcrExtractor, OcrOutcome
from app.security.fetcher import FetchFailure, FetchResult
from tests.unit.factories import claim
from tests.unit.test_orchestration import _result

pytestmark = pytest.mark.unit

FORWARD = (
    "*BREAKING NEWS*\nRBI has announced that all Rs 500 notes will be banned from 1 October 2026."
)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class TestTheImageTravelsInTheProvidersShape:
    def _call(self, fmt: WireFormat) -> dict[str, Any]:
        _, _, body = build_call(
            fmt=fmt,
            endpoint="https://example.invalid/{model}",
            model_id="m",
            api_key="k",
            system="read it",
            user_block="Read this image.",
            response_schema={"type": "object"},
            image=(b"\x89PNGdata", "image/png"),
        )
        return body

    def test_openai_gets_a_data_url_beside_the_text(self) -> None:
        user = self._call(WireFormat.OPENAI)["messages"][1]["content"]

        assert user[0] == {"type": "text", "text": "Read this image."}
        url = user[1]["image_url"]["url"]
        assert url == "data:image/png;base64," + base64.b64encode(b"\x89PNGdata").decode()
        assert user[1]["image_url"]["detail"] == "high"

    def test_gemini_gets_an_inline_part(self) -> None:
        parts = self._call(WireFormat.GEMINI)["contents"][0]["parts"]

        assert parts[1]["inlineData"]["mimeType"] == "image/png"
        assert base64.b64decode(parts[1]["inlineData"]["data"]) == b"\x89PNGdata"

    def test_a_call_without_an_image_is_unchanged(self) -> None:
        _, _, body = build_call(
            fmt=WireFormat.OPENAI,
            endpoint="https://example.invalid",
            model_id="m",
            api_key="k",
            system="s",
            user_block="text only",
            response_schema={"type": "object"},
        )

        assert body["messages"][1]["content"] == "text only"


class _Fetcher:
    def __init__(self, answer: dict[str, Any] | None, status: int = 200) -> None:
        self.answer = answer
        self.status = status
        self.sent: list[dict[str, Any]] = []

    async def post_json(self, url: str, body: dict[str, Any], **_: Any) -> Any:
        self.sent.append(body)
        if self.answer is None:
            return FetchFailure(url=url, reason="transport error: ConnectError", kind="network")
        envelope = {"choices": [{"message": {"content": json.dumps(self.answer)}}]}
        body = json.dumps(envelope).encode()
        return FetchResult(
            url=url,
            final_url=url,
            status_code=self.status,
            content_type="application/json",
            body=body,
            byte_count=len(body),
            fetched_at=datetime.now(UTC),
        )


class _Governor:
    async def acquire(self, provider: str) -> object:
        return object()


def _reader(fetcher: _Fetcher) -> OcrExtractor:
    return OcrExtractor(
        fetcher=fetcher,  # type: ignore[arg-type]
        governor=_Governor(),
        endpoint="https://example.invalid/chat/completions",
        api_key="k",
        model_id="gpt-4.1-mini",
        api_format=WireFormat.OPENAI,
    )


class TestTheReading:
    @pytest.mark.anyio
    async def test_the_text_and_what_the_image_shows_come_back(self) -> None:
        fetcher = _Fetcher(
            {
                "text": FORWARD,
                "description": "A WhatsApp forward in a group called  Family Group.",
                "kind": "chat_message",
                "publisher": "",
            }
        )

        outcome = await _reader(fetcher).transcribe(_png(), mime_type="image/png")

        assert outcome.succeeded and outcome.has_text
        assert outcome.text == FORWARD
        assert outcome.description == "A WhatsApp forward in a group called Family Group."
        assert outcome.kind == "CHAT_MESSAGE"
        assert outcome.language is not None and outcome.language.language.value == "en"

    @pytest.mark.anyio
    async def test_an_unknown_kind_is_other(self) -> None:
        fetcher = _Fetcher({"text": "", "description": "x", "kind": "SELFIE", "publisher": ""})

        outcome = await _reader(fetcher).transcribe(_png())

        assert outcome.kind == "OTHER"
        assert not outcome.has_text

    @pytest.mark.anyio
    async def test_a_provider_failure_is_a_reason_not_a_guess(self) -> None:
        outcome = await _reader(_Fetcher(None)).transcribe(_png())

        assert not outcome.succeeded
        assert outcome.text == ""

    @pytest.mark.anyio
    async def test_a_provider_error_status_is_a_reason(self) -> None:
        outcome = await _reader(_Fetcher({"text": "x"}, status=429)).transcribe(_png())

        assert outcome.reason == "provider returned 429"


class TestAnUploadedImageIsReadAndChecked:
    def _app(
        self, reading: OcrOutcome, *, cached: bool = False
    ) -> tuple[Any, dict[str, list[Any]]]:
        from app.main import create_app

        seen: dict[str, list[Any]] = {"extracted": [], "claims": []}

        class _Reader:
            async def transcribe(self, image: bytes, *, mime_type: str = "") -> OcrOutcome:
                return reading

        class _Pipeline:
            async def extract(self, text: str, **kwargs: Any) -> ExtractedClaims:
                seen["extracted"].append((text, kwargs))
                return ExtractedClaims(claims=(claim(text="RBI bans Rs 500 notes."),))

        class _Orchestrator:
            async def cached(self, intake: Any, *, case_id: UUID) -> Any:
                return _result(case_id=case_id) if cached else None

            async def verify(self, intake: Any, *, case_id: UUID, claims: Any, **_: Any) -> Any:
                seen["claims"].append(list(claims))
                return _result(case_id=case_id)

        app = create_app()
        app.state.ocr = _Reader()
        app.state.claim_pipeline = _Pipeline()
        app.state.orchestrator = _Orchestrator()
        return app, seen

    async def _upload(self, app: Any) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
            return await api.post(
                "/v1/verify/file",
                files={"file": ("forward.png", _png(), "image/png")},
                data={"consent_to_process_media": "true"},
            )

    @pytest.mark.anyio
    async def test_the_text_becomes_claims_and_the_reading_is_shown(self) -> None:
        reading = OcrOutcome(
            text=FORWARD,
            language=detect(FORWARD),
            description="A WhatsApp forward.",
            kind="CHAT_MESSAGE",
        )
        app, seen = self._app(reading)

        response = await self._upload(app)

        assert response.status_code == 200
        text, kwargs = seen["extracted"][0]
        assert text == FORWARD
        assert kwargs["input_kind"] == "image"
        assert [c.text for c in seen["claims"][0]] == ["RBI bans Rs 500 notes."]
        shown = response.json()["image_reading"]
        assert shown["text"] == FORWARD
        assert shown["description"] == "A WhatsApp forward."
        assert shown["kind"] == "CHAT_MESSAGE"
        assert shown["language"] == "en"

    @pytest.mark.anyio
    async def test_a_repeat_from_the_cache_still_shows_what_was_read(self) -> None:
        reading = OcrOutcome(text=FORWARD, language=detect(FORWARD), kind="CHAT_MESSAGE")
        app, _ = self._app(reading)
        await self._upload(app)

        app.state.orchestrator.cached = lambda intake, case_id: _cached(case_id)  # type: ignore[method-assign]
        repeat = await self._upload(app)

        assert repeat.json()["image_reading"]["text"] == FORWARD

    @pytest.mark.anyio
    async def test_an_image_that_cannot_be_read_says_so_and_checks_the_picture(self) -> None:
        app, seen = self._app(OcrOutcome(reason="provider failed: timeout"))

        response = await self._upload(app)

        assert response.status_code == 200
        assert seen["extracted"] == []
        assert seen["claims"] == [[]]  # the picture's own questions, as before
        skipped = {item["check"]: item["reason"] for item in response.json()["skipped"]}
        assert "could not be read" in skipped["image_text"]
        assert response.json()["image_reading"] is None

    @pytest.mark.anyio
    async def test_a_picture_with_no_text_is_checked_as_a_picture(self) -> None:
        reading = OcrOutcome(text="", description="A flooded street.", kind="PHOTO")
        app, seen = self._app(reading)

        response = await self._upload(app)

        assert seen["extracted"] == []
        assert seen["claims"] == [[]]
        assert response.json()["image_reading"]["description"] == "A flooded street."


async def _cached(case_id: UUID) -> Any:
    return _result(case_id=case_id)


def _text_pdf(line: str) -> bytes:
    """A one-page PDF with a real text layer, written out by hand."""
    stream = f"BT /F1 12 Tf 40 700 Td ({line}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


class TestAnUploadedPdfIsReadAndChecked:
    """A forged circular arrives as a PDF, and its text was never read either."""

    @pytest.mark.anyio
    async def test_its_text_layer_becomes_claims(self) -> None:
        from app.main import create_app

        seen: list[tuple[str, dict[str, Any]]] = []

        class _Pipeline:
            async def extract(self, text: str, **kwargs: Any) -> ExtractedClaims:
                seen.append((text, kwargs))
                return ExtractedClaims(claims=(claim(),))

        class _Orchestrator:
            async def cached(self, intake: Any, *, case_id: UUID) -> Any:
                return None

            async def verify(self, intake: Any, *, case_id: UUID, claims: Any, **_: Any) -> Any:
                return _result(case_id=case_id)

        app = create_app()
        app.state.claim_pipeline = _Pipeline()
        app.state.orchestrator = _Orchestrator()
        circular = "Government announces free laptops for all college students from October 2026"

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
            response = await api.post(
                "/v1/verify/file",
                files={"file": ("circular.pdf", _text_pdf(circular), "application/pdf")},
                data={"consent_to_process_media": "true"},
            )

        assert response.status_code == 200
        text, kwargs = seen[0]
        assert circular in text
        assert kwargs["input_kind"] == "pdf"
        assert response.json()["image_reading"] is None
