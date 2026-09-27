"""Reading the text in a picture on our own server: PaddleOCR's models, through RapidOCR.

The hosted model read every picture, and for Hindi that is not the gold standard it
looks like: in a June 2026 test on real Devanagari print, GPT-5.5 scored the same as
the free EasyOCR. PaddleOCR's PP-OCRv5 Devanagari reader (Apache-2.0, 7.9 MB) reads
Hindi and the Latin alphabet in one line, which is what a forward mixing the two
needs; the English reader of the same family is run beside it, and each line keeps
whichever reading the models were surer of. A second or two on a CPU, and nothing
leaves the server.

It reads text only. What the picture is and whose name it carries - the hosted
reader's description - is shown in the app and decides nothing, so when this reader
has read the picture it is simply not shown. The hosted reader is asked only when
this one finds little text or is unsure of what it found (`LocalFirstOcr`).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.extraction.language import detect
from app.extraction.ocr import OcrOutcome, OcrRegion
from app.media.detectors.common import model_path, rgb
from app.observability.logging import event

logger = logging.getLogger("factify.extraction.local_ocr")

MODEL_ID = "rapidocr/PP-OCRv5-devanagari+en"

DETECTOR = ("ocr-det-mobile", "inference.onnx")
READERS = {
    "hi": ("ocr-rec-devanagari", "inference.onnx"),
    "en": ("ocr-rec-en", "inference.onnx"),
}

# Enough text, read with enough confidence, that the hosted reader is not asked.
# A news card or a forward carries sentences; a photograph with a shop sign in it
# carries a word or two, and is better described than transcribed.
ENOUGH_CHARACTERS = 24
ENOUGH_CONFIDENCE = 0.80


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

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def confidence(self) -> float:
        """Mean confidence, weighted by how much text each line holds."""
        total = sum(len(line.text) for line in self.lines)
        if not total:
            return 0.0
        return sum(line.confidence * len(line.text) for line in self.lines) / total

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
            for language, (folder, file) in READERS.items():
                reader = model_path(self._directory, folder, file)
                keys = _keys_file(self._directory, folder)
                if detector is None or reader is None or keys is None:
                    continue
                try:
                    self._engines[language] = RapidOCR(
                        params={
                            "Global.use_cls": False,
                            "Global.log_level": "error",
                            "Det.model_path": str(detector),
                            "Rec.model_path": str(reader),
                            "Rec.rec_keys_path": str(keys),
                            "EngineConfig.onnxruntime.intra_op_num_threads": self._threads,
                            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                        }
                    )
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
        readings = {language: engine(image) for language, engine in self._engines.items()}
        lines = _best_of(readings)
        return LocalReading(lines=lines, elapsed_ms=(time.perf_counter() - started) * 1000)


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


def _in_rows(pieces: list[OcrLine]) -> tuple[OcrLine, ...]:
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
        row.sort(key=lambda p: p.left)
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
    """Our own reader first; the hosted one only when ours finds too little."""

    def __init__(self, *, local: LocalOcr, hosted: Any | None) -> None:
        self._local = local
        self._hosted = hosted

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
                latency_ms=round(reading.elapsed_ms),
            )
            if not text.strip():
                return OcrOutcome(reason="no legible text", model_id=MODEL_ID)
            return OcrOutcome(
                text=text,
                language=detect(text),
                regions=tuple(
                    OcrRegion(text=line.text, index=index)
                    for index, line in enumerate(reading.lines)
                ),
                model_id=MODEL_ID,
            )

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
        return hosted
