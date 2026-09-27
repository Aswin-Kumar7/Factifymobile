"""The cloned-voice detector's plumbing, without its 1.27 GB model.

A fake ONNX session stands in for Spectra-AASIST, so these prove what this module
decides on its own - which stretches of sound are judged, what counts as silence,
how two logits become a probability, and that a missing or broken model means "not
checked" - not whether the model is any good. That is the one `model` test at the
end, and the measurement behind the report, which found it no better than a guess
on the voices our users forward.

    FACTIFY_MODEL_TESTS=1 uv run --extra models pytest tests/unit/test_voice.py -m model
"""

from __future__ import annotations

import io
import math
import os
import shutil
import subprocess
import wave
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.media.detectors import voice
from app.media.detectors.voice import (
    BONAFIDE_LOGIT_AT,
    LOGIT_SUM,
    MAX_WINDOWS,
    RATE,
    THRESHOLD,
    WINDOW,
    VoiceDetector,
    VoiceScore,
    decode_audio,
    select_windows,
)

pytestmark = pytest.mark.unit

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def _speech_like(seconds: float, *, level: float = 0.3, seed: int = 0) -> np.ndarray:
    """Noise whose loudness rises and falls four times a second, like syllables, over a
    faint floor, like a room."""
    rng = np.random.default_rng(seed)
    count = int(seconds * RATE)
    time = np.arange(count) / RATE
    envelope = 0.1 + 0.9 * np.clip(np.sin(2 * math.pi * 4 * time), 0, None) ** 2
    return (level * envelope * rng.standard_normal(count)).astype(np.float32)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * RATE), dtype=np.float32)


class _Input:
    def __init__(self, shape: list[Any]) -> None:
        self.name = "waveform"
        self.shape = shape


class FakeSession:
    """Answers every window with the same logits, and remembers what it was fed."""

    def __init__(
        self, logits: tuple[float, float] = (0.0, 0.0), shape: list[Any] | None = None
    ) -> None:
        self.logits = logits
        self.shape = shape if shape is not None else ["batch", "samples"]
        self.fed: list[np.ndarray] = []

    def get_inputs(self) -> list[_Input]:
        return [_Input(self.shape)]

    def run(self, _outputs: Any, feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        batch = feed["waveform"]
        self.fed.append(batch)
        return [np.tile(np.array(self.logits, dtype=np.float32), (batch.shape[0], 1))]


def _detector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session: FakeSession
) -> VoiceDetector:
    folder = tmp_path / voice.MODEL[0]
    folder.mkdir()
    (folder / voice.MODEL[1]).write_bytes(b"weights")
    monkeypatch.setattr(voice, "onnx_session", lambda _path, *, threads: session)
    return VoiceDetector(directory=str(tmp_path))


# --- which stretches are judged ---------------------------------------------------


def test_silence_has_no_windows() -> None:
    assert select_windows(_silence(30)) == []


def test_a_steady_hum_is_not_speech() -> None:
    time = np.arange(30 * RATE) / RATE
    hum = (0.3 * np.sin(2 * math.pi * 220 * time)).astype(np.float32)
    assert select_windows(hum) == []


def test_steady_hiss_is_not_speech() -> None:
    hiss = (0.05 * np.random.default_rng(1).standard_normal(30 * RATE)).astype(np.float32)
    assert select_windows(hiss) == []


def test_the_loudest_stretches_are_chosen_and_never_overlap() -> None:
    # 90 seconds of quiet speech with one loud stretch from 40 s to 50 s.
    audio = _speech_like(90, level=0.1)
    audio[40 * RATE : 50 * RATE] = _speech_like(10, level=0.5, seed=2)
    starts = select_windows(audio)
    assert len(starts) == MAX_WINDOWS
    loudest = starts[0]
    assert 40 * RATE <= loudest and loudest + WINDOW <= 50 * RATE
    ordered = sorted(starts)
    assert all(later - earlier >= WINDOW for earlier, later in pairwise(ordered))
    assert all(0 <= start <= len(audio) - WINDOW for start in starts)


def test_silent_stretches_are_skipped_even_when_few_are_left() -> None:
    # Six seconds of speech in 86 of silence: only windows that are mostly speech.
    audio = np.concatenate([_silence(40), _speech_like(6), _silence(40)])
    starts = select_windows(audio)
    assert 1 <= len(starts) <= 2
    assert all(40 * RATE - 0.6 * WINDOW <= start <= 46 * RATE - 0.4 * WINDOW for start in starts)


def test_a_short_clip_is_one_window_and_a_blip_is_none() -> None:
    assert select_windows(_speech_like(2.5)) == [0]
    assert select_windows(_speech_like(0.5)) == []


# --- what is fed to the model, and what comes back --------------------------------


def test_silence_is_none_without_running_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeSession()
    detector = _detector(tmp_path, monkeypatch, session)
    assert detector.score_audio(_silence(20)) is None
    assert session.fed == []


def test_windows_are_preemphasised_and_full_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeSession()
    detector = _detector(tmp_path, monkeypatch, session)
    audio = _speech_like(30)
    score = detector.score_audio(audio)
    assert score is not None
    assert 4 <= score.windows <= MAX_WINDOWS
    assert score.seconds == pytest.approx(score.windows * WINDOW / RATE, abs=0.01)
    # One window per call (a batch was measured slower on a CPU), each full length.
    assert len(session.fed) == score.windows
    assert all(batch.dtype == np.float32 for batch in session.fed)
    assert all(batch.shape == (1, WINDOW) for batch in session.fed)
    start = select_windows(audio)[0]
    expected = audio[start + 1 : start + 100] - 0.97 * audio[start : start + 99]
    np.testing.assert_allclose(session.fed[0][0, 1:100], expected, rtol=1e-5, atol=1e-7)


def test_a_short_clip_is_repeated_to_fill_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeSession()
    detector = _detector(tmp_path, monkeypatch, session)
    score = detector.score_audio(_speech_like(2))
    assert score is not None
    assert score.windows == 1
    assert score.seconds == pytest.approx(2.0)
    (batch,) = session.fed
    assert batch.shape == (1, WINDOW)
    np.testing.assert_array_equal(batch[0, 2 * RATE : 2 * RATE + 50], batch[0, :50])


def test_stereo_is_refused_rather_than_misread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detector = _detector(tmp_path, monkeypatch, FakeSession())
    with pytest.raises(ValueError, match="mono"):
        detector.score_audio(np.stack([_speech_like(10), _speech_like(10)], axis=1))
    assert detector.score_audio(_speech_like(10)[None, :]) is not None


def test_a_graph_for_another_window_length_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = FakeSession(shape=["batch", 48_000])
    detector = _detector(tmp_path, monkeypatch, session)
    detector.load()
    assert not detector.available
    assert "voice model expects input" in caplog.text
    assert detector.score_audio(_speech_like(10)) is None
    assert session.fed == []


@pytest.mark.parametrize("logits", [(0.0, 0.0), (3.0, -1.0), (-2.0, 2.5), (40.0, -40.0)])
def test_likelihood_is_the_softmax_spoof_probability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logits: tuple[float, float]
) -> None:
    detector = _detector(tmp_path, monkeypatch, FakeSession(logits))
    score = detector.score_audio(_speech_like(20))
    assert score is not None
    spoof, bonafide = (math.exp(logit - max(logits)) for logit in logits)
    assert score.likelihood == pytest.approx(spoof / (spoof + bonafide))
    assert 0.0 <= score.likelihood <= 1.0


def test_threshold_is_the_makers_boundary_as_a_probability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A window exactly on the makers' boundary scores exactly the threshold; one on
    # either side lands on the matching side of it.
    on_boundary = (LOGIT_SUM - BONAFIDE_LOGIT_AT, BONAFIDE_LOGIT_AT)
    detector = _detector(tmp_path, monkeypatch, FakeSession(on_boundary))
    score = detector.score_audio(_speech_like(10))
    assert score is not None
    assert score.threshold == pytest.approx(THRESHOLD)
    assert score.likelihood == pytest.approx(THRESHOLD)
    assert 0.0 < THRESHOLD < 1.0
    spoofed = VoiceScore(likelihood=THRESHOLD + 0.01, threshold=THRESHOLD, seconds=4, windows=1)
    genuine = VoiceScore(likelihood=THRESHOLD - 0.01, threshold=THRESHOLD, seconds=4, windows=1)
    assert spoofed.raised and not genuine.raised


# --- a missing or broken model means "not checked" --------------------------------


def test_unavailable_when_the_model_is_missing(tmp_path: Path) -> None:
    detector = VoiceDetector(directory=str(tmp_path))
    assert not detector.available
    detector.load()
    assert not detector.available
    assert detector.score_audio(_speech_like(10)) is None
    assert detector.score_video(b"not a video") is None


def test_a_broken_model_is_logged_and_unavailable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    folder = tmp_path / voice.MODEL[0]
    folder.mkdir()
    (folder / voice.MODEL[1]).write_bytes(b"half a download")
    detector = VoiceDetector(directory=str(tmp_path))
    assert detector.available
    detector.load()
    assert not detector.available
    assert "voice model could not be loaded" in caplog.text
    assert detector.score_audio(_speech_like(10)) is None


def test_load_happens_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def loader(_path: Path, *, threads: int) -> FakeSession:
        calls.append("loaded")
        return FakeSession()

    folder = tmp_path / voice.MODEL[0]
    folder.mkdir()
    (folder / voice.MODEL[1]).write_bytes(b"weights")
    monkeypatch.setattr(voice, "onnx_session", loader)
    detector = VoiceDetector(directory=str(tmp_path))
    detector.load()
    detector.load()
    detector.score_audio(_speech_like(10))
    assert calls == ["loaded"]


# --- decoding a video's sound -----------------------------------------------------


def _wav(samples: np.ndarray, rate: int = RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


@requires_ffmpeg
def test_decoding_resamples_to_16khz_and_stops_at_max_seconds() -> None:
    audio = _speech_like(12)
    decoded = decode_audio(_wav(np.repeat(audio, 3), rate=48_000), max_seconds=5)
    assert decoded is not None
    assert decoded.dtype == np.float32
    assert abs(len(decoded) - 5 * RATE) <= RATE // 50


@requires_ffmpeg
def test_a_video_without_sound_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    session = FakeSession()
    detector = _detector(tmp_path, monkeypatch, session)
    assert decode_audio(clip.read_bytes(), max_seconds=90) is None
    assert detector.score_video(clip.read_bytes()) is None
    assert detector.score_video(b"not a video at all") is None
    assert session.fed == []


@requires_ffmpeg
def test_a_videos_sound_is_scored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession((1.0, -1.0))
    detector = _detector(tmp_path, monkeypatch, session)
    score = detector.score_video(_wav(_speech_like(20)))
    assert score is not None
    assert 3 <= score.windows <= 4
    assert score.likelihood == pytest.approx(1 / (1 + math.exp(-2.0)))


# --- the real model ---------------------------------------------------------------

MODELS = Path(".cache/models")


@pytest.mark.model
@pytest.mark.skipif(
    os.environ.get("FACTIFY_MODEL_TESTS") != "1"
    or not (MODELS / voice.MODEL[0] / voice.MODEL[1]).is_file(),
    reason="set FACTIFY_MODEL_TESTS=1 with Spectra-AASIST in .cache/models",
)
def test_the_real_model_scores_a_voice_and_ignores_silence() -> None:
    detector = VoiceDetector(directory=str(MODELS))
    detector.load()
    assert detector.available
    assert detector.score_audio(_silence(10)) is None
    score = detector.score_audio(_speech_like(10))
    assert score is not None
    assert 0.0 <= score.likelihood <= 1.0
    assert 1 <= score.windows <= 2
    assert score.threshold == pytest.approx(THRESHOLD)
