"""Reading the text in a picture on our own server: PaddleOCR's models, through RapidOCR.

The hosted model read every picture, and for Hindi that is not the gold standard it
looks like: in a June 2026 test on real Devanagari print, GPT-5.5 scored the same as
the free EasyOCR. PaddleOCR's PP-OCRv5 Devanagari reader (Apache-2.0, 7.9 MB) reads
Hindi and the Latin alphabet in one line, which is what a forward mixing the two
needs; the English reader of the same family is run beside it, and each line keeps
whichever reading the models were surer of. A second or two on a CPU, and nothing
leaves the server.

It reads text only. What the picture is and whose name it carries is the hosted
reader's to say, and since 2026-10-03 it is always asked (`LocalFirstOcr`): for the
description alone when this reader has the words, for everything when this one finds
little text or is unsure of what it found. Before, a picture whose words were read
here was never described, so the FAKE stamp on a gazette, the PIB Fact Check logo and
the leaders in an AI selfie went unseen.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from app.extraction.language import detect
from app.extraction.ocr import OcrOutcome, OcrRegion
from app.media.detectors.common import model_path, rgb
from app.observability.logging import event

logger = logging.getLogger("factify.extraction.local_ocr")

MODEL_ID = "rapidocr/PP-OCRv5"

DETECTOR = ("ocr-det-mobile", "inference.onnx")
READERS = {
    "hi": ("ocr-rec-devanagari", "inference.onnx"),
    "en": ("ocr-rec-en", "inference.onnx"),
}
# Read with when the two above are unsure: Tamil, PaddleOCR's own PP-OCRv5 reader
# (Apache-2.0). Every other script goes to the hosted reader.
#
# Telugu and Urdu had readers here too, and were taken out after they were measured
# against cards of known text (2026-09-28). Each was sure of itself and wrong in ways
# that change the claim: the Telugu reader read the "ra" joined under a letter as a
# bracket and dropped it, so "ప్రతి" (every) came out "పతి" (husband) and a claim
# about every woman became one about husbands and wives, which every source then
# rightly failed to support; the Urdu one is an Arabic-script reader and gave Arabic
# letters for Urdu ones ("ہر", every, read "بر"). A misread claim is checked wrong,
# which is worse than paying to read it right. Tamil read its claim whole (0.92 of
# the card, the errors in the call to action), and stays.
SCRIPT_READERS = {
    "ta": ("ocr-rec-ta", "inference.onnx"),
}
# Read right to left: none of the readers above, but kept for an Arabic-script one.
_RIGHT_TO_LEFT: frozenset[str] = frozenset()

# Enough text, read with enough confidence, that the hosted reader is not asked.
# A news card or a forward carries sentences; a photograph with a shop sign in it
# carries a word or two, and is better described than transcribed.
#
# 0.88, not 0.80: the Devanagari reader "read" a Tamil card as garbage at 0.74 and a
# Bengali one at 0.73 (2026-09-28), too close to 0.80 for comfort; real Hindi and
# English cards and screenshots read at 0.96-1.00.
ENOUGH_CHARACTERS = 24
ENOUGH_CONFIDENCE = 0.88


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    # The box, for matching the two readings and for reading order.
    top: float
    left: float
    bottom: float = 0.0
    right: float = 0.0

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def height(self) -> float:
        return max(1.0, self.bottom - self.top)


@dataclass(frozen=True, slots=True)
class LocalReading:
    lines: tuple[OcrLine, ...]
    elapsed_ms: float
    # Which reader it came from: "hi+en", or a script reader's language.
    reader: str = "hi+en"
    # The picture's size, for how much of it the text covers; 0 when not known.
    width: int = 0
    height: int = 0

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def text_area(self) -> float | None:
        """The share of the picture the text's lines cover, 0-1; None without a size.

        A card or a screenshot of a forward is mostly text; a photograph, even one
        with a caption or a sign in it, mostly is not (`looks_designed`).
        """
        if self.width <= 0 or self.height <= 0:
            return None
        covered = sum(
            max(0.0, line.right - line.left) * max(0.0, line.bottom - line.top)
            for line in self.lines
        )
        return min(1.0, covered / (self.width * self.height))

    @property
    def confidence(self) -> float:
        """Mean confidence, weighted by how much text each line holds."""
        total = sum(len(line.text) for line in self.lines)
        if not total:
            return 0.0
        return sum(line.confidence * len(line.text) for line in self.lines) / total

    @property
    def confident_characters(self) -> float:
        """How much text was read, weighted by how sure: for choosing between readers.
        Plain confidence let one reader win on "5000" alone over another that read the
        whole Urdu card."""
        return sum(line.confidence * len(line.text) for line in self.lines)

    @property
    def enough(self) -> bool:
        return (
            len(self.text.replace("\n", "").strip()) >= ENOUGH_CHARACTERS
            and self.confidence >= ENOUGH_CONFIDENCE
        )


def _keys_file(directory: str, folder: str) -> Path | None:
    """The reader's character list, from its `inference.yml`, as the one-per-line file
    RapidOCR expects. Written once beside the model."""
    target = Path(directory, folder, "keys.txt")
    if target.is_file() and target.stat().st_size > 0:
        return target
    config = model_path(directory, folder, "inference.yml")
    if config is None:
        return None
    import yaml  # type: ignore[import-untyped]

    loaded = yaml.safe_load(config.read_text(encoding="utf-8"))
    characters = loaded["PostProcess"]["character_dict"]
    target.write_text("\n".join(str(c) for c in characters) + "\n", encoding="utf-8")
    return target


class LocalOcr:
    """PP-OCRv5: one text finder, a Devanagari reader and an English reader."""

    def __init__(self, *, directory: str, threads: int = 4) -> None:
        self._directory = directory
        self._threads = threads
        self._lock = threading.Lock()
        self._engines: dict[str, Any] = {}
        self._loaded = False

    @property
    def available(self) -> bool:
        return (
            model_path(self._directory, *DETECTOR) is not None
            and model_path(self._directory, *READERS["hi"]) is not None
        )

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            from rapidocr import RapidOCR

            detector = model_path(self._directory, *DETECTOR)
            for language, (folder, file) in {**READERS, **SCRIPT_READERS}.items():
                reader = model_path(self._directory, folder, file)
                keys = _keys_file(self._directory, folder)
                if detector is None or reader is None or keys is None:
                    continue
                params: dict[str, Any] = {
                    "Global.use_cls": False,
                    "Global.log_level": "error",
                    "Det.model_path": str(detector),
                    "Rec.model_path": str(reader),
                    "Rec.rec_keys_path": str(keys),
                    "EngineConfig.onnxruntime.intra_op_num_threads": self._threads,
                    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                }
                if language in _RIGHT_TO_LEFT:
                    # RapidOCR puts an Arabic-script line back into reading order.
                    from rapidocr import LangRec

                    params["Rec.lang_type"] = LangRec.ARABIC
                try:
                    self._engines[language] = RapidOCR(params=params)
                except Exception:
                    logger.exception("OCR reader %s could not be loaded", language)
            self._loaded = True

    def read(self, data: bytes) -> LocalReading | None:
        """Every line of text found, best reading of each; None when no reader loaded."""
        self.load()
        if not self._engines:
            return None
        started = time.perf_counter()
        # BGR, as OpenCV and the models expect.
        image = np.asarray(rgb(data))[:, :, ::-1].copy()
        readings = {
            language: engine(image)
            for language, engine in self._engines.items()
            if language in READERS
        }
        best = LocalReading(lines=_best_of(readings), elapsed_ms=0.0)
        # Hindi and English first, as most pictures are; the other scripts only when
        # those two were unsure - each is another pass over the picture.
        if not best.enough:
            for language in SCRIPT_READERS:
                engine = self._engines.get(language)
                if engine is None:
                    continue
                candidate = LocalReading(
                    lines=_in_rows(_lines(engine(image)), right_to_left=language in _RIGHT_TO_LEFT),
                    elapsed_ms=0.0,
                    reader=language,
                )
                if candidate.confident_characters > best.confident_characters:
                    best = candidate
                if best.enough:
                    break
        return LocalReading(
            lines=best.lines,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            reader=best.reader,
            width=int(image.shape[1]),
            height=int(image.shape[0]),
        )


def _lines(result: Any) -> list[OcrLine]:
    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if boxes is None or texts is None or scores is None:
        return []
    found = []
    for box, text, score in zip(boxes, texts, scores, strict=False):
        points = np.asarray(box, dtype=np.float32)
        found.append(
            OcrLine(
                text=str(text).strip(),
                confidence=float(score),
                top=float(points[:, 1].min()),
                left=float(points[:, 0].min()),
                bottom=float(points[:, 1].max()),
                right=float(points[:, 0].max()),
            )
        )
    return [line for line in found if line.text]


def _best_of(readings: dict[str, Any]) -> tuple[OcrLine, ...]:
    """Each piece of text as whichever reader was surer of it, in reading order.

    Both readers see boxes from the same text finder; a piece is matched to its twin
    by overlap. A Hindi word read by the English model comes back as low-confidence
    Latin noise, and the reverse, so confidence picks the right one.
    """
    by_language = {language: _lines(result) for language, result in readings.items()}
    primary = by_language.get("hi") or []
    unmatched = list(by_language.get("en") or [])
    chosen: list[OcrLine] = []
    for piece in primary:
        twin = max(unmatched, key=lambda other: _overlap(piece, other), default=None)
        if twin is not None and _overlap(piece, twin) > 0.5:
            unmatched.remove(twin)
            chosen.append(twin if twin.confidence > piece.confidence else piece)
        else:
            chosen.append(piece)
    chosen.extend(unmatched)
    return _in_rows(chosen)


def _overlap(one: OcrLine, other: OcrLine) -> float:
    """Intersection over union of two boxes."""
    width = min(one.right, other.right) - max(one.left, other.left)
    height = min(one.bottom, other.bottom) - max(one.top, other.top)
    if width <= 0 or height <= 0:
        return 0.0
    shared = width * height
    area = (one.right - one.left) * one.height + (other.right - other.left) * other.height
    return shared / max(1.0, area - shared)


def _in_rows(pieces: list[OcrLine], *, right_to_left: bool = False) -> tuple[OcrLine, ...]:
    """Pieces on the same row joined left to right, rows top to bottom.

    By the middle of each box rather than its top: a Devanagari word's headline sits
    higher than the Latin word beside it, and sorting by top put "now:" after the web
    address that followed it.
    """
    rows: list[list[OcrLine]] = []
    for piece in sorted(pieces, key=lambda p: p.middle):
        row = rows[-1] if rows else None
        if row is not None and abs(piece.middle - _middle(row)) < 0.5 * _height(row):
            row.append(piece)
        else:
            rows.append([piece])
    joined = []
    for row in rows:
        row.sort(key=lambda p: -p.right if right_to_left else p.left)
        characters = sum(len(p.text) for p in row)
        joined.append(
            OcrLine(
                text=" ".join(p.text for p in row),
                confidence=sum(p.confidence * len(p.text) for p in row) / max(1, characters),
                top=min(p.top for p in row),
                left=min(p.left for p in row),
                bottom=max(p.bottom for p in row),
                right=max(p.right for p in row),
            )
        )
    return tuple(joined)


def _middle(row: list[OcrLine]) -> float:
    return sum(p.middle for p in row) / len(row)


def _height(row: list[OcrLine]) -> float:
    return sorted(p.height for p in row)[len(row) // 2]


class LocalFirstOcr:
    """Our own reader for the words first; the hosted one always says what the picture
    shows, and reads the words too when ours finds too little."""

    def __init__(self, *, local: LocalOcr, hosted: Any | None) -> None:
        self._local = local
        self._hosted = hosted

    @property
    def local(self) -> LocalOcr:
        """Our own reader on its own, with no hosted fallback: for the frames of a
        video (`app/media/frame_text.py`), where two dozen frames sent to a paid model
        would cost more than the check, and a frame with little text is no loss."""
        return self._local

    @property
    def hosted(self) -> Any | None:
        """The hosted reader, for what a video shows (`OcrExtractor.describe_video`)."""
        return self._hosted

    async def transcribe(self, image: bytes, *, mime_type: str = "image/jpeg") -> OcrOutcome:
        import asyncio

        reading: LocalReading | None = None
        try:
            reading = await asyncio.to_thread(self._local.read, image)
        except Exception:
            logger.exception("local OCR failed; the hosted reader is asked instead")

        if reading is not None and (reading.enough or self._hosted is None):
            text = reading.text
            event(
                logger,
                "image read",
                module="extraction.local_ocr",
                outcome="ok" if text else "skipped",
                provider="local",
                model_id=MODEL_ID,
                character_count=len(text),
                confidence=round(reading.confidence, 3),
                lines=len(reading.lines),
                reader=reading.reader,
                text_area=round(reading.text_area, 3) if reading.text_area is not None else None,
                latency_ms=round(reading.elapsed_ms),
            )
            if not text.strip():
                return OcrOutcome(reason="no legible text", model_id=MODEL_ID)
            read = OcrOutcome(
                text=text,
                language=detect(text),
                regions=tuple(
                    OcrRegion(text=line.text, index=index)
                    for index, line in enumerate(reading.lines)
                ),
                model_id=MODEL_ID,
                text_area=reading.text_area,
            )
            return await self._with_description(read, image, mime_type=mime_type)

        if reading is not None:
            event(
                logger,
                "local reading too thin; asking the hosted reader",
                module="extraction.local_ocr",
                outcome="degraded",
                provider="local",
                character_count=len(reading.text),
                confidence=round(reading.confidence, 3),
            )
        if self._hosted is None:
            return OcrOutcome(reason="unavailable: no reader could read this picture")
        hosted: OcrOutcome = await self._hosted.transcribe(image, mime_type=mime_type)
        if reading is not None and hosted.text_area is None:
            # How much of the picture is text, from our own reader's boxes, even though
            # its words were not the ones kept.
            hosted = replace(hosted, text_area=reading.text_area)
        return hosted

    async def _with_description(
        self, read: OcrOutcome, image: bytes, *, mime_type: str
    ) -> OcrOutcome:
        """Our own reading, with what the hosted reader says the picture is and shows.

        The words stay ours. A hosted reader that cannot describe it - down, refusing,
        or one with no `describe` - leaves the reading as it was, undescribed.
        """
        describe = getattr(self._hosted, "describe", None)
        if describe is None:
            return read
        try:
            described: OcrOutcome = await describe(image, mime_type=mime_type)
        except Exception:
            logger.exception("the picture could not be described; its words are kept")
            return read
        if not described.succeeded:
            event(
                logger,
                "picture not described",
                module="extraction.local_ocr",
                outcome="degraded",
                provider="llm",
                failure_reason=described.reason,
            )
            return read
        return replace(
            read,
            description=described.description,
            kind=described.kind,
            publisher=described.publisher,
        )
