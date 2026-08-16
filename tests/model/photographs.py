"""Real photographs for the model-level media tests.

The synthetic fixtures in tests/unit/images.py are right for testing the *matcher* —
they make hash behaviour explicit and the suite carries no binaries. They are wrong
for testing CLIP, and measurably so: encoded with real weights, an abstract pattern
and a different abstract pattern score 0.9491, while the same pattern after
recompression scores 0.9248. CLIP embeds semantic content, so to it every one of
those images is "an abstract picture with coloured shapes" and the differences are
noise. A verification test built on them would report whatever the noise happened to
do that day.

So these tests need photographs. Rather than commit a few megabytes of binaries to
the repository, they are sourced from the machine and the tests skip when there are
none — a skip that names its reason is worth more than a green tick over meaningless
data.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# Directories that hold real photographs on a normal desktop. Wallpaper sets are ideal
# for this: varied outdoor and studio scenes at high resolution.
SEARCH_PATHS = (
    Path("C:/Windows/Web/Wallpaper"),
    Path("C:/Windows/Web/4K/Wallpaper"),
    Path("C:/Windows/Web/Screen"),
    Path("/usr/share/backgrounds"),
    Path("/usr/share/wallpapers"),
    Path.home() / "Pictures",
)


def encode(image: Image.Image, quality: int = 92) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _base(image: Image.Image) -> bytes:
    return encode(image.resize((640, 480), Image.Resampling.LANCZOS))


def find(limit: int = 8) -> list[bytes]:
    """Collect distinct photographs, as published-size JPEGs.

    Deduped by content and then by perceptual hash, because the same wallpaper ships
    under several filenames — counting those as different pictures would score a
    correct match as a false positive, which is precisely the error this suite is
    supposed to catch.
    """
    from app.media.hashing import phash

    candidates: list[Path] = []
    for root in SEARCH_PATHS:
        if root.exists():
            candidates.extend(sorted(root.rglob("*.jpg"))[:60])

    seen_bytes: set[str] = set()
    kept_hashes: list[object] = []
    photographs: list[bytes] = []

    for path in candidates:
        if len(photographs) >= limit:
            break
        try:
            raw = path.read_bytes()
        except OSError:
            continue

        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen_bytes:
            continue
        seen_bytes.add(digest)

        # An unreadable or exotic file is simply not a fixture. Narrow rather than
        # bare, so a genuine bug in _base surfaces instead of silently skipping.
        try:
            with Image.open(io.BytesIO(raw)) as opened:
                data = _base(opened.copy())
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            print(f"skipping {path.name}: {type(exc).__name__}")  # noqa: T201
            continue

        marker = phash(data)
        if any(marker.distance(other) <= 6 for other in kept_hashes):  # type: ignore[arg-type]
            continue

        kept_hashes.append(marker)
        photographs.append(data)

    return photographs


def recycled(data: bytes) -> bytes:
    """A photograph on its third forward: downscaled and recompressed hard."""
    with Image.open(io.BytesIO(data)) as image:
        return encode(image.resize((480, 360), Image.Resampling.LANCZOS), quality=55)


def screenshotted(data: bytes) -> bytes:
    """Re-encoded at a different size — what a screenshot of a post produces."""
    with Image.open(io.BytesIO(data)) as image:
        return encode(image.resize((720, 540), Image.Resampling.BICUBIC), quality=70)


def cropped(data: bytes) -> bytes:
    """Edges trimmed, the other common re-share transformation."""
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        box = (int(width * 0.08), int(height * 0.08), int(width * 0.92), int(height * 0.92))
        return encode(image.crop(box), quality=80)
