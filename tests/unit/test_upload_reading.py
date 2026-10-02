"""Reading an uploaded picture or video in full, and what is checked from it (2026-10-03).

An audit of 45 real inputs found uploads read thinly: one frame of a video's first 90
seconds, never the end card that carried its claim; a picture's description asked for
only when our own reader could not read its words, and never checked; the AI-picture
detector's "likely AI-made" shown on genuine government graphics. These hold the
fixes, with every reader and model stood in for:

  - a video's speech, the words shown across all of it and one description of a
    contact sheet of its frames are checked together, each under Factify's own label;
  - what could not be read is said, as a reading gap, and nothing more is claimed;
  - the AI-picture detector is not shown or counted on a designed graphic, a document
    or a screenshot, nor counted for a video on one model's word.
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from PIL import Image

from app.api.schemas import (
    CredentialsResponse,
    DetectorResponse,
    EditingResponse,
    HistoryResponse,
    MediaReportResponse,
)
from app.extraction.claims import ExtractedClaims
from app.extraction.language import detect
from app.extraction.local_ocr import LocalFirstOcr, LocalReading, OcrLine
from app.extraction.ocr import READER_VERSION, OcrOutcome, looks_designed
from app.intake.normalizer import normalise_upload
from app.media.discovery import DiscoveryResult
from app.media.forensics import ForensicPanel
from app.media.provenance import ProvenanceReport
from app.media.report import MediaReport
from app.media.speech import SpeechOutcome, Transcript
from app.media.synthetic import SyntheticReading
from app.media.video import ffmpeg_available
from tests.unit.factories import claim
from tests.unit.test_frame_text import _clip, _second_of
from tests.unit.test_orchestration import _result

pytestmark = pytest.mark.unit

requires_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg is not installed")


# ------------------------------------------------------------------ a whole video


class _FrameWords:
    """Our own text reader, stood in for: a card that reads "REPO RATE UNCHANGED"
    from the tenth second of the clip to its end, and the channel's name throughout."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    def read(self, data: bytes) -> LocalReading:
        second = _second_of(data)
        self.seconds.append(second)
        lines = [OcrLine(text="NDTV Profit", confidence=0.97, top=0, left=0, bottom=10, right=60)]
        if second >= 10:
            lines.append(
                OcrLine(
                    text="REPO RATE UNCHANGED AT 5.25%",
                    confidence=0.99,
                    top=40,
                    left=0,
                    bottom=60,
                    right=150,
                )
            )
        return LocalReading(lines=tuple(lines), elapsed_ms=1.0)


class _Describer:
    """The hosted reader, stood in for: it is asked once, about a contact sheet."""

    def __init__(self, outcome: OcrOutcome | None = None) -> None:
        self.sheets: list[tuple[bytes, int, str]] = []
        self.outcome = outcome or OcrOutcome(
            description=(
                "A TV business news broadcast. A man who appears to be Sanjay Malhotra "
                "speaks at a podium; at 0:11 a full-screen card about the repo rate."
            ),
            kind="TV_GRAPHIC",
            publisher="NDTV Profit",
            model_id="hosted",
        )

    async def describe_video(self, sheet: bytes, *, frames: int, span: str) -> OcrOutcome:
        self.sheets.append((sheet, frames, span))
        return self.outcome

    async def transcribe(self, image: bytes, *, mime_type: str = "") -> OcrOutcome:
        raise AssertionError("a video is described once, never read frame by frame")


class _Ears:
    def __init__(self, outcome: SpeechOutcome) -> None:
        self.outcome = outcome
        self.windows: list[float] = []

    def read_video_outcome(self, _video: bytes, *, max_seconds: float) -> SpeechOutcome:
        self.windows.append(max_seconds)
        return self.outcome


SAID = "The Monetary Policy Committee decided to keep the policy rate unchanged."


def _heard(text: str = SAID, seconds: float = 14.0) -> SpeechOutcome:
    return SpeechOutcome(
        status="read",
        transcript=Transcript(
            text=text,
            language="en",
            language_confidence=0.98,
            seconds_read=2.0,
            audio_seconds=seconds,
        ),
        audio_seconds=seconds,
    )


class _Checker:
    """The claim extraction and the orchestrator, stood in for."""

    def __init__(self) -> None:
        self.documents: list[tuple[str, dict[str, Any]]] = []
        self.probed: list[Any] = []
        self.verified: list[dict[str, Any]] = []

    async def extract(self, text: str, **kwargs: Any) -> ExtractedClaims:
        self.documents.append((text, kwargs))
        return ExtractedClaims(claims=(claim(text="RBI kept the repo rate at 5.25%."),))

    async def cached(self, intake: Any, *, case_id: UUID) -> Any:
        self.probed.append(intake)
        return None

    async def verify(self, intake: Any, *, case_id: UUID, claims: Any, **kwargs: Any) -> Any:
        self.verified.append({"intake": intake, "claims": list(claims), **kwargs})
        return _result(case_id=case_id)


def _request(
    *, speech: SpeechOutcome, describer: _Describer | None, words: _FrameWords | None
) -> tuple[Any, _Checker, _Ears]:
    checker = _Checker()
    ears = _Ears(speech)
    state = SimpleNamespace(
        settings=SimpleNamespace(
            limits=SimpleNamespace(max_upload_bytes=50_000_000),
            social=SimpleNamespace(max_video_seconds=600),
        ),
        ocr=(
            LocalFirstOcr(local=words, hosted=describer)  # type: ignore[arg-type]
            if words is not None
            else describer
        ),
        speech_reader=ears,
        claim_pipeline=checker,
        orchestrator=checker,
        media_inspector=None,
    )
    return SimpleNamespace(app=SimpleNamespace(state=state)), checker, ears


def _video(tmp_path: Any, seconds: int = 14) -> tuple[Any, bytes]:
    data = _clip(tmp_path / "clip.mp4", seconds=seconds, cuts=False)
    intake = normalise_upload(data, max_bytes=50_000_000, declared_type="video/mp4", consent=True)
    return intake, data


@requires_ffmpeg
class TestAVideoIsReadWhole:
    async def test_speech_words_shown_and_what_it_shows_are_checked_together(
        self, tmp_path: Any
    ) -> None:
        from app.api.verify import _checked_video

        intake, data = _video(tmp_path)
        words, describer = _FrameWords(), _Describer()
        request, checker, ears = _request(speech=_heard(), describer=describer, words=words)

        response = await _checked_video(request, intake, data, case_id=uuid4(), recheck=False)

        [(document, kwargs)] = checker.documents
        spoken = document.index("Spoken in the video:\n" + SAID)
        shown = document.index("Text shown in the video:\nNDTV Profit\nREPO RATE UNCHANGED")
        seen = document.index("What the video shows (described by Factify):\nA TV business")
        assert spoken < shown < seen
        assert kwargs["language"] == "en"
        # The end of the clip was read, not only its opening seconds.
        assert max(words.seconds) > 12.5
        assert min(words.seconds) < 1.5
        # One description, of one sheet of frames, for the whole video.
        [(sheet, frames, span)] = describer.sheets
        assert 2 <= frames <= 9 and span == "0:00-0:14"
        with Image.open(io.BytesIO(sheet)) as picture:
            assert picture.format == "JPEG"
        # The whole clip heard, up to the background window.
        assert ears.windows == [600]

        body = response.model_dump()
        assert body["speech"]["text"] == SAID
        assert body["image_reading"]["text"].startswith("NDTV Profit")
        assert body["image_reading"]["publisher"] == "NDTV Profit"
        read = body["input_read"]
        assert read["kind"] == "video" and read["complete"]
        assert [part["kind"] for part in read["parts"]] == [
            "transcript",
            "on_screen_text",
            "video_description",
        ]
        assert all(part["checked"] for part in read["parts"])
        for part in read["parts"]:
            assert document[part["char_start"] : part["char_end"]] == part["text"]
        [note] = [item for item in body["skipped"] if item["check"] == "video_frames"]
        assert "read the words on" in note["reason"] and "to 0:13 of 0:14" in note["reason"]
        assert "listened to all 0:14 of it for speech" in note["reason"]

    async def test_it_is_kept_under_the_videos_identity_and_the_readers_version(
        self, tmp_path: Any
    ) -> None:
        from app.api.verify import _checked_video

        intake, data = _video(tmp_path)
        request, checker, _ = _request(speech=_heard(), describer=_Describer(), words=_FrameWords())

        await _checked_video(request, intake, data, case_id=uuid4(), recheck=False)

        [probed] = checker.probed
        assert probed.cache_identity == f"{intake.cache_identity}|reader:{READER_VERSION}"
        assert checker.verified[0]["intake"].cache_identity == probed.cache_identity
        assert checker.verified[0]["fresh"] is False

    async def test_speech_that_could_not_be_read_is_said_and_the_rest_is_checked(
        self, tmp_path: Any
    ) -> None:
        from app.api.verify import _checked_video

        intake, data = _video(tmp_path)
        failed = SpeechOutcome(status="failed", reason="decoding the sound took longer than 60s")
        request, checker, _ = _request(speech=failed, describer=_Describer(), words=_FrameWords())

        response = await _checked_video(request, intake, data, case_id=uuid4(), recheck=False)

        [(document, _)] = checker.documents
        assert "Spoken in the video" not in document
        assert "REPO RATE UNCHANGED" in document
        body = response.model_dump()
        [gap] = body["input_read"]["gaps"]
        assert (gap["code"], gap["part"], gap["blocking"]) == (
            "speech_unread",
            "transcript",
            True,
        )
        speech = {item["check"]: item for item in body["skipped"]}["speech"]
        assert speech["kind"] == "reading"
        assert "took longer than 60s" in speech["reason"]
        # Reported to the pipeline, which keeps the run out of the cache.
        assert [item.check for item in checker.verified[0]["noted"]] == ["speech"]

    async def test_a_video_longer_than_the_window_says_how_much_was_read(
        self, tmp_path: Any
    ) -> None:
        from app.api.verify import _checked_video

        intake, data = _video(tmp_path, seconds=20)
        request, _, _ = _request(
            speech=_heard(seconds=12.0), describer=_Describer(), words=_FrameWords()
        )
        request.app.state.settings.social.max_video_seconds = 12

        response = await _checked_video(request, intake, data, case_id=uuid4(), recheck=False)

        body = response.model_dump()
        gaps = {gap["part"]: gap for gap in body["input_read"]["gaps"]}
        assert gaps["video"]["code"] == "cut_off"
        assert "first 0:12 of the video's 0:20" in gaps["video"]["detail"]
        [note] = [item for item in body["skipped"] if item["check"] == "video_frames"]
        assert "nothing after 0:12 was read" in note["reason"]

    async def test_without_our_own_text_reader_the_unread_words_are_said(
        self, tmp_path: Any
    ) -> None:
        from app.api.verify import _checked_video

        intake, data = _video(tmp_path)
        request, checker, _ = _request(speech=_heard(), describer=_Describer(), words=None)

        response = await _checked_video(request, intake, data, case_id=uuid4(), recheck=False)

        [(document, _)] = checker.documents
        assert "Text shown in the video" not in document
        assert "Spoken in the video" in document and "described by Factify" in document
        body = response.model_dump()
        [gap] = body["input_read"]["gaps"]
        assert (gap["code"], gap["part"]) == ("reader_unavailable", "on_screen_text")
        [note] = [item for item in body["skipped"] if item["check"] == "video_frames"]
        assert "could not read their words" in note["reason"]

    async def test_without_a_hosted_reader_the_words_and_speech_are_still_checked(
        self, tmp_path: Any
    ) -> None:
        from app.api.verify import _checked_video

        intake, data = _video(tmp_path)
        request, checker, _ = _request(speech=_heard(), describer=None, words=_FrameWords())
        request.app.state.ocr = LocalFirstOcr(local=_FrameWords(), hosted=None)  # type: ignore[arg-type]

        response = await _checked_video(request, intake, data, case_id=uuid4(), recheck=False)

        [(document, _)] = checker.documents
        assert "described by Factify" not in document
        assert "REPO RATE UNCHANGED" in document
        [note] = [item for item in response.skipped if item.check == "video_frames"]
        assert "could not describe what it shows" in note.reason


# ------------------------------------------------------------------ AI on graphics


def _report(
    *,
    kind: str = "image",
    agreement: str | None = "likely_ai",
    second: float | None = None,
    declares_ai: bool = False,
    face_swapped: bool | None = None,
    machine_voice: bool | None = None,
) -> MediaReportResponse:
    return MediaReportResponse(
        kind=kind,
        credentials=CredentialsResponse(status="none", declares_ai=declares_ai),
        history=HistoryResponse(status="not_checked", why="off"),
        detector=DetectorResponse(
            status="checked",
            generated=0.99,
            second_opinion=second,
            agreement=agreement,
            face_swapped=face_swapped,
            machine_voice=machine_voice,
            on_server=True,
        ),
        editing=EditingResponse(status="checked"),
    )


class TestWhatCountsAsAiMade:
    def test_a_photograph_the_detectors_agree_on_counts(self) -> None:
        from app.api.verify import ai_made

        assert ai_made(_report())

    def test_a_designed_graphic_does_not_count_on_the_detectors_word(self) -> None:
        from app.api.verify import ai_made

        assert not ai_made(_report(), designed=True)
        assert not ai_made(_report(face_swapped=True), designed=True)
        # What the file itself says still counts.
        assert ai_made(_report(declares_ai=True), designed=True)

    def test_one_model_on_a_video_does_not_count(self) -> None:
        """Genuine UN footage of Netanyahu read 99.8% "generated" to the one picture
        model on the server (2026-10-02)."""
        from app.api.verify import ai_made

        assert not ai_made(_report(kind="video"))
        assert ai_made(_report(kind="video", second=0.8))
        assert ai_made(_report(kind="video", agreement="no_sign", machine_voice=True))
        assert ai_made(_report(kind="video", agreement="no_sign", face_swapped=True))


class TestWhatIsADesignedPicture:
    @pytest.mark.parametrize("kind", ["POSTER", "TV_GRAPHIC", "DOCUMENT", "CHAT_MESSAGE", "MEME"])
    def test_made_kinds_are_designed(self, kind: str) -> None:
        assert looks_designed(kind)

    @pytest.mark.parametrize("kind", ["PHOTO", "SOCIAL_POST", "NEWS_ARTICLE", "OTHER", None])
    def test_a_post_or_a_photo_is_judged_as_a_photograph(self, kind: str | None) -> None:
        assert not looks_designed(kind)
        assert not looks_designed(kind, 0.08)

    def test_a_picture_that_is_mostly_text_is_designed_whatever_it_was_called(self) -> None:
        assert looks_designed("SOCIAL_POST", 0.35)
        assert looks_designed(None, 0.2)


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 160, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


class _Inspector:
    """The picture checks, stood in for: the detector says likely AI-made."""

    async def inspect_image(self, data: bytes, *, mime: str = "") -> MediaReport:
        synthetic = SyntheticReading(generated=0.99, on_server=True, models=("cf",))
        return MediaReport(
            kind="image",
            credentials=ProvenanceReport(present=False, reason="no manifest"),
            history=DiscoveryResult(reason="unavailable: off"),
            synthetic=synthetic,
            editing=ForensicPanel(reason="not rendered"),
            advisories=synthetic.advisories(artifact_ref="upload"),
        )


class TestTheDetectorOnAPicture:
    async def _upload(self, reading: OcrOutcome) -> tuple[dict[str, Any], list[Any]]:
        from app.main import create_app

        asked: list[Any] = []

        class _Reader:
            async def transcribe(self, image: bytes, *, mime_type: str = "") -> OcrOutcome:
                return reading

        class _Orchestrator:
            async def cached(self, intake: Any, *, case_id: UUID) -> Any:
                return None

            async def verify(self, intake: Any, *, case_id: UUID, claims: Any, **kw: Any) -> Any:
                synthetic = kw.get("synthetic")
                asked.append(await synthetic() if synthetic is not None else None)
                return _result(case_id=case_id)

        app = create_app()
        app.state.ocr = _Reader()
        app.state.claim_pipeline = _Checker()
        app.state.orchestrator = _Orchestrator()
        app.state.media_inspector = _Inspector()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://factify.test") as api:
            response = await api.post(
                "/v1/verify/file",
                files={"file": ("card.png", _png(), "image/png")},
                data={"consent_to_process_media": "true"},
            )
        assert response.status_code == 200
        return response.json(), asked

    async def test_on_a_government_graphic_likely_ai_is_neither_shown_nor_counted(self) -> None:
        text = "EPF Wage Ceiling Revised to ₹25,000"
        body, asked = await self._upload(
            OcrOutcome(text=text, language=detect(text), kind="POSTER", description="A poster.")
        )

        detector = body["media_report"]["detector"]
        assert (detector["status"], detector["why"]) == ("not_checked", "text_card")
        assert detector["agreement"] is None and detector["generated"] is None
        assert not [item for item in body["advisories"] if item["provider"] == "ai_generation"]
        assert asked == [False]

    async def test_on_a_photograph_in_a_post_it_still_stands(self) -> None:
        text = "This pic says all! BRICS SUMMIT 2026"
        body, asked = await self._upload(
            OcrOutcome(
                text=text,
                language=detect(text),
                kind="SOCIAL_POST",
                description="A selfie of eight leaders.",
                text_area=0.06,
            )
        )

        assert body["media_report"]["detector"]["agreement"] == "likely_ai"
        [advisory] = [item for item in body["advisories"] if item["provider"] == "ai_generation"]
        assert advisory["signal"] == "ADVISORY_SUSPICION"
        assert asked == [True]


# ------------------------------------------------------------------ the picture reader


class TestWhatTheReaderIsAskedFor:
    def test_every_prompt_names_public_figures_and_notes_stamps_as_things_seen(self) -> None:
        from app.extraction.ocr import _DESCRIBE_INSTRUCTION, _INSTRUCTION, _VIDEO_INSTRUCTION

        for prompt in (_INSTRUCTION, _DESCRIBE_INSTRUCTION, _VIDEO_INSTRUCTION):
            assert '"appears to be <name>"' in prompt
            assert "never guess who a\n    private person is" in prompt
            assert "FAKE, FALSE or MISLEADING" in prompt
            assert "PIB Fact Check" in prompt
            assert "masthead" in prompt and "watermark" in prompt
            assert "generated or altered by AI" in prompt
            assert "Never say yourself whether anything in it is true" in prompt
        # Asked for its words only where they are wanted.
        assert "- text:" in _INSTRUCTION
        assert "- text:" not in _DESCRIBE_INSTRUCTION
        assert "- text:" not in _VIDEO_INSTRUCTION

    async def test_a_description_is_asked_for_alone_and_kept_short(self) -> None:
        from app.extraction.ocr import MAX_DESCRIBE_TOKENS
        from tests.unit.test_image_reading import _Fetcher, _reader

        fetcher = _Fetcher(
            {
                "description": "A poster from the Ministry of Labour with a man who "
                "appears to be Narendra Modi.",
                "kind": "poster",
                "publisher": "Ministry of Labour and Employment",
            }
        )

        outcome = await _reader(fetcher).describe(_png(), mime_type="image/png")

        assert outcome.succeeded and outcome.text == ""
        assert outcome.kind == "POSTER"
        assert outcome.publisher == "Ministry of Labour and Employment"
        assert "appears to be Narendra Modi" in outcome.description
        [sent] = fetcher.sent
        assert sent["max_tokens"] == MAX_DESCRIBE_TOKENS
        assert '"text"' not in sent["messages"][0]["content"].split("schema:")[-1]

    async def test_a_video_is_described_from_its_sheet_in_one_call(self) -> None:
        from tests.unit.test_image_reading import _Fetcher, _reader

        fetcher = _Fetcher(
            {"description": "A news broadcast.", "kind": "TV_GRAPHIC", "publisher": "CNN"}
        )

        outcome = await _reader(fetcher).describe_video(_png(), frames=9, span="0:00-2:09")

        assert (outcome.description, outcome.publisher) == ("A news broadcast.", "CNN")
        [sent] = fetcher.sent
        assert "contact sheet" in sent["messages"][0]["content"]
        assert sent["messages"][1]["content"][0]["text"] == (
            "Describe this video from these 9 frames, taken across 0:00-2:09 of it."
        )

    async def test_a_description_that_fails_is_a_reason(self) -> None:
        from tests.unit.test_image_reading import _Fetcher, _reader

        assert (await _reader(_Fetcher(None)).describe(_png())).reason is not None
        refused = await _reader(_Fetcher({"x": 1}, status=400)).describe_video(
            _png(), frames=3, span="0:00-0:03"
        )
        assert refused.reason == "provider returned 400"


class _Local:
    def __init__(self, reading: LocalReading) -> None:
        self.reading = reading

    def read(self, _: bytes) -> LocalReading:
        return self.reading


class _Hosted:
    def __init__(self, described: OcrOutcome) -> None:
        self.described = described
        self.asked: list[str] = []

    async def describe(self, image: bytes, *, mime_type: str = "") -> OcrOutcome:
        self.asked.append("describe")
        return self.described

    async def transcribe(self, image: bytes, *, mime_type: str = "") -> OcrOutcome:
        self.asked.append("transcribe")
        return OcrOutcome(text="read by the hosted reader", description="Described in full.")


def _confident(text: str) -> LocalReading:
    return LocalReading(
        lines=(OcrLine(text=text, confidence=0.97, top=0, left=0, bottom=100, right=400),),
        elapsed_ms=5,
        width=400,
        height=400,
    )


class TestEveryPictureIsDescribed:
    async def test_our_words_and_the_hosted_readers_description(self) -> None:
        hosted = _Hosted(
            OcrOutcome(
                description='A gazette page with a red "FAKE" stamp; the PIB Fact Check logo.',
                kind="DOCUMENT",
                publisher="PIB Fact Check",
            )
        )
        ocr = LocalFirstOcr(
            local=_Local(_confident("Fake Gazette claims all Saturdays are bank holidays")),  # type: ignore[arg-type]
            hosted=hosted,
        )

        outcome = await ocr.transcribe(_png())

        assert hosted.asked == ["describe"]
        assert outcome.text.startswith("Fake Gazette")
        assert outcome.model_id and outcome.model_id.startswith("rapidocr")
        assert "FAKE" in outcome.description
        assert (outcome.kind, outcome.publisher) == ("DOCUMENT", "PIB Fact Check")
        assert outcome.text_area == pytest.approx(0.25)

    async def test_a_description_that_fails_leaves_our_words(self) -> None:
        hosted = _Hosted(OcrOutcome(reason="provider returned 429"))
        ocr = LocalFirstOcr(local=_Local(_confident("RBI keeps repo rate at 5.25%")), hosted=hosted)  # type: ignore[arg-type]

        outcome = await ocr.transcribe(_png())

        assert outcome.succeeded
        assert outcome.text == "RBI keeps repo rate at 5.25%"
        assert outcome.description == ""

    async def test_too_little_read_here_asks_the_hosted_reader_for_everything(self) -> None:
        hosted = _Hosted(OcrOutcome(description="unused"))
        thin = LocalReading(
            lines=(OcrLine(text="SALE", confidence=0.99, top=0, left=0, bottom=10, right=10),),
            elapsed_ms=5,
            width=100,
            height=100,
        )
        ocr = LocalFirstOcr(local=_Local(thin), hosted=hosted)  # type: ignore[arg-type]

        outcome = await ocr.transcribe(_png())

        assert hosted.asked == ["transcribe"]
        assert outcome.text == "read by the hosted reader"
        # How much of it is text still comes from our own reader's boxes.
        assert outcome.text_area == pytest.approx(0.01)


# ------------------------------------------------------------ the sheet and the text


def _frame(at_ms: int, fill: tuple[int, int, int], size: tuple[int, int] = (160, 90)) -> Any:
    from app.media.video import Keyframe

    out = io.BytesIO()
    Image.new("RGB", size, fill).save(out, "JPEG")
    return Keyframe(index=at_ms, timestamp_ms=at_ms, data=out.getvalue())


class TestTheContactSheet:
    def test_the_frames_chosen_show_the_whole_clip_in_time_order(self) -> None:
        from app.media.sheet import pick_for_sheet

        talking = [_frame(1000 * second, (90, 90, 90)) for second in range(20)]
        card = _frame(12_500, (250, 250, 20))
        picked = pick_for_sheet([*talking, card], most=4)

        stamps = [frame.timestamp_ms for frame in picked]
        assert stamps == sorted(stamps)
        assert stamps[0] == 0 and stamps[-1] == 19_000
        # The one frame unlike the rest is never crowded out by the talking head.
        assert 12_500 in stamps
        assert len(picked) == 4

    def test_a_frame_that_cannot_be_opened_is_never_chosen(self) -> None:
        from app.media.sheet import contact_sheet, pick_for_sheet
        from app.media.video import Keyframe

        broken = Keyframe(index=0, timestamp_ms=500, data=b"not a picture")
        good = _frame(1000, (10, 200, 10))

        assert pick_for_sheet([broken, good]) == [good]
        assert contact_sheet([broken]) is None

    def test_nine_frames_are_laid_out_three_by_three_with_room_for_their_moments(self) -> None:
        from app.media.sheet import CELL, GAP, contact_sheet

        frames = [_frame(7000 * n, (20 * n, 100, 200), size=(854, 480)) for n in range(9)]
        sheet = contact_sheet(frames)

        assert sheet is not None
        with Image.open(io.BytesIO(sheet)) as picture:
            assert picture.format == "JPEG"
            width, height = picture.size
        assert width == 3 * CELL + 4 * GAP
        # Each row is a frame and the strip above it that holds its label.
        assert height > 3 * (CELL * 480 // 854) + 4 * GAP


class TestTheTextClaimsAreFoundIn:
    def test_every_part_with_words_under_its_label_descriptions_included(self) -> None:
        from app.extraction.reading import PartKind, Reading, ReadPart
        from app.media.composed import (
            PICTURE_DESCRIBED,
            SPOKEN_IN_VIDEO,
            TEXT_IN_VIDEO,
            VIDEO_DESCRIBED,
            compose,
        )

        reading = Reading(
            kind="video",
            parts=(
                ReadPart(PartKind.TRANSCRIPT, "Rates are unchanged.", "whisper", SPOKEN_IN_VIDEO),
                ReadPart(PartKind.ON_SCREEN_TEXT, "", "frames.ocr", TEXT_IN_VIDEO),
                ReadPart(
                    PartKind.VIDEO_DESCRIPTION, "A TV broadcast.", "ocr.hosted", VIDEO_DESCRIBED
                ),
            ),
        )

        composed = compose(reading)

        assert composed.text == (
            "Spoken in the video:\nRates are unchanged.\n\n"
            "What the video shows (described by Factify):\nA TV broadcast."
        )
        assert composed.span_of(1) is None
        start, end = composed.span_of(2) or (0, 0)
        assert composed.text[start:end] == "A TV broadcast."
        assert PICTURE_DESCRIBED == "What the picture shows (described by Factify)"

    def test_a_part_with_no_label_is_written_bare(self) -> None:
        from app.extraction.reading import PartKind, Reading, ReadPart
        from app.media.composed import compose

        reading = Reading(kind="pdf", parts=(ReadPart(PartKind.DOCUMENT_TEXT, "Circular", "pdf"),))

        assert compose(reading).text == "Circular"
