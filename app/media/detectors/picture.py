"""Was this picture made by an AI image generator? Community Forensics, retrained.

`Thermostatic/community-forensics-frontier-detector-2026-08` (MIT, August 2026): the
Community Forensics detector (Park and Owens, CVPR 2025; trained on 4,803
generators) fine-tuned on 40,000 pictures from the generators people use now -
GPT-Image, FLUX 1 and 2, Imagen 3 and 4, Seedream, Qwen-Image. A ViT-Small, 44 MB as
FP16 ONNX, a fraction of a second on a CPU.

Its low-quality continuation, trained on pictures shrunk to 32-256 pixels, reads
pictures too small for the main one. Both report one raw score; the maker's frozen
calibration turns it into a probability, and 0.65 is their "AI-made" boundary.

What the makers say it cannot do, and what this module therefore never claims:
find a small AI-made patch in a real photograph (it judges the whole picture), or
survive a picture shrunk and recompressed many times over. The numbers they publish
are their own, on a set also used to pick the model - which is why we measure it on
our own WhatsApp-forwarded pictures before trusting a threshold (tests/model).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.media.detectors.common import model_path, normalised, onnx_session, rgb, sigmoid

MAIN = ("cf-frontier", "community_forensics_frontier_fp16.onnx")
SMALL = ("cf-lowq", "community_forensics_low_quality_fp16.onnx")

logger = logging.getLogger("factify.media.detectors.picture")

# Pictures whose short side is below the model's own input size have been shrunk
# already; the low-quality model was trained for exactly those.
SMALL_BELOW = 384

# Below this there is too little left to judge. The low-quality model's own card:
# 58% of AI pictures caught at 128 px, 24% at 64 px. So a thumbnail is "too small to
# judge", never a score.
TOO_SMALL = 128

# A picture this much one flat colour is a text card or a screenshot, not a
# photograph - and the detector is not built for those: its makers list screenshots
# among its known weak spots. Measured 2026-09-28: plain text cards drawn by software
# scored 93% "AI-made"; no picture in the 108-picture test set, real or generated, was
# flatter than 0.85, and none of those scored wrongly. Share of pixels in the single
# commonest colour, at 8 levels per channel.
FLAT_AT = 0.86


def flatness(picture: Image.Image) -> float:
    """Share of the picture in its single commonest colour (8 levels a channel)."""
    small = picture.copy()
    small.thumbnail((256, 256))
    levels = np.asarray(small, dtype=np.uint16) // 32
    keys = (levels[..., 0] * 64 + levels[..., 1] * 8 + levels[..., 2]).reshape(-1)
    return float(np.bincount(keys, minlength=512).max() / max(1, keys.size))


@dataclass(frozen=True, slots=True)
class _Model:
    session: Any
    input_name: str
    size: int
    resize_short: int
    mean: tuple[float, ...]
    std: tuple[float, ...]
    slope: float
    intercept: float
    threshold: float
    name: str


def _load(directory: str, folder: str, file: str, *, threads: int) -> _Model | None:
    weights = model_path(directory, folder, file)
    config_file = model_path(directory, folder, "config.json")
    calibrator_file = model_path(directory, folder, "calibrator.json")
    if weights is None or config_file is None or calibrator_file is None:
        return None
    try:
        config = json.loads(Path(config_file).read_text(encoding="utf-8"))
        final = json.loads(Path(calibrator_file).read_text(encoding="utf-8"))["final"]
        session = onnx_session(weights, threads=threads)
    except Exception:
        # A half-downloaded or corrupt file: this model is not available, and the
        # check says "not checked" rather than failing the whole picture.
        logger.exception("picture model %s could not be loaded", folder)
        return None
    return _Model(
        session=session,
        input_name=session.get_inputs()[0].name,
        size=int(config["input_size"]),
        resize_short=int(config["resize_short_edge"]),
        mean=tuple(config["image_mean"]),
        std=tuple(config["image_std"]),
        slope=float(final["slope"]),
        intercept=float(final["intercept"]),
        threshold=float(final["target_threshold"]),
        name=folder,
    )


@dataclass(frozen=True, slots=True)
class PictureScore:
    """The calibrated likelihood that a generator made the picture, and which model said so."""

    likelihood: float
    threshold: float
    model: str

    @property
    def raised(self) -> bool:
        return self.likelihood >= self.threshold


class AiPictureDetector:
    """Community Forensics, main and low-quality, loaded once and shared."""

    def __init__(self, *, directory: str, threads: int = 4) -> None:
        self._directory = directory
        self._threads = threads
        self._lock = threading.Lock()
        self._main: _Model | None = None
        self._small: _Model | None = None
        self._loaded = False

    @property
    def available(self) -> bool:
        return model_path(self._directory, *MAIN) is not None

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._main = _load(self._directory, *MAIN, threads=self._threads)
            self._small = _load(self._directory, *SMALL, threads=self._threads)
            self._loaded = True

    def unjudgeable(self, data: bytes) -> str | None:
        """Why this picture cannot be judged, or None when it can."""
        picture = rgb(data)
        if min(picture.size) < TOO_SMALL:
            return "the picture is too small to judge"
        if flatness(picture) >= FLAT_AT:
            return "the picture is mostly flat colour, like a text card or a screenshot"
        return None

    def score(self, data: bytes) -> PictureScore | None:
        """The likelihood for one picture, or None when no model is loaded."""
        self.load()
        picture = rgb(data)
        if min(picture.size) < TOO_SMALL:
            return None
        model = self._small if min(picture.size) < SMALL_BELOW and self._small else self._main
        if model is None:
            return None
        tensor = normalised(_resized_and_cropped(picture, model), mean=model.mean, std=model.std)
        raw = float(model.session.run(None, {model.input_name: tensor})[0].reshape(-1)[0])
        return PictureScore(
            likelihood=sigmoid(model.slope * raw + model.intercept),
            threshold=model.threshold,
            model=model.name,
        )


def _resized_and_cropped(picture: Image.Image, model: _Model) -> Image.Image:
    """Short edge to `resize_short`, then the centre `size` x `size`: the model's own
    preprocessing, as its card states it."""
    width, height = picture.size
    scale = model.resize_short / min(width, height)
    resized = picture.resize(
        (max(model.size, round(width * scale)), max(model.size, round(height * scale))),
        Image.Resampling.BICUBIC,
    )
    left = (resized.width - model.size) // 2
    top = (resized.height - model.size) // 2
    return resized.crop((left, top, left + model.size, top + model.size))
