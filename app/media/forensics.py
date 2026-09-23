"""Forensic advisory panel (M37).

The visible forensic surface the problem statement expects, wired so it cannot decide
anything. Everything in this module returns `Advisory` — a Tier E object that shares
no base class with `Evidence`, so there is no function signature anywhere in the
codebase that would accept one of these where a citation belongs.

**Error-level analysis is deliberately absent, and this is not an oversight.** ELA
false-positives on recolouring, brightness adjustment, in-camera processing,
resampling and screenshots — which is precisely the input distribution here, since
most submissions arrive as a screenshot of a forward. It also cannot distinguish an
edit from naturally high-frequency content such as text and sharp edges, so a
screenshot of a WhatsApp message lights up in exactly the way a manipulated photograph
would. A persuasive-looking heatmap that is not diagnostic would reintroduce the
confident-wrong-answer failure through the interface, after the architecture went to
considerable trouble to exclude it from the engine. It is not implemented.

What is here instead:

  - **Noise inconsistency.** Sensor noise is roughly uniform across an authentic
    frame. A spliced region carries its own history. Reported as variance across
    blocks with a renderable map.
  - **Frequency-domain view.** The radial power spectrum. GAN and diffusion output has
    historically shown periodic artefacts from upsampling; heavy compression and
    resizing produce their own signatures. Shown, described, and not thresholded into
    a verdict.

Both are descriptive. Neither is calibrated against a labelled corpus, so neither
carries a number that could be quoted as an accuracy figure — there is no product
metric to misreport here because none is computed.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.domain.enums import SyntheticSignal
from app.domain.evidence import Advisory
from app.observability.logging import event

logger = logging.getLogger("factify.media.forensics")

PANEL_HEADER = (
    "Forensic signals — shown for transparency. These are not used in the verdict "
    "and cannot change it."
)

PROVIDER = "local_forensics"
VERSION = "2026.08.1"

# Block size for the noise map. 16px is small enough to localise a pasted face and
# large enough that per-block variance is not dominated by a handful of pixels.
BLOCK = 16


@dataclass(frozen=True, slots=True)
class NoiseMap:
    """Per-block noise energy, renderable as a heatmap."""

    blocks: tuple[tuple[float, ...], ...]
    mean: float
    spread: float

    @property
    def normalised(self) -> tuple[tuple[float, ...], ...]:
        """Scaled to 0-1 for rendering. Presentation only; nothing reads this."""
        flat = [value for row in self.blocks for value in row]
        if not flat:
            return ()
        low, high = min(flat), max(flat)
        span = high - low
        if span <= 0:
            return tuple(tuple(0.0 for _ in row) for row in self.blocks)
        return tuple(tuple((value - low) / span for value in row) for row in self.blocks)

    @property
    def description(self) -> str:
        """Plain-language, and hedged because the signal genuinely is ambiguous."""
        if self.mean <= 0:
            return "Noise could not be measured on this image."
        ratio = self.spread / self.mean
        if ratio > 1.2:
            return (
                "Noise levels vary considerably across this image. That can happen when "
                "regions come from different sources, but it also happens with heavy "
                "compression, mixed lighting, or a screenshot of another image."
            )
        return (
            "Noise levels are fairly consistent across this image. Consistency is "
            "expected in an unedited photograph, and it is also what re-compression "
            "produces — it does not confirm the image is unedited."
        )


@dataclass(frozen=True, slots=True)
class SpectrumProfile:
    """Radial power spectrum, renderable as a curve."""

    radial: tuple[float, ...]
    peak_ratio: float

    @property
    def description(self) -> str:
        if self.peak_ratio > 3.0:
            return (
                "The frequency profile shows pronounced periodic structure. Some image "
                "generators leave regular patterns from upsampling — so do JPEG blocking, "
                "screen capture, and resizing, which are far more common."
            )
        return (
            "The frequency profile shows no pronounced periodic structure. This is "
            "unremarkable and does not indicate the image is authentic."
        )


@dataclass(frozen=True, slots=True)
class ForensicPanel:
    """Everything the panel renders, plus the advisories it emits.

    There is no `verdict`, `score`, `is_fake` or `confidence` field, and there is no
    method that returns one. The only object type leaving here is `Advisory`.
    """

    header: str = PANEL_HEADER
    noise: NoiseMap | None = None
    spectrum: SpectrumProfile | None = None
    advisories: tuple[Advisory, ...] = field(default_factory=tuple)
    reason: str | None = None

    @property
    def rendered(self) -> bool:
        return self.noise is not None or self.spectrum is not None

    @property
    def caveat(self) -> str:
        return (
            "None of these signals can establish that content is authentic or fabricated. "
            "The verdict above is based only on cited sources."
        )


def _luminance(data: bytes, *, max_side: int = 512) -> np.ndarray:
    """Decode to greyscale, bounded. Analysis does not need full resolution."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            grey = image.convert("L")
            grey.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            return np.asarray(grey, dtype=np.float64)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"could not decode image: {exc}") from exc


def noise_map(pixels: np.ndarray, *, block: int = BLOCK) -> NoiseMap:
    """Per-block high-frequency energy.

    The high-pass step is a Laplacian difference: subtract each pixel's neighbourhood
    mean, leaving what varies locally. Sensor noise dominates that residual in an
    authentic frame.
    """
    padded = np.pad(pixels, 1, mode="edge")
    neighbourhood = (
        padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:]
    ) / 4.0
    residual = np.abs(pixels - neighbourhood)

    rows = residual.shape[0] // block
    cols = residual.shape[1] // block

    if rows == 0 or cols == 0:
        return NoiseMap(blocks=(), mean=0.0, spread=0.0)

    trimmed = residual[: rows * block, : cols * block]
    grid = trimmed.reshape(rows, block, cols, block).mean(axis=(1, 3))

    return NoiseMap(
        blocks=tuple(tuple(float(value) for value in row) for row in grid),
        mean=float(grid.mean()),
        spread=float(grid.std()),
    )


def spectrum_profile(pixels: np.ndarray, *, bins: int = 48) -> SpectrumProfile:
    """Azimuthally averaged power spectrum.

    Collapses the 2-D spectrum to a curve of energy against spatial frequency, which
    is the view in which upsampling artefacts and JPEG blocking are visible at all.
    """
    windowed = pixels - pixels.mean()
    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(windowed))) ** 2

    height, width = spectrum.shape
    centre_y, centre_x = height // 2, width // 2
    y, x = np.ogrid[:height, :width]
    radius = np.hypot(y - centre_y, x - centre_x).astype(np.int64)

    max_radius = min(centre_y, centre_x)
    if max_radius < 2:
        return SpectrumProfile(radial=(), peak_ratio=0.0)

    totals = np.bincount(radius.ravel(), weights=spectrum.ravel())
    counts = np.bincount(radius.ravel())
    averaged = (totals[:max_radius] / np.maximum(counts[:max_radius], 1))[1:]

    if averaged.size == 0:
        return SpectrumProfile(radial=(), peak_ratio=0.0)

    curve = np.log1p(averaged)
    step = max(1, curve.size // bins)
    binned = curve[: (curve.size // step) * step].reshape(-1, step).mean(axis=1)

    # How far the curve departs from a smooth falloff. Periodic upsampling artefacts
    # show as bumps; so does compression, which is why this is described, not scored.
    smoothed = np.convolve(binned, np.ones(5) / 5, mode="same")
    deviation = np.abs(binned - smoothed)
    peak_ratio = float(deviation.max() / deviation.mean()) if deviation.mean() > 0 else 0.0

    return SpectrumProfile(radial=tuple(float(v) for v in binned), peak_ratio=peak_ratio)


def analyse(data: bytes, *, artifact_ref: str | None = None) -> ForensicPanel:
    """Run the panel over one image or keyframe.

    Returns advisories and renderable maps. Nothing here returns a verdict, and
    disabling this call entirely changes no verdict and no strength score — which is
    the property the module's gate is written against.
    """
    try:
        pixels = _luminance(data)
    except ValueError as exc:
        return ForensicPanel(reason=str(exc))

    noise = noise_map(pixels)
    spectrum = spectrum_profile(pixels)

    advisories = (
        Advisory(
            id=f"adv:noise:{artifact_ref or 'inline'}",
            provider=PROVIDER,
            signal=SyntheticSignal.ADVISORY_SUSPICION
            if noise.mean > 0 and noise.spread / noise.mean > 1.2
            else SyntheticSignal.NO_SIGNAL,
            note=noise.description,
            provider_version=VERSION,
            artifact_ref=artifact_ref,
        ),
        Advisory(
            id=f"adv:spectrum:{artifact_ref or 'inline'}",
            provider=PROVIDER,
            signal=SyntheticSignal.ADVISORY_SUSPICION
            if spectrum.peak_ratio > 3.0
            else SyntheticSignal.NO_SIGNAL,
            note=spectrum.description,
            provider_version=VERSION,
            artifact_ref=artifact_ref,
        ),
    )

    event(
        logger,
        "forensic panel computed",
        module="media.forensics",
        outcome="ok",
        advisories=len(advisories),
        # Logged as a description, never as a score, so no dashboard can start
        # trending it as an accuracy figure.
        noise_variation=round(noise.spread / noise.mean, 3) if noise.mean > 0 else 0.0,
    )

    return ForensicPanel(noise=noise, spectrum=spectrum, advisories=advisories)


def analyse_keyframes(frames: list[bytes]) -> ForensicPanel:
    """Run the panel across video keyframes.

    One panel for the clip, built from the frame with the most to say. Per-frame
    panels would imply a temporal analysis this does not perform.
    """
    panels = [analyse(frame, artifact_ref=f"frame:{index}") for index, frame in enumerate(frames)]
    rendered = [panel for panel in panels if panel.rendered]

    if not rendered:
        return ForensicPanel(reason="no keyframe could be analysed")

    return max(
        rendered,
        key=lambda panel: sum(
            1 for a in panel.advisories if a.signal is SyntheticSignal.ADVISORY_SUSPICION
        ),
    )


# Deliberately not implemented, and kept as a name so the absence is legible rather
# than looking like something nobody got around to.
def error_level_analysis(data: bytes) -> None:
    """Not implemented. See the module docstring.

    ELA false-positives on the exact input distribution this product receives —
    screenshots, re-compressed forwards, recoloured images — and produces a heatmap
    persuasive enough to be believed. It is excluded by design, not by omission.
    """
    del data
    raise NotImplementedError(
        "error-level analysis is excluded by design: it false-positives on screenshots "
        "and re-compression, which is most of the input here, and its output looks "
        "authoritative enough to be believed anyway"
    )
