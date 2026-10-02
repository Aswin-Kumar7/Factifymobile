"""Was the voice in this video made by a speech generator? Spectra-AASIST, on a CPU.

`lab260/Spectra-AASIST` (Apache-2.0): a wav2vec 2.0 XLS-R 300M encoder, a
self-supervised speech model pretrained on 128 languages, feeding an AASIST graph
classifier. It reads the raw waveform, four seconds at a time, and answers with two
numbers, a "spoof" and a "bonafide" logit. Exported to ONNX it is 1.27 GB, and it runs
on our own server, so the sound of a forward is never sent anywhere.

What it costs, measured on the development machine with 4 threads: 8-48 s to load
(warm and cold disk), 1.3 GB resident afterwards and 1.45 GB at the peak, and
0.65-1.1 s for each four-second window, so 4.5-7 s for a 90-second clip, decoding
included. That is why it loads once per server and judges at most six windows.

Why it is shown only as an experimental estimate. Its makers report low error rates
on the English and Chinese benchmarks it was tuned for, but independent multilingual
tests put every open voice detector near chance: equal error rates of 40-50%, and
42.8% on Hindi for the best of them. A WhatsApp forward is also recompressed at a low
bitrate, often over music, which none of those benchmarks contain. So this module
reports a likelihood and the boundary its makers chose; it never reports "fake", and
what it says can never decide a verdict (app/media/synthetic.py turns it into an
advisory, the only form in which a detector's opinion leaves the media layer).

What it judges. Up to six four-second stretches of the first 90 seconds: those with
the most sound in them, skipping silence and steady hum, because a window of silence
tells the model nothing and costs as much to run as a window of speech. A clip with
no stretch that sounds like speech gets no score rather than a guess.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.media.detectors.common import model_path, onnx_session, sigmoid
from app.observability.logging import event

logger = logging.getLogger("factify.media.detectors.voice")

MODEL = ("spectra-aasist", "spectra-aasist.onnx")

RATE = 16_000
# 4.04 seconds: the length the model was trained on, and the length its makers crop
# or repeat every recording to before judging it.
WINDOW = 64_600
MAX_WINDOWS = 6

# The makers' preprocessing (their model card): a first-order pre-emphasis filter,
# y[t] = x[t] - 0.97 * x[t-1], on the whole recording before cropping. The ONNX
# graph starts at the encoder's first convolution (read from the file), so the filter
# is applied here. The model was trained without peak normalisation (its model.py
# passes normalize_waveform=False), so the level is left as it is.
PREEMPHASIS = 0.97

# The makers' decision boundary, on the bonafide logit alone: at or below it the
# model calls the window spoofed. Their card says -1.140625; the `classify()`
# default in their model.py says -1.0625009. The card is the documented one.
BONAFIDE_LOGIT_AT = -1.140625

# The model's two logits are near mirror images: spoof + bonafide stays close to this
# sum whatever the sound. Measured on 76 windows (a LibriVox audiobook, a LibriSpeech
# reading, two Windows text-to-speech voices): spoof = -0.987 * bonafide + 0.646,
# correlation -0.9999; the sum averaged 0.675 with a standard deviation of 0.054.
LOGIT_SUM = 0.675

# Loudness is measured over 25 ms frames. A frame is "sounding" above -45 dBFS -
# quieter than any voice meant to be heard, louder than a quiet room.
FRAME = 400
SOUNDING_DBFS = -45.0
# Frames below this are counted as this: digital silence is -inf dB, and one such
# frame would otherwise swamp every average it enters.
FLOOR_DBFS = -80.0
# A stretch counts as speech-like when at least 40% of its frames are sounding
# (speech pauses between phrases; a stretch that is mostly pause is not worth four
# seconds of CPU) and its loudness swings by at least 2 dB (standard deviation over
# frames): syllables rise and fall several times a second, while a hum, a hiss or a
# held tone stays within a fraction of a decibel. Set low on purpose: a 64 kbps
# audiobook, continuous narration over a noise floor, measured 3.9-4.7 dB, and a
# voice over background music swings less still. Music passes this test too, which
# is why the output is only ever "the model's estimate for this sound".
MIN_SOUNDING = 0.4
MIN_SWING_DB = 2.0
# Candidate windows start every half window (two seconds), and the chosen ones never
# overlap, so a clip of continuous speech can still be tiled edge to edge.
HOP = WINDOW // 2
# Anything shorter than a second is too little to judge; a clip between one and four
# seconds is repeated to fill a window, as the makers do.
MIN_SAMPLES = RATE

# Decoding a 90-second sound track takes well under a second; a container that makes
# ffmpeg spin is killed long before a request's own budget runs out. A longer read
# gets longer (`decode_timeout`): a background check hears up to ten minutes of a
# clip, and a fixed 30 s would have cut a slow, honest decode off with the rest.
DECODE_TIMEOUT_S = 30.0
DECODE_TIMEOUT_PER_SECOND = 0.05

# What ffmpeg says when a file has no sound track to map: "Stream map '0:a:0' matches
# no streams" (ffmpeg 8 prints the map as ''), or, for an optional map, that the
# output "does not contain any stream". Not translated: ffmpeg's messages are English.
_NO_SOUND_TRACK = ("matches no streams", "does not contain any stream")

SoundStatus = Literal["ok", "no_audio", "unavailable", "failed"]


@dataclass(frozen=True, slots=True)
class VoiceScore:
    """How likely the speech is to be machine-made, and the boundary to read it against.

    `likelihood` is the mean, over the windows judged, of each window's two-class
    softmax probability of "spoof". The mean rather than the maximum because a
    detector this close to chance on the audio we see would call almost every long
    clip suspicious if its single most suspicious window decided; the cost is that one
    spliced-in sentence inside a real speech is diluted by the rest.

    `threshold` is the makers' own boundary carried into the same probability scale
    (`_threshold`): about 0.95, because their rule calls a window spoofed only when it
    is that sure. A mean of probabilities reaches it only when nearly every window
    judged is one their `classify()` would call spoofed, so it is a boundary for
    raising a suspicion, not a line between "real" and "fake".
    """

    likelihood: float
    threshold: float
    seconds: float
    windows: int

    @property
    def raised(self) -> bool:
        return self.likelihood >= self.threshold


def _spoof_probability(spoof_logit: np.ndarray, bonafide_logit: np.ndarray) -> np.ndarray:
    """The softmax probability of "spoof": sigmoid(spoof_logit - bonafide_logit)."""
    # Clipped so an extreme logit saturates to 0 or 1 instead of overflowing exp().
    difference = np.clip(spoof_logit.astype(np.float64) - bonafide_logit, -60.0, 60.0)
    probability: np.ndarray = 1.0 / (1.0 + np.exp(-difference))
    return probability


def _threshold() -> float:
    """The makers' bonafide-logit boundary as a softmax "spoof" probability.

    Their rule looks at the bonafide logit only; a softmax looks at the difference of
    the two. On this model the two logits mirror each other (spoof = LOGIT_SUM -
    bonafide, measured), so the difference is LOGIT_SUM - 2 * bonafide, and the
    boundary on the bonafide logit becomes one on the probability:
    sigmoid(0.675 + 2 * 1.140625) = 0.951.
    """
    return sigmoid(LOGIT_SUM - 2.0 * BONAFIDE_LOGIT_AT)


THRESHOLD = _threshold()


def _preemphasised(samples: np.ndarray) -> np.ndarray:
    filtered = np.empty_like(samples)
    filtered[0] = samples[0]
    filtered[1:] = samples[1:] - PREEMPHASIS * samples[:-1]
    return filtered


def _frame_loudness(samples: np.ndarray) -> np.ndarray:
    """Loudness of each 25 ms frame in dBFS, floored at FLOOR_DBFS."""
    count = len(samples) // FRAME
    frames = samples[: count * FRAME].reshape(count, FRAME).astype(np.float64)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    return np.maximum(20.0 * np.log10(np.maximum(rms, 1e-12)), FLOOR_DBFS)


def _speech_like(loudness: np.ndarray) -> bool:
    if loudness.size == 0:
        return False
    sounding = float(np.mean(loudness >= SOUNDING_DBFS))
    return sounding >= MIN_SOUNDING and float(np.std(loudness)) >= MIN_SWING_DB


def select_windows(samples: np.ndarray, *, limit: int = MAX_WINDOWS) -> list[int]:
    """Where the loudest speech-like stretches start, loudest first, never overlapping.

    Loudness picks them because the voice is usually the loudest thing in a forward;
    the speech-like test (`_speech_like`) keeps silence and a steady hum out. For a
    clip no longer than one window the answer is [0] or nothing.
    """
    loudness = _frame_loudness(samples)
    if len(samples) <= WINDOW:
        return [0] if len(samples) >= MIN_SAMPLES and _speech_like(loudness) else []
    starts = list(range(0, len(samples) - WINDOW + 1, HOP))
    if starts[-1] != len(samples) - WINDOW:
        # The tail, so the last seconds are a candidate too.
        starts.append(len(samples) - WINDOW)
    per_window = WINDOW // FRAME
    candidates: list[tuple[float, int]] = []
    for start in starts:
        first = start // FRAME
        stretch = loudness[first : first + per_window]
        if _speech_like(stretch):
            # Mean power, not mean dB: a loud stretch with pauses outranks a quiet
            # one without, which is the ranking a listener would make.
            power = float(np.mean(np.power(10.0, stretch / 10.0)))
            candidates.append((power, start))
    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
    chosen: list[int] = []
    for _, start in candidates:
        if all(abs(start - other) >= WINDOW for other in chosen):
            chosen.append(start)
            if len(chosen) == limit:
                break
    return chosen


def decode_timeout(max_seconds: float) -> float:
    """How long decoding `max_seconds` of sound may take: 30 s, and 0.05 s a second
    more (34.5 s for the voice check's 90 seconds, 60 s for ten minutes)."""
    return DECODE_TIMEOUT_S + DECODE_TIMEOUT_PER_SECOND * max(0.0, max_seconds)


@dataclass(frozen=True, slots=True, eq=False)
class Sound:
    """A video's decoded sound, or why there is none.

    The voice check needs only the samples; the speech reader also needs to know why
    there are none, because "this video has no sound" is a full reading of it and
    "the sound could not be decoded" is a gap in one (`app/media/speech.py`).
    """

    status: SoundStatus
    # 16 kHz mono float32 in [-1, 1]; only when `status` is "ok".
    samples: np.ndarray | None = field(default=None, repr=False)
    reason: str | None = None


def decode_sound(video: bytes, *, max_seconds: float) -> Sound:
    """The first `max_seconds` of the first sound track, and what stopped it if not.

    "no_audio" when the file has no sound track (or one with nothing in it),
    "unavailable" when ffmpeg is not installed, "failed" when ffmpeg could not read the
    file or ran out of time. Never raises.

    The bytes go to a temporary file rather than ffmpeg's stdin because an MP4 whose
    index is written at the end (common from phone editors) cannot be read from a
    pipe. The file is deleted when the decode is done, whatever happened.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        logger.warning("ffmpeg is not installed; a video's sound cannot be judged")
        return Sound(status="unavailable", reason="ffmpeg is not installed")
    timeout = decode_timeout(max_seconds)
    try:
        # A file left behind on Windows (still held by a killed ffmpeg) is the
        # system's to clear; it is no reason to lose a decode that finished.
        with tempfile.TemporaryDirectory(
            prefix="factify-voice-", ignore_cleanup_errors=True
        ) as workspace:
            source = Path(workspace) / "input"
            source.write_bytes(video)
            # A fixed argument list, never a shell; the only path is one this process
            # made.
            command = [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-t",
                f"{max_seconds:.3f}",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(RATE),
                "-f",
                "s16le",
                "pipe:1",
            ]
            try:
                completed = subprocess.run(  # noqa: S603 - fixed arguments, no shell
                    command, capture_output=True, timeout=timeout, check=False
                )
            except subprocess.TimeoutExpired:
                # `run` has killed ffmpeg before raising; nothing is left running.
                logger.warning("decoding a video's sound exceeded %.0fs", timeout)
                return Sound(
                    status="failed", reason=f"decoding the sound took longer than {timeout:.0f}s"
                )
    except OSError as error:
        # The temporary file could not be written or ffmpeg could not be started.
        logger.warning("a video's sound could not be decoded: %s", type(error).__name__)
        return Sound(status="failed", reason="the sound could not be decoded")
    stderr = completed.stderr.decode("utf-8", "replace")
    if completed.returncode != 0:
        if any(marker in stderr for marker in _NO_SOUND_TRACK):
            # The commonest case and no failure: a screen recording, a GIF-like clip.
            return Sound(status="no_audio", reason="the video has no sound track")
        logger.debug("no sound decoded (ffmpeg exit %s): %s", completed.returncode, stderr[:300])
        return Sound(status="failed", reason="ffmpeg could not read the video's sound")
    if not completed.stdout:
        return Sound(status="no_audio", reason="the video's sound track is empty")
    pcm = np.frombuffer(completed.stdout[: len(completed.stdout) // 2 * 2], dtype="<i2")
    return Sound(status="ok", samples=pcm.astype(np.float32) / 32768.0)


def decode_audio(video: bytes, *, max_seconds: float) -> np.ndarray | None:
    """The first `max_seconds` of the first sound track as 16 kHz mono float32.

    None when ffmpeg is missing, the file has no sound track, or ffmpeg cannot read it:
    for the voice check all three mean "no sound to judge", and none is worth failing
    a check over. `decode_sound` says which it was.
    """
    return decode_sound(video, max_seconds=max_seconds).samples


class VoiceDetector:
    """Spectra-AASIST, loaded once and shared by every check on this server."""

    def __init__(self, *, directory: str, threads: int = 4) -> None:
        self._directory = directory
        self._threads = threads
        self._lock = threading.Lock()
        self._session: Any = None
        self._input_name = ""
        self._loaded = False

    @property
    def available(self) -> bool:
        """Whether the model can be used: downloaded, and not found broken on loading."""
        if self._loaded:
            return self._session is not None
        return model_path(self._directory, *MODEL) is not None

    def load(self) -> None:
        """Loads the model once. A missing or broken file leaves the detector
        unavailable, logged, rather than failing the check that asked."""
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            weights = model_path(self._directory, *MODEL)
            if weights is None:
                return
            started = time.perf_counter()
            try:
                session = onnx_session(weights, threads=self._threads)
                graph_input = session.get_inputs()[0]
            except Exception:
                # A half-downloaded or corrupt file: no voice check, and the check says
                # "not checked" rather than failing the whole video.
                logger.exception("voice model could not be loaded")
                return
            shape = list(graph_input.shape)
            if len(shape) != 2 or (isinstance(shape[1], int) and shape[1] != WINDOW):
                # A different export would be fed windows of the wrong length and answer
                # confidently about nothing; better no voice check at all.
                logger.error("voice model expects input %s, not (batch, %s)", shape, WINDOW)
                return
            self._session = session
            self._input_name = graph_input.name
            event(
                logger,
                "voice model loaded",
                module="media.detectors.voice",
                outcome="ok",
                model_id="spectra-aasist",
                latency_ms=round((time.perf_counter() - started) * 1000),
            )

    def score_video(self, video: bytes, *, max_seconds: float = 90.0) -> VoiceScore | None:
        """The likelihood for a video's sound; None when it has no sound track, nothing
        in it sounds like speech, or the model is not available."""
        if not self.available:
            return None
        samples = decode_audio(video, max_seconds=max_seconds)
        if samples is None:
            return None
        return self.score_audio(samples)

    def score_audio(self, samples: np.ndarray) -> VoiceScore | None:
        """The likelihood for 16 kHz mono float32 sound in [-1, 1]; None when nothing in
        it sounds like speech, or the model is not available."""
        audio = np.squeeze(np.asarray(samples, dtype=np.float32))
        if audio.ndim != 1:
            raise ValueError(f"expected mono samples, got shape {audio.shape}")
        audio = np.nan_to_num(audio)
        starts = select_windows(audio)
        if not starts:
            return None
        self.load()
        if self._session is None:
            return None
        filtered = _preemphasised(audio)
        if len(filtered) < WINDOW:
            # One short clip, repeated to fill the window, as the makers do.
            windows = [np.tile(filtered, -(-WINDOW // len(filtered)))[:WINDOW]]
            seconds = len(audio) / RATE
        else:
            windows = [filtered[start : start + WINDOW] for start in starts]
            seconds = len(windows) * WINDOW / RATE
        # One window per call: measured on this model, a batch of six took 5.1 s where
        # six single windows took 3.9 s, and a batch needs six windows' activations in
        # memory at once.
        logits = np.concatenate(
            [
                np.asarray(self._session.run(None, {self._input_name: window[None, :]})[0])
                for window in windows
            ]
        )
        # Index 0 is "spoof", index 1 "bonafide" (the model card).
        probabilities = _spoof_probability(logits[:, 0], logits[:, 1])
        return VoiceScore(
            likelihood=float(np.mean(probabilities)),
            threshold=THRESHOLD,
            seconds=round(seconds, 2),
            windows=len(windows),
        )
