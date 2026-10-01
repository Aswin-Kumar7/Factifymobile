"""Perceptual hashing (M33 support). Pure, no dependencies beyond Pillow and numpy.

Implemented here rather than taken from a library for the same reason MinHash was:
the value has to serialise into a `bit(64)` column in a layout the Hamming index
understands, and this is machinery the correctness of media matching rests on.

Two hashes, because they fail differently:

**dHash** compares adjacent pixel brightnesses. It is robust to scaling, compression
and gamma shifts, and it is sensitive to crops — a cropped image shifts every
comparison. Cheap and good at "same picture, re-saved".

**pHash** takes the low-frequency DCT coefficients. It survives cropping and mild
rotation far better because low frequencies describe overall structure rather than
local detail, and it costs a 32×32 transform.

Both produce 64 bits. Neither identifies an image on its own — a 64-bit hash has
collisions, and the plan is explicit that a false media match is the worst failure
available here. They generate candidates; the embedding verifies them.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, UnidentifiedImageError

HASH_BITS = 64

# Hamming distance below which two hashes are worth comparing properly. Generous on
# purpose: this is a shortlist, and a candidate that survives to the embedding stage
# costs one comparison while a candidate never proposed is a match never found.
CANDIDATE_DISTANCE = 12


class HashFailed(Exception):
    """The image could not be hashed. Recorded, never guessed around."""


@dataclass(frozen=True, slots=True)
class PerceptualHash:
    """A 64-bit perceptual hash, comparable and storable."""

    bits: int
    algorithm: str

    def to_bit_string(self) -> str:
        """The literal a `bit(64)` column takes, MSB first."""
        return format(self.bits, f"0{HASH_BITS}b")

    @classmethod
    def from_bit_string(cls, value: str, algorithm: str = "dhash") -> PerceptualHash:
        return cls(bits=int(value, 2), algorithm=algorithm)

    def distance(self, other: PerceptualHash) -> int:
        """Hamming distance — the number of differing bits."""
        if self.algorithm != other.algorithm:
            raise ValueError(
                f"cannot compare {self.algorithm} with {other.algorithm}; the values "
                "describe different things"
            )
        return int((self.bits ^ other.bits).bit_count())


def _grayscale(data: bytes, size: tuple[int, int]) -> np.ndarray:
    """Decode, desaturate and resize. The common first step of both hashes."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            converted = image.convert("L").resize(size, Image.Resampling.LANCZOS)
            return np.asarray(converted, dtype=np.float64)
    except (UnidentifiedImageError, OSError) as exc:
        raise HashFailed(f"could not decode image: {exc}") from exc


def dhash(data: bytes) -> PerceptualHash:
    """Difference hash over a 9×8 grid.

    Nine columns give eight horizontal comparisons per row, so the result is exactly
    64 bits with no padding. Encodes gradient direction rather than absolute
    brightness, which is why it survives re-encoding and exposure changes.
    """
    pixels = _grayscale(data, (9, 8))
    difference = pixels[:, 1:] > pixels[:, :-1]

    bits = 0
    for value in difference.flatten():
        bits = (bits << 1) | int(value)

    return PerceptualHash(bits=bits, algorithm="dhash")


def phash(data: bytes) -> PerceptualHash:
    """Perceptual hash over the low-frequency DCT coefficients.

    The DC term at [0,0] is excluded: it encodes average brightness, which every
    image has and which carries no information about content. Including it would
    make dark images resemble each other.
    """
    pixels = _grayscale(data, (32, 32))

    transformed = _dct2(pixels)
    low_frequency = transformed[:8, :8].flatten()

    # Median of everything except the DC term.
    median = float(np.median(low_frequency[1:]))

    bits = 0
    for value in low_frequency:
        bits = (bits << 1) | int(value > median)

    return PerceptualHash(bits=bits, algorithm="phash")


def _dct2(matrix: np.ndarray) -> np.ndarray:
    """Two-dimensional DCT-II, built from the FFT numpy already provides.

    Avoids a scipy dependency for one transform. The even-symmetric extension turns
    an FFT into a DCT: mirror the signal, transform, and take the real part with the
    appropriate phase correction.
    """
    return _dct1(_dct1(matrix.T).T)


def _dct1(matrix: np.ndarray) -> np.ndarray:
    """DCT-II along the last axis."""
    length = matrix.shape[-1]
    extended = np.concatenate([matrix, matrix[..., ::-1]], axis=-1)
    spectrum = np.fft.rfft(extended, axis=-1)[..., :length]
    phase = np.exp(-1j * np.pi * np.arange(length) / (2 * length))
    return np.real(spectrum * phase)


@dataclass(frozen=True, slots=True)
class MediaFingerprint:
    """Every identifier computed for one image."""

    sha256: str
    dhash: PerceptualHash
    phash: PerceptualHash


def fingerprint(data: bytes) -> MediaFingerprint:
    """Compute every identifier for an image in one pass."""
    import hashlib

    return MediaFingerprint(
        sha256=f"sha256:{hashlib.sha256(data).hexdigest()}",
        dhash=dhash(data),
        phash=phash(data),
    )
