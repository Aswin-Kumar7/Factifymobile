"""What is said in a video, read on our own server.

A forwarded video usually makes its claim out loud - a voice over a still, a clip of
someone speaking - and until this existed only the words on one frame were read, so
a spoken claim was never checked (2026-09-30). The sound is decoded the way the voice
detector decodes it (`decode_sound`), and Whisper, through faster-whisper and
CTranslate2 (MIT, weights MIT), writes it down in the language it was spoken in.

What is read is text to check, exactly as a pasted message is: it goes through the
same claim extraction, anchoring and search. It is never evidence, and it never
decides anything on its own.

Whisper writes words where there are none - "Thank you for watching" over music is
its best known - so only stretches the voice-activity filter hears as speech are
read, and a stretch it is not sure holds speech is dropped.

What happened is said, not only what was heard (`SpeechOutcome`, contract 1.8). A
video with no sound, or with sound and no speech in it, has been read in full:
nothing was said. A reader that failed, or is not here, has not read it, and the
speech it missed may be the claim. The two used to look the same (None), so a failure
was never reported and the video was checked as if it were silent.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.media.detectors.voice import RATE, decode_sound
from app.observability.logging import event

logger = logging.getLogger("factify.media.speech")

# The part of a clip that is read. A forward is rarely longer; the rest of a long
# video is said to have not been read. A background check passes its own, longer
# window (`max_seconds`).
MAX_SECONDS = 180.0
# Less speech than this is not worth a claim.
MIN_SPEECH_SECONDS = 1.5
# A stretch the model is this sure holds no speech, and cannot read confidently, is
# dropped: Whisper's inventions over silence and music look like this.
NO_SPEECH_AT = 0.6
LOW_LOGPROB = -1.0
# The longest transcript kept: about three minutes of speech, and more for a longer
# read - 25 characters for each second heard (`max_characters`). Fast Hindi or
# English speech writes down to about 15 a second, so a whole ten-minute clip fits
# and a runaway transcript still stops somewhere.
MAX_CHARACTERS = 4000
CHARACTERS_PER_SECOND = 25

SpeechStatus = Literal["read", "no_speech", "no_audio", "failed", "unavailable"]


def max_characters(max_seconds: float) -> int:
    """The longest transcript kept from `max_seconds` of sound: at least 4000."""
    return max(MAX_CHARACTERS, int(CHARACTERS_PER_SECOND * max_seconds))


@dataclass(frozen=True, slots=True)
class Transcript:
    """What was said: the words, the language Whisper heard, and how much it heard."""

    text: str
    language: str | None
    language_confidence: float | None
    # How long the reading took, in seconds of processing - not how much was heard,
    # which is `audio_seconds`.
    seconds_read: float
    cut_off: bool = False
    # Seconds of the sound that were heard: the read window, or the clip if shorter;
    # up to the last stretch read when there was no time for the rest.
    audio_seconds: float | None = None
    # Reading stopped at its time limit (`read_video_outcome(time_limit=...)`), before
    # the end of the sound: `audio_seconds` says how far it got.
    timed_out: bool = False


class SpeechTimedOut(Exception):
    """No speech was read before the time limit: nothing can be said of the sound."""


@dataclass(frozen=True, slots=True)
class SpeechOutcome:
    """What reading a video's speech came to.

    - "read": something was said, and `transcript` holds it.
    - "no_speech": there is sound, and none of it is speech (music, noise, a
      breath). Read in full; nothing was said.
    - "no_audio": the video has no sound track. Read in full; nothing was said.
    - "failed": the sound could not be decoded, or the reader failed on it.
    - "unavailable": no reader here (the model, its library or ffmpeg is missing).

    Only the last two are a gap in what was read (`unread`). A transcript cut at the
    read window is a read, with `transcript.cut_off` set.
    """

    status: SpeechStatus
    transcript: Transcript | None = None
    # Seconds of sound heard; None when none could be decoded.
    audio_seconds: float | None = None
    # Why there is no transcript, as a short English phrase: for the log, and the
    # detail of a gap.
    reason: str | None = None

    @property
    def unread(self) -> bool:
        """Whether the speech, if there is any, was not read: a gap, not a silence."""
        return self.status in ("failed", "unavailable")


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
        """What is said in a video's first `max_seconds`, or None when nothing is.

        None too when the speech could not be read; `read_video_outcome` says which.
        """
        return self.read_video_outcome(video, max_seconds=max_seconds).transcript

    def read_video_outcome(
        self,
        video: bytes,
        *,
        max_seconds: float = MAX_SECONDS,
        time_limit: float | None = None,
        stop: threading.Event | None = None,
    ) -> SpeechOutcome:
        """What is said in a video's first `max_seconds`, and what stopped it when
        nothing is. Never raises: a reader that fails says so in the outcome.

        With `time_limit`, reading stops that many seconds after it began (decoding
        included) at the end of the stretch being read, and the transcript says how
        far it got (`Transcript.timed_out`): ten minutes of speech take minutes of
        CPU on the server's four cores, shared with everything else a check reads, and
        the person is waiting. `stop`, once set, stops it the same way: the check it
        was for was stopped, and a thread cannot be cancelled from outside.
        """
        deadline = time.perf_counter() + time_limit if time_limit is not None else None
        try:
            # A second more than the window, so a clip longer than it is known to be.
            sound = decode_sound(video, max_seconds=max_seconds + 1)
        except Exception as error:  # decode_sound does not raise; a backstop
            logger.exception("a video's sound could not be decoded")
            return SpeechOutcome(status="failed", reason=f"decoding failed ({_named(error)})")
        if sound.status == "unavailable":
            return SpeechOutcome(status="unavailable", reason=sound.reason)
        if sound.status == "no_audio":
            return SpeechOutcome(status="no_audio", audio_seconds=0.0, reason=sound.reason)
        if sound.status != "ok" or sound.samples is None:
            return SpeechOutcome(status="failed", reason=sound.reason)

        samples = sound.samples
        window = int(max_seconds * RATE)
        heard = round(min(len(samples), window) / RATE, 1)
        if len(samples) < RATE:
            # Under a second of sound holds no claim; it was heard in full all the same.
            return SpeechOutcome(
                status="no_speech", audio_seconds=heard, reason="less than a second of sound"
            )
        try:
            self.load()
        except Exception as error:
            logger.exception("the speech model could not be loaded")
            return SpeechOutcome(
                status="unavailable",
                audio_seconds=heard,
                reason=f"the speech model could not be loaded ({_named(error)})",
            )
        try:
            transcript = self.read(
                samples[:window],
                cut_off=len(samples) > window,
                max_seconds=max_seconds,
                deadline=deadline,
                stop=stop,
            )
        except SpeechTimedOut as late:
            return SpeechOutcome(status="failed", audio_seconds=heard, reason=str(late))
        except Exception as error:
            logger.exception("the video's speech could not be read")
            return SpeechOutcome(
                status="failed",
                audio_seconds=heard,
                reason=f"the speech reader failed ({_named(error)})",
            )
        if transcript is None:
            return SpeechOutcome(
                status="no_speech", audio_seconds=heard, reason="nothing in the sound is speech"
            )
        if transcript.timed_out:
            return SpeechOutcome(
                status="read", transcript=transcript, audio_seconds=transcript.audio_seconds
            )
        return SpeechOutcome(status="read", transcript=transcript, audio_seconds=heard)

    def read(
        self,
        samples: np.ndarray,
        *,
        cut_off: bool = False,
        max_seconds: float | None = None,
        deadline: float | None = None,
        stop: threading.Event | None = None,
    ) -> Transcript | None:
        """What is said in 16 kHz mono samples, or None when nothing is.

        The words are kept to `max_characters(max_seconds)`; with no window given, to
        that of the samples' own length.

        Whisper writes the sound down a stretch at a time, as its stretches are asked
        for, so reading can stop between two: at `deadline` (a `time.perf_counter()`
        moment) or once `stop` is set. What was read up to there is the transcript,
        `timed_out`, heard up to the end of its last stretch; with nothing read by
        then, `SpeechTimedOut`.
        """
        self.load()
        assert self._model is not None
        audio_seconds = round(len(samples) / RATE, 1)
        limit = max_characters(audio_seconds if max_seconds is None else max_seconds)
        began = time.perf_counter()
        timed_out = False
        reached = 0.0
        with self._lock:
            segments, info = self._model.transcribe(
                samples,
                vad_filter=True,
                beam_size=5,
                # Each stretch read on its own: carried over, one misheard line
                # becomes the next one's prompt and repeats.
                condition_on_previous_text=False,
            )
            kept = []
            for segment in segments:
                reached = max(reached, float(segment.end))
                if _speech(segment):
                    kept.append(segment)
                if (stop is not None and stop.is_set()) or (
                    deadline is not None and time.perf_counter() >= deadline
                ):
                    timed_out = reached < audio_seconds - 1.0
                    break
            close = getattr(segments, "close", None)
            if timed_out and close is not None:
                close()
        spoken = sum(segment.end - segment.start for segment in kept)
        text = " ".join(" ".join(segment.text.split()) for segment in kept).strip()
        seconds = round(time.perf_counter() - began, 1)
        event(
            logger,
            "speech read",
            module="media.speech",
            outcome=("cut_off" if timed_out else "ok") if text else "empty",
            provider="local",
            language=getattr(info, "language", None),
            speech_seconds=round(spoken, 1),
            audio_seconds=audio_seconds,
            heard_seconds=round(reached, 1) if timed_out else audio_seconds,
            characters=len(text),
            seconds=seconds,
        )
        if timed_out and (spoken < MIN_SPEECH_SECONDS or not text):
            raise SpeechTimedOut(
                f"there was no time to read its speech ({round(reached)} of "
                f"{round(audio_seconds)} s heard, nothing said)"
            )
        if spoken < MIN_SPEECH_SECONDS or not text:
            return None
        return Transcript(
            text=_clipped(text, limit),
            language=getattr(info, "language", None),
            language_confidence=getattr(info, "language_probability", None),
            seconds_read=seconds,
            cut_off=cut_off or timed_out or len(text) > limit,
            audio_seconds=round(reached, 1) if timed_out else audio_seconds,
            timed_out=timed_out,
        )


async def read_speech(
    reader: SpeechReader | None,
    video: bytes,
    *,
    max_seconds: float = MAX_SECONDS,
    time_limit: float | None = None,
) -> SpeechOutcome:
    """What is said in a video, read off the event loop; "unavailable" with no reader.

    Never raises: whatever goes wrong is a "failed" outcome, and the video is still
    checked from its frames. Within `time_limit` seconds when given
    (`SpeechReader.read_video_outcome`). Cancelled, it stops the reader at the end of
    the stretch it is on, rather than leave it reading for nobody.
    """
    if reader is None:
        return SpeechOutcome(status="unavailable", reason="speech is not read on this server")
    stop = threading.Event()
    options: dict[str, Any] = {"max_seconds": max_seconds}
    if time_limit is not None:
        options.update(time_limit=time_limit, stop=stop)
    try:
        return await asyncio.to_thread(reader.read_video_outcome, video, **options)
    except asyncio.CancelledError:
        stop.set()
        raise
    except Exception as error:
        logger.exception("the video's speech could not be read")
        return SpeechOutcome(status="failed", reason=f"the speech reader failed ({_named(error)})")


def _speech(segment: Any) -> bool:
    """Whether a stretch Whisper wrote is speech it heard, not words it made up."""
    return not (
        getattr(segment, "no_speech_prob", 0.0) >= NO_SPEECH_AT
        and getattr(segment, "avg_logprob", 0.0) <= LOW_LOGPROB
    )


def _clipped(text: str, limit: int) -> str:
    """The text cut to `limit` characters, at the last whole word that fits."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Back to a word boundary, unless that would throw much of it away (a script
    # written without spaces).
    word = cut.rsplit(" ", 1)[0]
    return word if len(word) >= limit * 0.9 else cut


def _named(error: BaseException) -> str:
    return type(error).__name__


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
