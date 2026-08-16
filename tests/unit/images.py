"""Deterministic image fixtures for the media tests.

Built rather than checked in, so the suite carries no binary blobs and every test can
state exactly what makes two images the same or different.

Photograph-like on purpose: smooth gradients with structure and sensor-style noise.
Flat synthetic patterns hash unlike real photographs — a solid colour has almost no
DCT energy outside the DC term, so a pHash over one measures rounding error rather
than content, and a test built on that would prove nothing about the real input.

**These are for hashing and matcher logic only. They cannot be used to test CLIP.**
Measured with real weights, a recompressed copy of `original()` scores 0.9248 against
itself while `distinct()` scores 0.9491 — the same picture ranks below a different
one, because CLIP embeds semantic content and every image here is semantically "an
abstract picture with coloured shapes". Embedding verification is tested against real
photographs in tests/model/photographs.py, and the full measurement is in
docs/ops-notes.md.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def scene(
    seed: int,
    *,
    size: tuple[int, int] = (640, 480),
    subjects: int = 5,
) -> Image.Image:
    """A synthetic photograph: lit background, solid subjects, sensor noise."""
    width, height = size
    rng = _rng(seed)

    y, x = np.mgrid[0:height, 0:width].astype(np.float64)

    # A lit background — a broad gradient plus a soft falloff, as a real frame has.
    background = (
        90.0
        + 60.0 * (x / width)
        + 40.0 * (1.0 - ((y - height / 2) / (height / 2)) ** 2)
        + 25.0 * np.sin(x / (40.0 + seed % 17))
    )

    canvas = np.stack([background, background * 0.94, background * 0.86], axis=-1)

    # Subjects: opaque regions with their own tone, giving the frame real structure
    # at the scale pHash's low-frequency band actually looks at.
    for _ in range(subjects):
        cx, cy = rng.integers(0, width), rng.integers(0, height)
        radius = int(rng.integers(min(width, height) // 12, min(width, height) // 4))
        colour = rng.integers(20, 235, size=3).astype(np.float64)

        mask = ((x - cx) ** 2 + (y - cy) ** 2) < radius**2
        canvas[mask] = colour

    # Sensor noise, so the residual a noise map measures is not identically zero.
    canvas += rng.normal(0.0, 3.0, canvas.shape)

    return Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")


def encode(image: Image.Image, *, quality: int = 92, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, quality=quality)
    return buffer.getvalue()


def original(seed: int = 7) -> bytes:
    """The image as first published."""
    return encode(scene(seed))


def recycled(seed: int = 7) -> bytes:
    """The same photograph after a trip through social media.

    Downscaled and re-compressed hard — what actually happens to an image on its
    third forward. Byte-different from the original, visually the same picture, which
    is the whole case perceptual hashing exists to catch.
    """
    resized = scene(seed).resize((480, 360), Image.Resampling.LANCZOS)
    return encode(resized, quality=55)


def cropped(seed: int = 7) -> bytes:
    """The same photograph with its edges trimmed — the other common re-share."""
    image = scene(seed)
    width, height = image.size
    trimmed = image.crop(
        (int(width * 0.08), int(height * 0.08), int(width * 0.92), int(height * 0.92))
    )
    return encode(trimmed, quality=80)


def distinct(seed: int = 41) -> bytes:
    """A different photograph of the same kind of scene.

    Same generator, same style, different content. This is the hard negative: the
    case where a hash-only matcher would be most tempted to call a match, and the
    case the gate requires to produce none.
    """
    return encode(scene(seed))
