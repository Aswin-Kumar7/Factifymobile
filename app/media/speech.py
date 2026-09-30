"""What is said in a video, read on our own server.

A forwarded video usually makes its claim out loud - a voice over a still, a clip of
someone speaking - and until this existed only the words on one frame were read, so
a spoken claim was never checked (2026-09-30). The sound is decoded the way the voice
detector decodes it (`decode_audio`), and Whisper, through faster-whisper and
CTranslate2 (MIT, weights MIT), writes it down in the language it was spoken in.

What is read is text to check, exactly as a pasted message is: it goes through the
same claim extraction, anchoring and search. It is never evidence, and it never
decides anything on its own.

Whisper writes words where there are none - "Thank you for watching" over music is
its best known - so only stretches the voice-activity filter hears as speech are
read, and a stretch it is not sure holds speech is dropped.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.media.detectors.voice import RATE, decode_audio
from app.observability.logging import event

logger = logging.getLogger("factify.media.speech")

# The part of a clip that is read. A forward is rarely longer; the rest of a long
# video is said to have not been read.
MAX_SECONDS = 180.0
# Less speech than this is not worth a claim.
MIN_SPEECH_SECONDS = 1.5
# A stretch the model is this sure holds no speech, and cannot read confidently, is
# dropped: Whisper's inventions over silence and music look like this.
NO_SPEECH_AT = 0.6
LOW_LOGPROB = -1.0
# The longest transcript kept: about three minutes of speech.
MAX_CHARACTERS = 4000


@dataclass(frozen=True, slots=True)
class Transcript:
    """What was said: the words, the language Whisper heard, and how long it read."""

    text: str
    language: str | None
    language_confidence: float | None
    seconds_read: float
    cut_off: bool = False


class SpeechReader:
    """Whisper on our own server, loaded on the first video (like the voice model)."""

    def __init__(self, *, directory: str, model: str = "small", threads: int = 4) -> None:
        self._path = Path(directory) / f"faster-whisper-{model}"
        self._threads = threads
        self._model: Any | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        """Whether the model's files and the library are both here."""
        if not (self._path / "model.bin").exists():
            return False
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                str(self._path), device="cpu", compute_type="int8", cpu_threads=self._threads
            )

    def read_video(self, video: bytes, *, max_seconds: float = MAX_SECONDS) -> Transcript | None:
        """What is said in a video's first `max_seconds`, or None when nothing is."""
        samples = decode_audio(video, max_seconds=max_seconds + 1)
        if samples is None or len(samples) < RATE:
            return None
        cut_off = len(samples) > max_seconds * RATE
        return self.read(samples[: int(max_seconds * RATE)], cut_off=cut_off)

    def read(self, samples: np.ndarray, *, cut_off: bool = False) -> Transcript | None:
        """What is said in 16 kHz mono samples, or None when nothing is."""
        self.load()
        assert self._model is not None
        began = time.perf_counter()
        with self._lock:
            segments, info = self._model.transcribe(
                samples,
                vad_filter=True,
                beam_size=5,
                # Each stretch read on its own: carried over, one misheard line
                # becomes the next one's prompt and repeats.
                condition_on_previous_text=False,
            )
            kept = [segment for segment in segments if _speech(segment)]
        spoken = sum(segment.end - segment.start for segment in kept)
        text = " ".join(" ".join(segment.text.split()) for segment in kept).strip()
        seconds = round(time.perf_counter() - began, 1)
        event(
            logger,
            "speech read",
            module="media.speech",
            outcome="ok" if text else "empty",
            provider="local",
            language=getattr(info, "language", None),
            speech_seconds=round(spoken, 1),
            characters=len(text),
            seconds=seconds,
        )
        if spoken < MIN_SPEECH_SECONDS or not text:
            return None
        return Transcript(
            text=text[:MAX_CHARACTERS],
            language=getattr(info, "language", None),
            language_confidence=getattr(info, "language_probability", None),
            seconds_read=seconds,
            cut_off=cut_off or len(text) > MAX_CHARACTERS,
        )


def _speech(segment: Any) -> bool:
    """Whether a stretch Whisper wrote is speech it heard, not words it made up."""
    return not (
        getattr(segment, "no_speech_prob", 0.0) >= NO_SPEECH_AT
        and getattr(segment, "avg_logprob", 0.0) <= LOW_LOGPROB
    )


def build(settings: Any) -> SpeechReader | None:
    """The reader when it is switched on and its files are here; None otherwise."""
    local = settings.local
    if not local.speech:
        return None
    reader = SpeechReader(
        directory=local.directory, model=local.speech_model, threads=local.threads
    )
    if not reader.available:
        logger.warning("speech in videos is not read: %s is missing", reader._path)
        return None
    return reader
