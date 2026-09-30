"""What is said in a video (2026-09-30): read on our own server, and never invented.

The model is stood in for: these test what the reader does with what Whisper writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from app.media.speech import RATE, SpeechReader, Transcript, build

pytestmark = pytest.mark.unit


@dataclass
class _Segment:
    text: str
    start: float
    end: float
    no_speech_prob: float = 0.05
    avg_logprob: float = -0.3


class _Whisper:
    def __init__(self, segments: list[_Segment], language: str = "hi") -> None:
        self._segments = segments
        self._language = language

    def transcribe(self, _samples: object, **_: object) -> tuple[object, object]:
        info = SimpleNamespace(language=self._language, language_probability=0.9)
        return iter(self._segments), info


def _reader(segments: list[_Segment], language: str = "hi") -> SpeechReader:
    reader = SpeechReader(directory="nowhere")
    reader._model = _Whisper(segments, language)
    return reader


def _second_of_sound() -> np.ndarray:
    return np.zeros(RATE * 2, dtype=np.float32)


def test_what_is_said_is_written_down_in_its_own_language() -> None:
    reader = _reader(
        [
            _Segment("सरकार ने घोषणा की है", 0.0, 2.5),
            _Segment(" कि हर महिला को   पाँच हज़ार रुपये मिलेंगे।", 2.5, 5.0),
        ]
    )

    transcript = reader.read(_second_of_sound())

    assert isinstance(transcript, Transcript)
    assert transcript.text == "सरकार ने घोषणा की है कि हर महिला को पाँच हज़ार रुपये मिलेंगे।"
    assert transcript.language == "hi"


def test_words_written_over_silence_are_dropped() -> None:
    """Whisper's "Thank you for watching" over music: sure it is not speech, and
    unsure of its own words."""
    reader = _reader(
        [
            _Segment("Thank you for watching.", 0.0, 3.0, no_speech_prob=0.9, avg_logprob=-1.4),
        ],
        language="en",
    )

    assert reader.read(_second_of_sound()) is None


def test_a_breath_of_speech_is_not_a_claim() -> None:
    reader = _reader([_Segment("Hmm.", 0.0, 0.6)], language="en")

    assert reader.read(_second_of_sound()) is None


def test_it_is_off_when_switched_off_or_its_files_are_missing() -> None:
    local = SimpleNamespace(speech=False, directory="nowhere", speech_model="small", threads=2)
    assert build(SimpleNamespace(local=local)) is None
    local = SimpleNamespace(speech=True, directory="nowhere", speech_model="small", threads=2)
    assert build(SimpleNamespace(local=local)) is None


class TestAVideosSpeechInTheCheck:
    @staticmethod
    def _request(reader: object | None) -> object:
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(speech_reader=reader)))

    async def test_without_a_reader_the_video_is_checked_from_its_frames(self) -> None:
        from app.api.verify import _spoken

        assert await _spoken(self._request(None), b"video") is None  # type: ignore[arg-type]

    async def test_a_reader_that_fails_takes_nothing_else_down(self) -> None:
        from app.api.verify import _spoken

        class _Broken:
            def read_video(self, _video: bytes) -> Transcript:
                raise RuntimeError("model gone")

        assert await _spoken(self._request(_Broken()), b"video") is None  # type: ignore[arg-type]

    async def test_what_is_said_is_passed_on(self) -> None:
        from app.api.verify import _spoken

        said = Transcript(
            text="Every woman gets Rs 5,000.",
            language="en",
            language_confidence=0.99,
            seconds_read=1.0,
        )

        class _Reader:
            def read_video(self, _video: bytes) -> Transcript:
                return said

        assert await _spoken(self._request(_Reader()), b"video") == said  # type: ignore[arg-type]
