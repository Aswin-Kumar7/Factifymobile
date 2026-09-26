"""A PDF whose Hindi came out scrambled is read the way a person sees it.

A typed Hindi PDF - a printed web page, a government circular - can store its glyphs
in the order they are drawn, and that is the order pypdf reads back: "विज्ञान" came
out as "िव ान". Every claim taken from such text was thrown away as not found in the
document, and a true Hindi PDF about Aditya-L1 came back "Unconfirmed" with nothing
checked.
"""

from __future__ import annotations

import base64
import io
from typing import Any
from uuid import UUID

import httpx
import pytest
from pypdf import PdfReader, PdfWriter

from app.extraction.claims import ExtractedClaims
from app.extraction.language import detect
from app.extraction.model_wire import PDF_MIME, WireFormat, build_call
from app.extraction.ocr import OcrOutcome
from app.extraction.pdf import ExtractedPdf, PdfPage, broken_script, first_pages
from tests.unit.factories import claim
from tests.unit.test_image_reading import _text_pdf
from tests.unit.test_orchestration import _result

# What pypdf read out of the Aditya-L1 PDF, exactly.
SCRAMBLED = (
    "िव ान  समाचार\n"
    "इसरो  ने  आिदत्य -L1 िमशन  लॉन्च  िकया\n"
    "भारतीय  अंत रक्ष  अनुसंधान  संगठन  ( इसरो ) ने  2 िसतंबर  2023 को   ीह रकोटा  से  सूय   का  "
    "अध्ययन  करने  के  िलए  भारत  का\n"
    "पहला  सौर  िमशन  आिदत्य -L1 लॉन्च  िकया।"
)
# What the page says.
CLEAN = (
    "भारतीय अंतरिक्ष अनुसंधान संगठन (इसरो) ने 2 सितंबर 2023 को श्रीहरिकोटा से सूर्य का "
    "अध्ययन करने के लिए भारत का पहला सौर मिशन आदित्य-L1 लॉन्च किया।"
)


class TestScrambledHindiIsRecognised:
    def test_a_text_layer_in_drawing_order_is_broken(self) -> None:
        assert broken_script(SCRAMBLED)

    def test_hindi_as_written_is_not(self) -> None:
        assert not broken_script(CLEAN)

    def test_english_is_not(self) -> None:
        assert not broken_script("The G20 adopted the New Delhi declaration on 9 September 2023.")

    def test_one_stray_sign_in_a_long_text_is_not_enough(self) -> None:
        assert not broken_script(f"{CLEAN} {CLEAN} ि")


class TestThePagesTravelAsADocument:
    def test_openai_gets_the_pdf_as_a_file(self) -> None:
        _, _, body = build_call(
            fmt=WireFormat.OPENAI,
            endpoint="https://example.invalid",
            model_id="m",
            api_key="k",
            system="read it",
            user_block="Read this image.",
            response_schema={"type": "object"},
            image=(b"%PDF-1.4 data", PDF_MIME),
        )

        part = body["messages"][1]["content"][1]
        assert part["type"] == "file"
        assert part["file"]["file_data"] == (
            "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 data").decode()
        )

    def test_only_the_first_pages_are_sent(self) -> None:
        writer = PdfWriter()
        for _ in range(5):
            writer.add_blank_page(width=200, height=200)
        buffer = io.BytesIO()
        writer.write(buffer)
        five = buffer.getvalue()

        assert len(PdfReader(io.BytesIO(first_pages(five, 3))).pages) == 3
        assert first_pages(five, 10) == five


class TestAScrambledHindiPdfIsReadAsADocument:
    @pytest.mark.anyio
    async def test_the_pages_are_read_and_that_reading_is_checked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.main import create_app

        sent: list[str] = []
        extracted: list[str] = []

        class _Reader:
            async def transcribe(self, data: bytes, *, mime_type: str = "") -> OcrOutcome:
                sent.append(mime_type)
                return OcrOutcome(text=CLEAN, language=detect(CLEAN), kind="DOCUMENT")

        class _Pipeline:
            async def extract(self, text: str, **_: Any) -> ExtractedClaims:
                extracted.append(text)
                return ExtractedClaims(claims=(claim(),))

        class _Orchestrator:
            async def cached(self, intake: Any, *, case_id: UUID) -> Any:
                return None

            async def verify(self, intake: Any, *, case_id: UUID, **_: Any) -> Any:
                return _result(case_id=case_id)

        page = PdfPage(number=1, text=SCRAMBLED, char_start=0, char_end=len(SCRAMBLED))
        monkeypatch.setattr(
            "app.api.verify.extract_pdf",
            lambda data: ExtractedPdf(text=SCRAMBLED, pages=(page,), page_count=1),
        )
        app = create_app()
        app.state.ocr = _Reader()
        app.state.claim_pipeline = _Pipeline()
        app.state.orchestrator = _Orchestrator()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
            response = await api.post(
                "/v1/verify/file",
                files={"file": ("aditya.pdf", _text_pdf("Aditya-L1"), "application/pdf")},
                data={"consent_to_process_media": "true"},
            )

        assert response.status_code == 200
        assert sent == [PDF_MIME]
        assert extracted == [CLEAN]
        assert response.json()["image_reading"]["text"] == CLEAN
