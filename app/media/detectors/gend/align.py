"""The face crop GenD was trained on: turned upright on five landmarks, 1.3x the face.

Adapted from `align_face` in `detector.py` of https://github.com/yermandy/GenD (MIT
licence, copyright (c) 2025 Andy; see LICENSE in this folder). Every training and test
face they used was cut this way - eyes, nose tip and mouth corners moved onto a fixed
template, with 30% of the face's size again as context - so a face cut any other way
is not what the model learned to read.

Their version uses OpenCV (`estimateAffinePartial2D` with LMedS, then `warpAffine`).
Here the same similarity transform is a least-squares fit in NumPy and the warp is
Pillow's: with five good landmarks the two agree to a fraction of a pixel, the fit is
deterministic where LMedS samples at random, and the crop can be tested without
OpenCV installed.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# Where the eyes, nose tip and mouth corners sit in their aligned face, as fractions
# of its width and height; left and right as seen in the picture.
TEMPLATE = np.array(
    [[0.34, 0.46], [0.66, 0.46], [0.5, 0.64], [0.37, 0.82], [0.63, 0.82]],
    dtype=np.float64,
)

SCALE = 1.3


def crop_size(landmarks: np.ndarray, *, scale: float = SCALE) -> int:
    """The side of the square crop: the face's own size, with the context added.

    Their `target_size=None` path, the one their datasets were made with: the mean
    ratio of every landmark-to-landmark distance to the template's, so the crop
    keeps the face at the resolution the picture had.
    """
    points = np.asarray(landmarks, dtype=np.float64).reshape(5, 2)
    upper = np.triu_indices(5, k=1)
    found = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=-1)[upper]
    template = np.linalg.norm(TEMPLATE[:, None, :] - TEMPLATE[None, :, :], axis=-1)[upper]
    return max(1, round(float(np.mean(found / template)) * scale))


def similarity(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """The 2x3 rotation + uniform scale + shift that best moves `source` onto `target`."""
    rows = []
    values = []
    for (x, y), (u, v) in zip(source, target, strict=True):
        rows.append([x, -y, 1.0, 0.0])
        values.append(u)
        rows.append([y, x, 0.0, 1.0])
        values.append(v)
    a, b, tx, ty = np.linalg.lstsq(np.array(rows), np.array(values), rcond=None)[0]
    return np.array([[a, -b, tx], [b, a, ty]], dtype=np.float64)


def align_face(image: Image.Image, landmarks: np.ndarray, *, scale: float = SCALE) -> Image.Image:
    """The face as a square crop, template-aligned; outside the picture is black, as
    in theirs."""
    points = np.asarray(landmarks, dtype=np.float64).reshape(5, 2)
    size = crop_size(points, scale=scale)
    # Their margin arithmetic, solved: the template is laid out in a (size / scale)
    # square and centred in the size x size crop.
    target = (TEMPLATE + (scale - 1.0) / 2.0) * size / scale
    forward = np.vstack([similarity(points, target), [0.0, 0.0, 1.0]])
    # Pillow asks, for each pixel of the crop, where to read from in the picture.
    inverse = np.linalg.inv(forward)[:2].reshape(-1)
    return image.transform(
        (size, size),
        Image.Transform.AFFINE,
        tuple(float(value) for value in inverse),
        resample=Image.Resampling.BILINEAR,
    )
