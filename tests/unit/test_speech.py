"""What is said in a video (2026-09-30): read on our own server, and never invented.

The model is stood in for: these test what the reader does with what Whisper writes,
and what it says happened when nothing was written (contract 1.8): a silent video
read in full is not a video whose speech could not be read.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.media import speech as speech_module
from app.media.detectors import voice
from app.media.detectors.voice import Sound, decode_sound, decode_timeout
from app.media.speech import (
    MAX_CHARACTERS,
    RATE,
    SpeechOutcome,
    SpeechReader,
    Transcript,
    build,
    max_characters,
    read_speech,
)

pytestmark = pytest.mark.unit

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="no ffmpeg")


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
        from app.api.verify import _heard

        heard = await _heard(self._request(None), b"video", max_seconds=600)  # type: ignore[arg-type]

        assert heard.transcript is None
        # Said, not taken for a silent video.
        assert heard.unread

    async def test_a_reader_that_fails_takes_nothing_else_down(self) -> None:
        from app.api.verify import _heard

        class _Broken:
            def read_video_outcome(self, _video: bytes, *, max_seconds: float) -> SpeechOutcome:
                raise RuntimeError("model gone")

        heard = await _heard(self._request(_Broken()), b"video", max_seconds=600)  # type: ignore[arg-type]

        assert heard.status == "failed"
        assert heard.transcript is None

    async def test_what_is_said_is_passed_on_with_the_whole_window(self) -> None:
        from app.api.verify import _heard

        said = Transcript(
            text="Every woman gets Rs 5,000.",
            language="en",
            language_confidence=0.99,
            seconds_read=1.0,
            audio_seconds=129.0,
        )
        windows: list[float] = []

        class _Reader:
            def read_video_outcome(self, _video: bytes, *, max_seconds: float) -> SpeechOutcome:
                windows.append(max_seconds)
                return SpeechOutcome(status="read", transcript=said, audio_seconds=129.0)

        heard = await _heard(self._request(_Reader()), b"video", max_seconds=600)  # type: ignore[arg-type]

        assert heard.transcript == said
        # The whole clip up to the background window, not the first three minutes.
        assert windows == [600]


# ------------------------------------------------------------ what happened (1.8)


class _Silent:
    """A Whisper that must not be asked: there is nothing for it to read."""

    def transcribe(self, _samples: object, **_: object) -> tuple[object, object]:
        raise AssertionError("Whisper was asked to read a video with nothing to read")


class _Failing:
    def transcribe(self, _samples: object, **_: object) -> tuple[object, object]:
        raise RuntimeError("model gone")


def _sounds(
    monkeypatch: pytest.MonkeyPatch, sound: Sound, asked: list[float] | None = None
) -> None:
    """The video's sound, as the decoder would give it."""

    def decoded(_video: bytes, *, max_seconds: float) -> Sound:
        if asked is not None:
            asked.append(max_seconds)
        return sound

    monkeypatch.setattr(speech_module, "decode_sound", decoded)


def _seconds_of_sound(seconds: float) -> Sound:
    return Sound(status="ok", samples=np.zeros(int(RATE * seconds), dtype=np.float32))


def _unasked() -> SpeechReader:
    reader = SpeechReader(directory="nowhere")
    reader._model = _Silent()
    return reader


class TestWhatHappened:
    def test_what_is_said_is_read_with_how_much_was_heard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _sounds(monkeypatch, _seconds_of_sound(5))
        reader = _reader([_Segment("Every woman gets Rs 5,000 a month.", 0.0, 4.0)], "en")

        outcome = reader.read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "read"
        assert outcome.transcript is not None
        assert outcome.transcript.text == "Every woman gets Rs 5,000 a month."
        assert outcome.audio_seconds == 5.0
        # Seconds of sound heard, not the seconds the reading took.
        assert outcome.transcript.audio_seconds == 5.0
        assert not outcome.transcript.cut_off
        assert not outcome.unread

    def test_sound_with_no_speech_in_it_was_read_in_full(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Music under a clip: Whisper's "Thank you for watching" is dropped, and the
        video was read - nothing in it was said."""
        _sounds(monkeypatch, _seconds_of_sound(8))
        reader = _reader(
            [_Segment("Thank you for watching.", 0.0, 3.0, no_speech_prob=0.9, avg_logprob=-1.4)],
            "en",
        )

        outcome = reader.read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "no_speech"
        assert outcome.transcript is None
        assert outcome.audio_seconds == 8.0
        assert not outcome.unread

    def test_under_a_second_of_sound_holds_no_speech(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _sounds(monkeypatch, _seconds_of_sound(0.5))

        outcome = _unasked().read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "no_speech"
        assert outcome.audio_seconds == 0.5
        assert not outcome.unread

    def test_a_video_with_no_sound_track_was_read_in_full(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _sounds(monkeypatch, Sound(status="no_audio", reason="the video has no sound track"))

        outcome = _unasked().read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "no_audio"
        assert outcome.audio_seconds == 0.0
        assert not outcome.unread

    def test_sound_that_cannot_be_decoded_is_a_failure_not_a_silence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _sounds(monkeypatch, Sound(status="failed", reason="decoding took longer than 60s"))

        outcome = _unasked().read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "failed"
        assert outcome.unread
        assert outcome.audio_seconds is None
        assert outcome.reason == "decoding took longer than 60s"

    def test_a_reader_that_fails_is_a_failure_not_a_silence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It used to be None, as a silent video's is, and the video was checked as if
        nothing had been said in it."""
        _sounds(monkeypatch, _seconds_of_sound(5))
        reader = SpeechReader(directory="nowhere")
        reader._model = _Failing()

        outcome = reader.read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "failed"
        assert outcome.unread
        assert outcome.audio_seconds == 5.0
        assert outcome.reason is not None and "RuntimeError" in outcome.reason
        # The old call still answers None, as it always did.
        assert reader.read_video(b"video") is None

    def test_without_ffmpeg_speech_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _sounds(monkeypatch, Sound(status="unavailable", reason="ffmpeg is not installed"))

        outcome = _unasked().read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "unavailable"
        assert outcome.unread

    def test_a_model_that_cannot_be_loaded_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _sounds(monkeypatch, _seconds_of_sound(5))
        reader = SpeechReader(directory="nowhere")

        def broken() -> None:
            raise OSError("model.bin is truncated")

        # Stood in for: a real load of a missing model would go looking for it online.
        monkeypatch.setattr(reader, "load", broken)

        outcome = reader.read_video_outcome(b"video", max_seconds=600)

        assert outcome.status == "unavailable"
        assert outcome.unread
        assert outcome.reason is not None and "OSError" in outcome.reason


class TestTheWindow:
    def test_a_second_more_than_the_window_is_decoded_to_know_a_longer_clip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[float] = []
        _sounds(monkeypatch, _seconds_of_sound(12), asked)
        reader = _reader([_Segment("The dam has burst, leave now.", 0.0, 4.0)], "en")

        outcome = reader.read_video_outcome(b"video", max_seconds=10)

        assert asked == [11]
        assert outcome.status == "read"
        assert outcome.audio_seconds == 10.0
        assert outcome.transcript is not None
        assert outcome.transcript.audio_seconds == 10.0
        assert outcome.transcript.cut_off

    def test_the_transcript_kept_grows_with_the_window(self) -> None:
        assert max_characters(90) == MAX_CHARACTERS == 4000
        assert max_characters(180) == 4500
        assert max_characters(600) == 15000

    def test_minutes_of_speech_are_kept_whole_in_a_long_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """6,000 characters is about seven minutes of speech: it used to be cut at
        4,000, two thirds of the way through."""
        sentence = "The government has announced a new scheme for every farmer in the state."
        segments = [_Segment(sentence, 5.0 * index, 5.0 * index + 4.5) for index in range(84)]
        said = " ".join([sentence] * 84)
        assert len(said) > 6000
        _sounds(monkeypatch, _seconds_of_sound(420))

        whole = _reader(segments, "en").read_video_outcome(b"video", max_seconds=600)
        short = _reader(segments, "en").read_video_outcome(b"video", max_seconds=90)

        assert whole.transcript is not None and short.transcript is not None
        assert whole.transcript.text == said
        assert not whole.transcript.cut_off
        # Cut at a whole word, and said to be cut.
        assert len(short.transcript.text) <= 4000
        assert said.startswith(short.transcript.text)
        assert said[len(short.transcript.text)] == " "
        assert short.transcript.cut_off


class TestReadingOffTheEventLoop:
    async def test_with_no_reader_here_the_speech_is_unavailable(self) -> None:
        outcome = await read_speech(None, b"video", max_seconds=600)

        assert outcome.status == "unavailable"
        assert outcome.unread

    async def test_a_reader_that_raises_is_a_failure(self) -> None:
        class _Broken:
            def read_video_outcome(self, _video: bytes, *, max_seconds: float) -> SpeechOutcome:
                raise MemoryError

        outcome = await read_speech(_Broken(), b"video", max_seconds=600)  # type: ignore[arg-type]

        assert outcome.status == "failed"
        assert outcome.reason is not None and "MemoryError" in outcome.reason

    async def test_the_window_is_passed_on(self) -> None:
        heard: list[float] = []

        class _Reader:
            def read_video_outcome(self, _video: bytes, *, max_seconds: float) -> SpeechOutcome:
                heard.append(max_seconds)
                return SpeechOutcome(status="no_audio", audio_seconds=0.0)

        outcome = await read_speech(_Reader(), b"video", max_seconds=600)  # type: ignore[arg-type]

        assert heard == [600]
        assert outcome.status == "no_audio"


# ------------------------------------------------------------------------ decoding


def _stand_in_ffmpeg(monkeypatch: pytest.MonkeyPatch, run: object) -> None:
    """ffmpeg for the decoder alone: its `subprocess` and `shutil`, not the process's."""
    monkeypatch.setattr(voice, "shutil", SimpleNamespace(which=lambda _: "ffmpeg"))
    monkeypatch.setattr(
        voice, "subprocess", SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired)
    )


class TestDecoding:
    def test_the_time_allowed_grows_with_the_window(self) -> None:
        assert decode_timeout(0) == 30.0
        assert decode_timeout(90) == pytest.approx(34.5)
        assert decode_timeout(600) == pytest.approx(60.0)

    def test_ten_minutes_are_given_a_minute_to_decode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        given: list[float] = []

        def run(command: list[str], **options: float) -> subprocess.CompletedProcess[bytes]:
            given.append(options["timeout"])
            return subprocess.CompletedProcess(command, 0, stdout=b"\x00\x00" * RATE, stderr=b"")

        _stand_in_ffmpeg(monkeypatch, run)

        sound = decode_sound(b"video", max_seconds=600)

        assert given == [pytest.approx(60.0)]
        assert sound.status == "ok"
        assert sound.samples is not None and len(sound.samples) == RATE

    def test_a_decode_that_runs_out_of_time_is_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def run(command: list[str], **options: float) -> subprocess.CompletedProcess[bytes]:
            raise subprocess.TimeoutExpired(command, options["timeout"])

        _stand_in_ffmpeg(monkeypatch, run)

        sound = decode_sound(b"video", max_seconds=600)

        assert sound.status == "failed"
        assert sound.reason == "decoding the sound took longer than 60s"
        assert voice.decode_audio(b"video", max_seconds=600) is None

    def test_without_ffmpeg_the_sound_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(voice, "shutil", SimpleNamespace(which=lambda _: None))

        assert decode_sound(b"video", max_seconds=90).status == "unavailable"
        assert voice.decode_audio(b"video", max_seconds=90) is None

    @requires_ffmpeg
    def test_a_video_with_no_sound_track_is_told_from_one_that_cannot_be_read(
        self, tmp_path: Path
    ) -> None:
        clip = tmp_path / "silent.mp4"
        subprocess.run(
            [
                str(shutil.which("ffmpeg")),
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=2:size=64x64:rate=10",
                "-c:v",
                "mpeg4",
                str(clip),
            ],
            check=True,
            timeout=60,
        )

        assert decode_sound(clip.read_bytes(), max_seconds=90).status == "no_audio"
        assert decode_sound(b"not a video at all", max_seconds=90).status == "failed"

    @requires_ffmpeg
    def test_sound_is_decoded_to_the_window(self) -> None:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(RATE)
            writer.writeframes((np.sin(np.arange(RATE * 4) / 9) * 8000).astype("<i2").tobytes())

        sound = decode_sound(buffer.getvalue(), max_seconds=2)

        assert sound.status == "ok"
        assert sound.samples is not None
        assert abs(len(sound.samples) - 2 * RATE) <= RATE // 50
