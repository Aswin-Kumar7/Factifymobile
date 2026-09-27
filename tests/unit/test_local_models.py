"""Our own models, and the rules around them (2026-09-28).

Held here, with fakes in place of the models: the text reader puts words back into
lines in reading order and keeps the surer of its two readings; the hosted reader is
asked only when ours finds too little; two AI-picture models must agree before a
picture is called likely AI-made, and "real" is never an answer; one failing
detector takes nothing else down; and the local page reader answers only "not about
the claim" and plain English support - never a contradiction, a debunk, reported
speech or Hindi.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

from app.domain.enums import SyntheticSignal
from app.extraction.local_ocr import LocalFirstOcr, LocalReading, OcrLine, _best_of
from app.extraction.ocr import OcrOutcome
from app.media.detectors.local import LocalDetector
from app.media.synthetic import LIKELY_AI, NO_SIGN, UNCLEAR, SyntheticReading
from app.sources.local_reading import local_reading, local_same_claim
from app.sources.reasoning import Passage
from app.sources.stance import Entailment


def _jpeg(width: int = 400, height: int = 300) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (120, 140, 160)).save(out, "JPEG")
    return out.getvalue()


# ---------------------------------------------------------------- reading text


@dataclass
class _Result:
    boxes: list[Any]
    txts: list[str]
    scores: list[float]


def _box(left: float, top: float, right: float, bottom: float) -> list[list[float]]:
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


class TestReadingText:
    def test_words_on_one_line_are_joined_in_reading_order(self) -> None:
        # A Devanagari word's box sits a little higher than the Latin one beside it.
        hindi = _Result(
            boxes=[_box(300, 100, 520, 150), _box(40, 96, 280, 146)],
            txts=["now:", "Apply"],
            scores=[0.99, 0.99],
        )
        [line] = _best_of({"hi": hindi})
        assert line.text == "Apply now:"

    def test_each_word_keeps_the_surer_reading(self) -> None:
        box = _box(40, 100, 300, 150)
        read = _best_of(
            {
                "hi": _Result(boxes=[box], txts=["वायरल"], scores=[0.95]),
                "en": _Result(boxes=[box], txts=["qrw"], scores=[0.31]),
            }
        )
        assert [line.text for line in read] == ["वायरल"]

    def test_rows_stay_in_order_top_to_bottom(self) -> None:
        read = _best_of(
            {
                "hi": _Result(
                    boxes=[_box(40, 300, 400, 350), _box(40, 100, 400, 150)],
                    txts=["second", "first"],
                    scores=[1.0, 1.0],
                )
            }
        )
        assert [line.text for line in read] == ["first", "second"]


class _Local:
    def __init__(self, reading: LocalReading | None) -> None:
        self.reading = reading

    def read(self, _: bytes) -> LocalReading | None:
        return self.reading


class _Hosted:
    asked = 0

    async def transcribe(self, image: bytes, *, mime_type: str = "image/jpeg") -> OcrOutcome:
        _Hosted.asked += 1
        return OcrOutcome(text="from the hosted reader", model_id="hosted")


def _reading(text: str, confidence: float) -> LocalReading:
    return LocalReading(
        lines=(OcrLine(text=text, confidence=confidence, top=0, left=0, bottom=10, right=10),),
        elapsed_ms=5,
    )


class TestLocalFirst:
    async def test_enough_text_read_confidently_never_reaches_the_hosted_reader(self) -> None:
        _Hosted.asked = 0
        ocr = LocalFirstOcr(
            local=_Local(_reading("RBI keeps repo rate unchanged at 6.5%", 0.97)),  # type: ignore[arg-type]
            hosted=_Hosted(),
        )
        outcome = await ocr.transcribe(_jpeg())
        assert outcome.text.startswith("RBI keeps")
        assert outcome.model_id and outcome.model_id.startswith("rapidocr")
        assert _Hosted.asked == 0

    async def test_too_little_or_unsure_asks_the_hosted_reader(self) -> None:
        _Hosted.asked = 0
        for reading in (_reading("SALE", 0.99), _reading("a long but unsure line of text", 0.4)):
            ocr = LocalFirstOcr(local=_Local(reading), hosted=_Hosted())  # type: ignore[arg-type]
            assert (await ocr.transcribe(_jpeg())).text == "from the hosted reader"
        assert _Hosted.asked == 2

    async def test_without_a_hosted_reader_what_was_read_is_kept(self) -> None:
        ocr = LocalFirstOcr(local=_Local(_reading("SALE", 0.99)), hosted=None)  # type: ignore[arg-type]
        assert (await ocr.transcribe(_jpeg())).text == "SALE"


# ---------------------------------------------------------------- AI-made pictures


class TestAgreement:
    def test_both_must_agree_before_likely_ai(self) -> None:
        both = SyntheticReading(generated=0.9, second_opinion=0.8, generated_at=0.65)
        one = SyntheticReading(generated=0.9, second_opinion=0.2, generated_at=0.65)
        none = SyntheticReading(generated=0.1, second_opinion=0.2, generated_at=0.65)
        assert (both.outcome, one.outcome, none.outcome) == (LIKELY_AI, UNCLEAR, NO_SIGN)

    def test_only_agreement_raises_a_suspicion(self) -> None:
        [one] = SyntheticReading(generated=0.9, second_opinion=0.2).advisories(artifact_ref="x")
        [both] = SyntheticReading(generated=0.9, second_opinion=0.8).advisories(artifact_ref="x")
        assert one.signal is SyntheticSignal.NO_SIGNAL
        assert both.signal is SyntheticSignal.ADVISORY_SUSPICION

    def test_never_real(self) -> None:
        reading = SyntheticReading(generated=0.01, second_opinion=0.01)
        assert reading.outcome == NO_SIGN
        assert all("real" not in a.note.lower() for a in reading.advisories(artifact_ref="x"))


@dataclass
class _Score:
    likelihood: float
    threshold: float = 0.5
    faces: int = 1


class _Model:
    def __init__(self, score: Any = None, *, fails: bool = False) -> None:
        self._score = score
        self._fails = fails

    def load(self) -> None: ...

    def score(self, _: bytes) -> Any:
        if self._fails:
            raise RuntimeError("broken model")
        return self._score

    score_frames = score  # type: ignore[assignment]

    def score_video(self, _: bytes) -> Any:
        return self._score


class TestLocalDetector:
    async def test_a_picture_is_read_by_every_model_present(self) -> None:
        detector = LocalDetector(
            pictures=_Model(_Score(0.9, 0.65)),
            second=_Model(_Score(0.8)),
            faces=_Model(_Score(0.3, 0.5, faces=2)),
        )
        reading = await detector.read(_jpeg())
        assert reading.on_server
        assert (reading.generated, reading.second_opinion, reading.face_swap) == (0.9, 0.8, 0.3)
        assert reading.faces == 2
        assert reading.outcome == LIKELY_AI

    async def test_one_failing_detector_takes_nothing_else_down(self) -> None:
        detector = LocalDetector(pictures=_Model(_Score(0.2, 0.65)), second=_Model(fails=True))
        reading = await detector.read(_jpeg())
        assert reading.checked and reading.second_opinion is None
        assert reading.outcome == NO_SIGN

    async def test_too_small_to_judge_is_not_checked(self) -> None:
        reading = await LocalDetector(pictures=_Model(None)).read(_jpeg(64, 48))
        assert not reading.checked

    async def test_a_clip_is_read_from_its_frames_and_its_sound(self) -> None:
        detector = LocalDetector(
            pictures=_Model(_Score(0.4, 0.65)),
            voice=_Model(_Score(0.8)),
        )
        reading = await detector.read_video(b"video", [_jpeg()] * 12)
        assert reading.voice == 0.8
        assert reading.generated == 0.4


# ---------------------------------------------------------------- reading pages


class _Stance:
    """Fake relevance and entailment, by substring."""

    can_gate = True

    def __init__(self, relevance: float, entails: float = 0.0, contradicts: float = 0.0) -> None:
        self._relevance = relevance
        self._entails = entails
        self._contradicts = contradicts
        self.entailment_asked = 0

    def relevance(self, _: str, passages: list[str]) -> list[float]:
        return [self._relevance] * len(passages)

    def entailment(self, premises: list[str], _: str) -> list[Entailment]:
        self.entailment_asked += 1
        rest = max(0.0, 1 - self._entails - self._contradicts)
        return [Entailment(self._entails, rest, self._contradicts)] * len(premises)


CLAIM = "The Reserve Bank of India kept the repo rate unchanged at 6.5 per cent."
STATES = "The Reserve Bank of India kept the repo rate unchanged at 6.5 per cent on Friday."


def _passages(text: str) -> list[Passage]:
    return [Passage(index=0, text=text, char_start=100, char_end=100 + len(text))]


class TestLocalReading:
    def test_a_page_not_about_the_claim_is_not_read_by_the_hosted_model(self) -> None:
        outcome = local_reading(_Stance(0.001), CLAIM, _passages(STATES), None, "STATEMENT")
        assert outcome is not None and outcome.judgements == ()

    def test_a_page_about_the_claim_is_always_read_by_the_hosted_model(self) -> None:
        # However sure a local model might be of support: it disagreed with the hosted
        # reader too often to decide (app/sources/local_reading.py).
        stance = _Stance(0.9, entails=0.999)
        assert local_reading(stance, CLAIM, _passages(STATES), None, None) is None
        assert stance.entailment_asked == 0

    def test_same_claim_only_rules_out_a_different_subject(self) -> None:
        assert local_same_claim(_Stance(0.001), CLAIM, "Something else entirely") is False
        assert local_same_claim(_Stance(0.9, entails=0.999), CLAIM, STATES) is None
