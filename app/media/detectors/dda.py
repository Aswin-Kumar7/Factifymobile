"""A second opinion on AI-made pictures: Dual Data Alignment (DDA), on the CPU.

Chen, Xi, Yan et al., "Dual Data Alignment Makes AI-Generated Image Detector Easier
Generalizable" (NeurIPS 2025 spotlight). Checkpoint `Junwei-Xi/Dual-Data-Alignment`
on Hugging Face, Apache-2.0; the network code is vendored in `dda_model/`.

Why a second detector, and why this one. Community Forensics (picture.py) learned
what generators' pictures look like from thousands of generators. DDA learned from
pairs instead: a real photograph and the same photograph passed through a
generator's autoencoder, aligned in pixels and in JPEG compression, so the only
difference left to learn is the generator's own trace - not the subject, the style or
the file format. Two detectors that learned different things agreeing means more than
either alone, and their disagreeing is worth showing too: independent tests find
detectors 20-40 points apart on the same generator (DailyBench, July 2026).

What it looks at: only the central 336 x 336 pixels, at the picture's own
resolution. Nothing is resized - shrinking smooths away the fine traces the model
reads, and it was trained on crops like this. On a large photograph it therefore
judges the middle; a picture smaller than 336 pixels is padded with black, exactly
as in DDA's training and inference code. Its authors' decision boundary is 0.5.

What it costs: a ViT-L (300 million parameters) in float32 - seconds of CPU per
picture where Community Forensics takes a fraction of one, and 1.2 GB of memory once
loaded (figures in `DdaDetector`). So it is loaded on first use, not at start-up.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.media.detectors.common import model_path, normalised, rgb

CHECKPOINT = ("dda", "DDA_ckpt.pth")

# DDA's inference transform (Inference/inference.py): CenterCrop(336), ToTensor,
# Normalize with CLIP's mean and deviation - DINOv2 is fed CLIP's statistics here
# because that is what DDA trained it with.
CROP = 336
MEAN = (0.48145466, 0.4578275, 0.40821073)
STD = (0.26862954, 0.26130258, 0.27577711)

# The authors report accuracy at a sigmoid output of 0.5; no calibration is published.
THRESHOLD = 0.5

logger = logging.getLogger("factify.media.detectors.dda")

# The normalised 1x3x336x336 picture in, the network's raw logit out.
Network = Callable[[np.ndarray], float]


@dataclass(frozen=True, slots=True)
class DdaScore:
    """DDA's probability that a generator made the picture, and its boundary."""

    likelihood: float
    threshold: float

    @property
    def raised(self) -> bool:
        return self.likelihood >= self.threshold


class DdaDetector:
    """DDA, loaded once on first use and shared by every check.

    Measured 2026-09-27 on the development machine (8-core Ryzen, Windows, float32):
    about 2.8 s per picture at 4 threads (1.9 s at 8, 6.4 s at 1); loading takes a
    few seconds from a warm disk cache and adds 1.2 GB of resident memory.
    """

    def __init__(self, *, directory: str, threads: int = 4) -> None:
        self._directory = directory
        self._threads = threads
        self._lock = threading.Lock()
        # One picture at a time: each call already uses `threads` cores, and two at
        # once would only fight over them while doubling the working memory.
        self._running = threading.Lock()
        self._network: Network | None = None
        self._loaded = False

    @property
    def available(self) -> bool:
        """Whether a score can be expected: the checkpoint is there, and, once a load
        has been tried, it worked."""
        if self._loaded:
            return self._network is not None
        return model_path(self._directory, *CHECKPOINT) is not None

    def load(self) -> None:
        """Read the checkpoint once. A missing, half-downloaded or corrupt file, or
        PyTorch not being installed, leaves the detector unavailable - logged, never
        raised, so the picture check says "not checked" rather than failing."""
        with self._lock:
            if self._loaded:
                return
            try:
                path = model_path(self._directory, *CHECKPOINT)
                if path is not None:
                    self._network = _load_network(path, threads=self._threads)
            except Exception:
                logger.exception("the DDA picture model could not be loaded")
                self._network = None
            finally:
                self._loaded = True

    def score(self, data: bytes) -> DdaScore | None:
        """The likelihood for one picture (JPEG, PNG, ...), or None when the model is
        not available or the bytes are not a picture it can read."""
        self.load()
        network = self._network
        if network is None:
            return None
        try:
            picture = rgb(data)
        except Exception as error:
            # Not a picture, truncated, or a decompression bomb: Pillow raises a
            # different type for each, and none of them is a reason to fail a check.
            logger.info("DDA could not read the picture: %r", error)
            return None
        with self._running:
            logit = network(prepared(picture))
        if math.isnan(logit):
            logger.warning("DDA returned no number for a picture")
            return None
        return DdaScore(likelihood=probability(logit), threshold=THRESHOLD)


def prepared(picture: Image.Image) -> np.ndarray:
    """The picture as the network's input: 1 x 3 x 336 x 336 float32, normalised."""
    return normalised(centre_crop(picture), mean=MEAN, std=STD)


def centre_crop(picture: Image.Image, size: int = CROP) -> Image.Image:
    """The central `size` x `size` pixels, padded with black where the picture is
    smaller - torchvision's `CenterCrop` on a PIL image, offsets and rounding
    included, so the same pixels reach the network as in DDA's own code.

    torchvision pads first (the extra pixel, when odd, on the right or bottom) and
    then crops at round((side - size) / 2) with Python's rounding. PIL's `crop`
    fills anything outside the picture with black, so both steps are one crop."""
    width, height = picture.size
    left, top = _offset(width, size), _offset(height, size)
    return picture.crop((left, top, left + size, top + size))


def _offset(side: int, size: int) -> int:
    if side < size:
        return -((size - side) // 2)
    return round((side - size) / 2.0)


def probability(logit: float) -> float:
    """The sigmoid, written so a very confident logit cannot overflow `math.exp`."""
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    tail = math.exp(logit)
    return tail / (1.0 + tail)


def _load_network(path: Path, *, threads: int) -> Network:
    """The real network, as a plain function of the prepared array.

    PyTorch is imported here, not at the top of the module: it is an optional
    dependency (`--extra models`), and a server without it must still start.
    `set_num_threads` is process-wide, so every PyTorch model in the process shares
    this setting."""
    import torch

    from app.media.detectors import dda_model

    torch.set_num_threads(threads)
    network = dda_model.load(path)

    def run(array: np.ndarray) -> float:
        with torch.inference_mode():
            return float(network(torch.from_numpy(array)).reshape(-1)[0])

    return run
