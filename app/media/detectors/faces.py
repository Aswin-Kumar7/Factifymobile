"""Was a face in this picture or video swapped or AI-modified? GenD, on faces YuNet finds.

GenD (Yermakov, Cech, Matas and Fritz, WACV 2026; MIT) is a Perception Encoder
Large of which only the LayerNorms - 0.03% of the weights - were fine-tuned, with the
features held on a sphere so real and fake stay apart on manipulations it never saw.
Its authors test it on fourteen benchmarks from 2019 to 2025 rather than the one it
was trained on, which is the claim that matters here: what a person forwards us was
seldom made by a method in anyone's training set. The code it needs is vendored in
`gend/` (why, and what changed, is written there).

It judges a face, not a picture. So YuNet (OpenCV zoo, MIT) finds the faces first,
and each one is cut exactly as GenD's own pipeline cut its training faces: turned
upright on five landmarks, with 30% of the face again as context. A picture with no
face we can find says "no face", never "no swap"; faces under 48 px are skipped, as
there is too little left of them to judge; at most five, largest first, are read.

How the per-face estimates become one:

  - a picture: the highest. One swapped face among five real ones is still a picture
    with a swapped face in it;
  - a video: the largest face in each keyframe (their video pipeline's rule - it is
    nearly always the person the clip is about), at most 12 frames, and the mean of
    the three highest. A single blurred or half-turned frame cannot decide a clip on
    its own, and a swap that shows in only part of it is not averaged away.

The boundary is 0.5 because the model has none of its own: a two-way softmax whose
makers report AUROC and equal-error rates, never a calibrated threshold. Like every
detector here the number is an estimate shown beside a verdict, never inside it; how
far the display boundary sits above 0.5 is decided where it is shown
(`app/media/synthetic.py`).

What it cannot tell: a picture made whole by a generator with no swapped face (the
AI-picture detector's question), or a face too small, turned away or covered to find.
And, as the package notes say of every detector, a face recompressed through several
forwards reads less reliably than the benchmark faces it was measured on.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.media.detectors.common import model_path, rgb
from app.media.detectors.gend.align import align_face

YUNET = ("yunet", "face_detection_yunet_2023mar.onnx")
GEND = ("gend-pe-l", "model.safetensors")
GEND_CONFIG = ("gend-pe-l", "config.json")

# What `gend-pe-l/config.json` says, for when it is missing: the checkpoint's keys are
# those of this backbone and head, and nothing else loads into them.
BACKBONE = "vit_pe_core_large_patch14_336"
HEAD = "LinearNorm"

THRESHOLD = 0.5

# Smaller faces than this are skipped, not judged.
MIN_FACE = 48
MAX_FACES = 5
MAX_FRAMES = 12
TOP_FRAMES = 5
# Faces judged per video frame: the swapped face is not always the largest one.
FACES_PER_FRAME = 3

# YuNet searches a copy no larger than this. It misses faces under about 25 px, so
# the copy must keep a MIN_FACE face at half its size or more. Measured on a
# 4000 x 3000 photograph: at 960 px even a 96 px face was lost; at 1920 px a 64 px
# face is found, in about 130 ms against 500 ms at full size.
DETECT_SIDE = 1920
# OpenCV's demo uses 0.9 and GenD's app 0.5 (with RetinaFace). A face model shown a
# shoulder or a poster still returns a number, and that number means nothing, so a
# missed face ("no face") is the cheaper error.
FACE_CONFIDENCE = 0.8
FACE_NMS = 0.3

# Faces judged per forward pass: more buys little on a CPU and costs memory.
BATCH = 4

logger = logging.getLogger("factify.media.detectors.faces")


@dataclass(frozen=True, slots=True)
class Face:
    """One face YuNet found: its box (x, y, width, height) and five landmarks - eyes,
    nose tip, mouth corners, left to right as seen - in the picture's own pixels."""

    box: tuple[float, float, float, float]
    landmarks: np.ndarray
    confidence: float

    @property
    def area(self) -> float:
        return self.box[2] * self.box[3]

    @property
    def side(self) -> float:
        return min(self.box[2], self.box[3])


@dataclass(frozen=True, slots=True)
class FaceScore:
    """How likely it is that a face was swapped or AI-modified, over the faces judged."""

    faces: int
    likelihood: float | None
    threshold: float

    @property
    def raised(self) -> bool:
        return self.likelihood is not None and self.likelihood >= self.threshold


Finder = Callable[[Image.Image], list[Face]]
Judge = Callable[[list[Image.Image]], list[float]]


class FaceSwapDetector:
    """YuNet and GenD, loaded once and shared; one check runs through them at a time."""

    def __init__(self, *, directory: str, threads: int = 4) -> None:
        self._directory = directory
        self._threads = threads
        self._lock = threading.Lock()
        # The model is given every thread it may use; two checks at once would only
        # fight over them and hold two batches of activations in memory.
        self._running = threading.Lock()
        self._finder: Finder | None = None
        self._judge: Judge | None = None
        self._failed = False

    @property
    def available(self) -> bool:
        return not self._failed and self._files() is not None and _libraries_installed()

    def load(self) -> None:
        with self._lock:
            if self._judge is not None or self._failed:
                return
            files = self._files()
            if files is None or not _libraries_installed():
                # Not a failure: the weights may still be downloading.
                return
            yunet, weights = files
            backbone, head = _config(self._directory)
            try:
                finder = _load_finder(yunet)
                judge = _load_judge(weights, backbone=backbone, head=head, threads=self._threads)
            except Exception:
                # The check then says "not checked", never "no swap".
                logger.exception("face-swap model could not be loaded")
                self._failed = True
                return
            self._finder, self._judge = finder, judge

    def score(self, data: bytes) -> FaceScore | None:
        """The highest estimate over up to five faces in one picture; None when the
        detector is unavailable or the picture cannot be read."""
        self.load()
        finder, judge = self._finder, self._judge
        if finder is None or judge is None:
            return None
        picture = _decoded(data)
        if picture is None:
            return None
        with self._running:
            faces = _faces(finder, picture, limit=MAX_FACES)
            if not faces:
                return FaceScore(faces=0, likelihood=None, threshold=THRESHOLD)
            scores = judge([align_face(picture, face.landmarks) for face in faces])
        return FaceScore(faces=len(scores), likelihood=max(scores), threshold=THRESHOLD)

    def score_frames(self, frames: list[bytes]) -> FaceScore | None:
        """A clip's estimate: each frame's most swapped-looking face, the mean of the
        five highest frames.

        Measured on 50 real and 50 face-swapped videos (Google's DeepFakeDetection,
        2026-09-30). The largest face of three keyframes, mean of the top three, caught
        13 of 25 swaps. A swap shows in some frames and not others - one read 1-15% in
        thirteen frames of sixteen and 78-100% in three - and not always on the largest
        face. Every face of up to three per frame, each read as it is and mirrored
        (the higher kept), over eight evenly spaced frames, the mean of the top five:
        39 of 50 swaps past 0.9 and none of 50 real videos, alike on both halves.
        """
        self.load()
        finder, judge = self._finder, self._judge
        if finder is None or judge is None:
            return None
        with self._running:
            crops: list[Image.Image] = []
            owners: list[int] = []
            # One frame decoded at a time, and only its face crops kept.
            for index, data in enumerate(_spread(frames, MAX_FRAMES)):
                picture = _decoded(data)
                if picture is None:
                    continue
                for face in _faces(finder, picture, limit=FACES_PER_FRAME):
                    crop = align_face(picture, face.landmarks)
                    crops += [crop, crop.transpose(Image.Transpose.FLIP_LEFT_RIGHT)]
                    owners += [index, index]
            if not crops:
                return FaceScore(faces=0, likelihood=None, threshold=THRESHOLD)
            scores = judge(crops)
        per_frame: dict[int, float] = {}
        for owner, score in zip(owners, scores, strict=True):
            per_frame[owner] = max(per_frame.get(owner, 0.0), score)
        top = sorted(per_frame.values(), reverse=True)[:TOP_FRAMES]
        return FaceScore(faces=len(crops) // 2, likelihood=sum(top) / len(top), threshold=THRESHOLD)

    def _files(self) -> tuple[Path, Path] | None:
        yunet = model_path(self._directory, *YUNET)
        weights = model_path(self._directory, *GEND)
        if yunet is None or weights is None or not _complete(weights):
            return None
        return yunet, weights


def _faces(finder: Finder, picture: Image.Image, *, limit: int) -> list[Face]:
    """The faces large enough to judge, largest first."""
    found = [face for face in finder(picture) if face.side >= MIN_FACE]
    return sorted(found, key=lambda face: face.area, reverse=True)[:limit]


def _spread[T](items: Sequence[T], most: int) -> list[T]:
    """At most `most` of them, evenly spaced, the first and last included."""
    if len(items) <= most:
        return list(items)
    step = (len(items) - 1) / (most - 1)
    return [items[round(index * step)] for index in range(most)]


def _decoded(data: bytes) -> Image.Image | None:
    try:
        return rgb(data)
    except (OSError, ValueError, Image.DecompressionBombError):
        logger.warning("face check: a picture could not be read")
        return None


def _config(directory: str) -> tuple[str, str]:
    path = model_path(directory, *GEND_CONFIG)
    if path is None:
        return BACKBONE, HEAD
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        return str(config.get("backbone", BACKBONE)), str(config.get("head", HEAD))
    except (OSError, ValueError):
        return BACKBONE, HEAD


def _complete(path: Path) -> bool:
    """Whether the safetensors file is all there. `model_path` only asks that a file
    exists, and a 1.3 GB download in progress exists long before it is usable."""
    return _complete_at(str(path), path.stat().st_size)


@functools.lru_cache(maxsize=8)
def _complete_at(path: str, size: int) -> bool:
    try:
        with open(path, "rb") as file:
            length = int.from_bytes(file.read(8), "little")
            if not 0 < length <= min(size - 8, 100_000_000):
                return False
            header = json.loads(file.read(length))
        end = max(
            (entry["data_offsets"][1] for key, entry in header.items() if key != "__metadata__"),
            default=0,
        )
        return 8 + length + int(end) == size
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return False


@functools.cache
def _libraries_installed() -> bool:
    """`uv sync --extra models`: OpenCV for YuNet, PyTorch and timm for GenD."""
    return all(
        importlib.util.find_spec(name) is not None
        for name in ("cv2", "torch", "timm", "safetensors")
    )


def _load_finder(path: Path) -> Finder:
    import cv2

    detector = cv2.FaceDetectorYN.create(
        str(path), "", (320, 320), score_threshold=FACE_CONFIDENCE, nms_threshold=FACE_NMS
    )

    def find(picture: Image.Image) -> list[Face]:
        width, height = picture.size
        factor = min(1.0, DETECT_SIDE / max(width, height))
        searched = picture
        if factor < 1.0:
            size = (max(1, round(width * factor)), max(1, round(height * factor)))
            searched = picture.resize(size, Image.Resampling.BILINEAR)
        scale = np.array([width / searched.width, height / searched.height])
        bgr = np.ascontiguousarray(np.asarray(searched)[:, :, ::-1])
        detector.setInputSize(searched.size)
        _, rows = detector.detect(bgr)
        # No face comes back as None, whatever OpenCV's type hints say.
        if rows is None or len(rows) == 0:
            return []
        faces = []
        for row in rows:
            x, y = row[0:2] * scale
            w, h = row[2:4] * scale
            faces.append(
                Face(
                    box=(float(x), float(y), float(w), float(h)),
                    landmarks=row[4:14].reshape(5, 2).astype(np.float64) * scale,
                    confidence=float(row[14]),
                )
            )
        return faces

    return find


def _load_judge(weights: Path, *, backbone: str, head: str, threads: int) -> Judge:
    import torch

    from app.media.detectors.gend.modeling import FAKE, load

    torch.set_num_threads(threads)
    model = load(weights, backbone=backbone, head=head)

    def judge(crops: list[Image.Image]) -> list[float]:
        scores: list[float] = []
        with torch.inference_mode():
            for start in range(0, len(crops), BATCH):
                batch = torch.stack(
                    [model.preprocess(crop) for crop in crops[start : start + BATCH]]
                )
                scores.extend(float(p) for p in model(batch).softmax(dim=-1)[:, FAKE])
        return scores

    return judge
