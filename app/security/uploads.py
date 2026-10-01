"""Upload validation and resource limits (M10).

Everything here runs **before** a parser sees the bytes. A decompression bomb, a
polyglot file or a mislabelled archive is cheap to reject at the header and expensive
to discover inside an image decoder.

Two rules that are easy to state and easy to violate later:

  - the declared content type is a claim by the uploader and is never trusted; the
    magic bytes decide;
  - EXIF GPS is removed before anything persists or is logged. It is the one field in
    a shared photograph that can put a person in a place, and we have no use for it.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import StrEnum

from PIL import Image, UnidentifiedImageError

# Pillow refuses very large images by default to prevent decompression bombs. The
# cap is raised to an explicit, documented number rather than disabled: a 50 MP
# ceiling is far above any real screenshot and far below anything that will exhaust
# a 1.5 GB container.
Image.MAX_IMAGE_PIXELS = 50_000_000

MAX_PIXELS = 50_000_000


class MediaKind(StrEnum):
    IMAGE = "image"
    PDF = "pdf"
    VIDEO = "video"
    UNKNOWN = "unknown"


class UploadRejected(Exception):
    """The upload will not be processed, and the reason is recorded."""

    def __init__(self, reason: str, *, kind: str = "invalid") -> None:
        self.reason = reason
        self.kind = kind
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class SniffResult:
    kind: MediaKind
    mime_type: str


# Magic-byte signatures. Deliberately a short list of things we actually parse:
# an unrecognised file is rejected rather than guessed at.
_SIGNATURES: tuple[tuple[bytes, str, MediaKind], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", MediaKind.IMAGE),
    (b"\x89PNG\r\n\x1a\n", "image/png", MediaKind.IMAGE),
    (b"GIF87a", "image/gif", MediaKind.IMAGE),
    (b"GIF89a", "image/gif", MediaKind.IMAGE),
    (b"BM", "image/bmp", MediaKind.IMAGE),
    (b"%PDF-", "application/pdf", MediaKind.PDF),
)


def sniff(data: bytes) -> SniffResult:
    """Identify content from its bytes, ignoring whatever the client claimed."""
    for signature, mime_type, kind in _SIGNATURES:
        if data.startswith(signature):
            return SniffResult(kind=kind, mime_type=mime_type)

    # Container formats need a couple of bytes of context rather than a prefix.
    if len(data) >= 12:
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return SniffResult(kind=MediaKind.IMAGE, mime_type="image/webp")
        if data[4:8] == b"ftyp":
            brand = data[8:12]
            if brand in (b"avif", b"avis"):
                return SniffResult(kind=MediaKind.IMAGE, mime_type="image/avif")
            if brand in (b"heic", b"heix", b"mif1"):
                return SniffResult(kind=MediaKind.IMAGE, mime_type="image/heic")
            return SniffResult(kind=MediaKind.VIDEO, mime_type="video/mp4")
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return SniffResult(kind=MediaKind.VIDEO, mime_type="video/webm")

    return SniffResult(kind=MediaKind.UNKNOWN, mime_type="application/octet-stream")


def validate_size(data: bytes, *, max_bytes: int) -> None:
    if not data:
        raise UploadRejected("upload is empty")
    if len(data) > max_bytes:
        raise UploadRejected(
            f"upload is {len(data)} bytes, over the {max_bytes} byte limit", kind="too_large"
        )


def validate_image(data: bytes, *, max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    """Check dimensions from the header, before any decode. Returns (width, height).

    `Image.open` reads only enough to populate the header, so a bomb is rejected on
    its declared dimensions rather than after allocating a buffer for them.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            image.verify()
    except Image.DecompressionBombError as exc:
        raise UploadRejected(f"decompression bomb: {exc}", kind="bomb") from exc
    except UnidentifiedImageError as exc:
        raise UploadRejected("not a decodable image", kind="invalid") from exc
    except OSError as exc:
        raise UploadRejected(f"corrupt image: {exc}", kind="invalid") from exc

    if width * height > max_pixels:
        raise UploadRejected(
            f"image is {width}x{height} ({width * height} pixels), over the "
            f"{max_pixels} pixel limit",
            kind="bomb",
        )

    return width, height


# EXIF tags carrying location. 0x8825 is the GPS IFD pointer; the rest are the
# individual fields as they appear once that block is flattened.
_GPS_IFD_TAG = 0x8825
_LOCATION_TAG_NAMES = frozenset(
    {
        "GPSInfo",
        "GPSLatitude",
        "GPSLongitude",
        "GPSAltitude",
        "GPSLatitudeRef",
        "GPSLongitudeRef",
        "GPSDestLatitude",
        "GPSDestLongitude",
    }
)


def has_location(data: bytes) -> bool:
    """Whether this image carries EXIF location. Used to report, never to store."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            exif = image.getexif()
            return _GPS_IFD_TAG in exif
    except (UnidentifiedImageError, OSError):
        return False


def strip_location(data: bytes) -> bytes:
    """Return the image with all EXIF removed.

    Everything goes, not only the GPS block. Orientation is applied to the pixels
    first so the image still displays correctly, and the rest of the metadata —
    device serial numbers, owner names, thumbnails that can differ from the visible
    image — has no role in verification and is not worth retaining.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
            transposed = _apply_orientation(image)

            buffer = io.BytesIO()
            # Saving without an `exif` argument writes no EXIF block at all.
            transposed.save(buffer, format=image_format)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise UploadRejected(f"could not re-encode image: {exc}", kind="invalid") from exc


def _apply_orientation(image: Image.Image) -> Image.Image:
    """Bake EXIF orientation into the pixels before discarding the metadata."""
    from PIL import ImageOps

    return ImageOps.exif_transpose(image) or image


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    """An upload that passed every check, with its location metadata already gone."""

    data: bytes
    kind: MediaKind
    mime_type: str
    byte_size: int
    width: int | None = None
    height: int | None = None
    location_stripped: bool = False


def validate_upload(
    data: bytes,
    *,
    max_bytes: int,
    declared_type: str | None = None,
    max_pixels: int = MAX_PIXELS,
) -> ValidatedUpload:
    """Run every pre-parse check and return sanitised bytes.

    `declared_type` is accepted only to be compared against reality — a mismatch is
    recorded, not honoured.
    """
    validate_size(data, max_bytes=max_bytes)
    sniffed = sniff(data)

    if sniffed.kind is MediaKind.UNKNOWN:
        raise UploadRejected(
            f"unrecognised file type (client declared {declared_type or 'nothing'})",
            kind="unsupported",
        )

    width = height = None
    payload = data
    stripped = False

    if sniffed.kind is MediaKind.IMAGE:
        width, height = validate_image(data, max_pixels=max_pixels)
        if has_location(data):
            payload = strip_location(data)
            stripped = True

    return ValidatedUpload(
        data=payload,
        kind=sniffed.kind,
        mime_type=sniffed.mime_type,
        byte_size=len(payload),
        width=width,
        height=height,
        location_stripped=stripped,
    )
