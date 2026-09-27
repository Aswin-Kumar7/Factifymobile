"""Our own detectors, behind the interface the hosted one had.

A picture is read by two AI-picture models (Community Forensics, retrained in August
2026, and DDA as the second opinion) and, when it shows faces, by the face-swap
model. A video is read from its keyframes - the picture models on a few frames
spread across the clip, the face model on the largest face in every frame - and its
sound by the voice model.

One inference at a time: the models share the CPU, and two checks running side by
side would each take as long as both.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from app.media.synthetic import FACE_SWAP_AT, SECOND_AT, VOICE_AT, SyntheticReading
from app.observability.logging import event

logger = logging.getLogger("factify.media.detectors")

# Frames of a clip the picture models read; the face model reads every keyframe.
PICTURE_FRAMES = 3
SECOND_OPINION_FRAMES = 2


class LocalDetector:
    """Community Forensics + DDA + GenD + Spectra-AASIST; any of them may be missing."""

    def __init__(
        self,
        *,
        pictures: Any,
        second: Any | None = None,
        faces: Any | None = None,
        voice: Any | None = None,
    ) -> None:
        self._pictures = pictures
        self._second = second
        self._faces = faces
        self._voice = voice
        self._busy = threading.Lock()

    def warm(self) -> None:
        """Load every model now, so the first picture does not wait for it."""
        for model in (self._pictures, self._second, self._faces, self._voice):
            if model is None:
                continue
            try:
                model.load()
            except Exception:
                logger.exception("a local detector could not be loaded")

    @property
    def models(self) -> tuple[str, ...]:
        names = [("community-forensics-2026-08", self._pictures), ("dda", self._second)]
        names += [("gend-pe-l", self._faces), ("spectra-aasist", self._voice)]
        return tuple(name for name, model in names if model is not None)

    async def read(self, image: bytes, *, mime: str = "image/jpeg") -> SyntheticReading:
        del mime
        return await asyncio.to_thread(self._read_picture, image)

    async def read_video(self, video: bytes, frames: list[bytes]) -> SyntheticReading:
        return await asyncio.to_thread(self._read_clip, video, frames)

    def _read_picture(self, image: bytes) -> SyntheticReading:
        with self._busy:
            main = self._pictures.score(image)
            if main is None:
                return SyntheticReading(reason="not checked: the picture is too small to judge")
            second = _safely(self._second, "score", image)
            faces = _safely(self._faces, "score", image)
        reading = self._reading(main=[main], second=[second] if second else [], faces=faces)
        _log("picture", reading)
        return reading

    def _read_clip(self, video: bytes, frames: list[bytes]) -> SyntheticReading:
        with self._busy:
            mains = [s for f in _spread(frames, PICTURE_FRAMES) if (s := self._pictures.score(f))]
            seconds = [
                s
                for f in _spread(frames, SECOND_OPINION_FRAMES)
                if (s := _safely(self._second, "score", f))
            ]
            faces = _safely(self._faces, "score_frames", frames)
            voice = _safely(self._voice, "score_video", video)
        if not mains:
            return SyntheticReading(
                reason="not checked: no frame of the video could be read",
                voice=voice.likelihood if voice else None,
                voice_at=voice.threshold if voice else VOICE_AT,
                on_server=True,
                models=self.models,
            )
        reading = self._reading(main=mains, second=seconds, faces=faces, voice=voice)
        _log("video", reading)
        return reading

    def _reading(
        self,
        *,
        main: list[Any],
        second: list[Any],
        faces: Any | None,
        voice: Any | None = None,
    ) -> SyntheticReading:
        # For a clip, the frame the models were surest was AI-made speaks for it.
        top = max(main, key=lambda s: s.likelihood)
        top_second = max(second, key=lambda s: s.likelihood) if second else None
        return SyntheticReading(
            generated=round(top.likelihood, 4),
            generated_at=top.threshold,
            second_opinion=round(top_second.likelihood, 4) if top_second else None,
            second_at=top_second.threshold if top_second else SECOND_AT,
            face_swap=(
                round(faces.likelihood, 4) if faces and faces.likelihood is not None else None
            ),
            face_swap_at=faces.threshold if faces else FACE_SWAP_AT,
            faces=faces.faces if faces else None,
            voice=round(voice.likelihood, 4) if voice else None,
            voice_at=voice.threshold if voice else VOICE_AT,
            on_server=True,
            models=self.models,
        )


def _safely(model: Any | None, method: str, *args: Any) -> Any | None:
    """One detector's answer, or None: a detector that fails takes nothing else down."""
    if model is None:
        return None
    try:
        return getattr(model, method)(*args)
    except Exception:
        logger.exception("local detector %s failed", type(model).__name__)
        return None


def _spread(frames: list[bytes], most: int) -> list[bytes]:
    if len(frames) <= most:
        return list(frames)
    step = (len(frames) - 1) / (most - 1)
    return [frames[int(index * step + 0.5)] for index in range(most)]


def _log(kind: str, reading: SyntheticReading) -> None:
    event(
        logger,
        "local detectors read",
        module="media.detectors",
        outcome="ok",
        provider="local",
        kind=kind,
        generated=reading.generated,
        second_opinion=reading.second_opinion,
        agreement=reading.outcome,
        faces=reading.faces,
        face_swap=reading.face_swap,
        voice=reading.voice,
    )


def build(settings: Any) -> LocalDetector | None:
    """The detectors whose files and libraries are present; None when not even the
    main picture model is."""
    from app.media.detectors.picture import AiPictureDetector

    local = settings.local
    if not local.pictures:
        return None
    pictures = AiPictureDetector(directory=local.directory, threads=local.threads)
    if not pictures.available:
        return None

    def optional(module: str, name: str, enabled: bool) -> Any | None:
        if not enabled:
            return None
        try:
            imported = __import__(f"app.media.detectors.{module}", fromlist=[name])
            model = getattr(imported, name)(directory=local.directory, threads=local.threads)
        except Exception:
            logger.exception("local detector %s is not available", name)
            return None
        return model if model.available else None

    return LocalDetector(
        pictures=pictures,
        second=optional("dda", "DdaDetector", local.pictures),
        faces=optional("faces", "FaceSwapDetector", local.faces),
        voice=optional("voice", "VoiceDetector", local.voice),
    )
