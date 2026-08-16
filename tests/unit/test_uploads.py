"""M10 — hostile files are rejected before a parser sees them, and GPS never lands."""

from __future__ import annotations

import io
import zlib

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.security.uploads import (
    MediaKind,
    UploadRejected,
    has_location,
    sniff,
    strip_location,
    validate_image,
    validate_size,
    validate_upload,
)

pytestmark = pytest.mark.unit


def _png(width: int = 8, height: int = 8) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_with_gps() -> bytes:
    """A JPEG carrying EXIF GPS, built the way a phone camera would write it."""
    image = Image.new("RGB", (16, 16), "blue")
    exif = image.getexif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (IFDRational(28), IFDRational(36), IFDRational(0))  # 28°36'N — New Delhi
    gps[3] = "E"
    gps[4] = (IFDRational(77), IFDRational(12), IFDRational(0))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


class TestSniffing:
    """The declared type is a claim by the uploader; the magic bytes decide."""

    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            (b"\xff\xd8\xff\xe0rest", MediaKind.IMAGE),
            (b"\x89PNG\r\n\x1a\nrest", MediaKind.IMAGE),
            (b"GIF89a rest", MediaKind.IMAGE),
            (b"%PDF-1.7 rest", MediaKind.PDF),
            (b"RIFF\x00\x00\x00\x00WEBPrest", MediaKind.IMAGE),
            (b"\x00\x00\x00\x18ftypmp42rest", MediaKind.VIDEO),
        ],
    )
    def test_recognised_formats(self, data: bytes, expected: MediaKind) -> None:
        assert sniff(data).kind is expected

    def test_a_php_file_named_as_a_jpeg_is_not_an_image(self) -> None:
        """The classic upload bypass: a benign extension over hostile content."""
        result = sniff(b"<?php system($_GET['c']); ?>")

        assert result.kind is MediaKind.UNKNOWN

    def test_an_unrecognised_file_is_rejected_rather_than_guessed_at(self) -> None:
        with pytest.raises(UploadRejected, match="unrecognised"):
            validate_upload(b"not any known format", max_bytes=1024, declared_type="image/png")


class TestSizeAndBombs:
    def test_an_empty_upload_is_rejected(self) -> None:
        with pytest.raises(UploadRejected, match="empty"):
            validate_size(b"", max_bytes=1024)

    def test_an_oversized_upload_is_rejected(self) -> None:
        with pytest.raises(UploadRejected, match="over the"):
            validate_size(b"x" * 2048, max_bytes=1024)

    def test_dimensions_are_checked_before_decoding(self) -> None:
        """A bomb is refused on its declared size, not after allocating for it."""
        with pytest.raises(UploadRejected, match="pixel limit"):
            validate_image(_png(4000, 4000), max_pixels=1000)

    def test_a_decompression_bomb_png_is_rejected(self) -> None:
        """A tiny file declaring enormous dimensions — the whole point of the attack.

        A 60000x60000 PNG compresses to a few hundred bytes and expands to ~10 GB.
        """
        header = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\rIHDR"
            + (60000).to_bytes(4, "big")
            + (60000).to_bytes(4, "big")
            + b"\x08\x02\x00\x00\x00"
        )
        header += zlib.crc32(header[12:]).to_bytes(4, "big")

        with pytest.raises(UploadRejected):
            validate_image(header)

    def test_a_corrupt_image_is_rejected_without_crashing(self) -> None:
        with pytest.raises(UploadRejected):
            validate_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)

    def test_a_normal_image_passes(self) -> None:
        assert validate_image(_png(64, 48)) == (64, 48)


class TestLocationStripping:
    def test_gps_is_detected(self) -> None:
        assert has_location(_jpeg_with_gps())

    def test_gps_is_removed(self) -> None:
        """The one field in a shared photograph that places a person somewhere."""
        stripped = strip_location(_jpeg_with_gps())

        assert not has_location(stripped)

    def test_the_stripped_bytes_are_what_get_stored(self) -> None:
        """Validation returns sanitised bytes, so the original cannot leak by default."""
        validated = validate_upload(_jpeg_with_gps(), max_bytes=10_000_000)

        assert validated.location_stripped
        assert not has_location(validated.data)

    def test_an_image_without_location_is_left_alone(self) -> None:
        validated = validate_upload(_png(), max_bytes=10_000_000)

        assert not validated.location_stripped
        assert validated.data == _png()

    def test_the_image_still_decodes_after_stripping(self) -> None:
        stripped = strip_location(_jpeg_with_gps())

        with Image.open(io.BytesIO(stripped)) as image:
            assert image.size == (16, 16)


class TestValidatedUpload:
    def test_a_clean_image_reports_its_dimensions(self) -> None:
        validated = validate_upload(_png(32, 24), max_bytes=10_000_000)

        assert validated.kind is MediaKind.IMAGE
        assert validated.mime_type == "image/png"
        assert (validated.width, validated.height) == (32, 24)

    def test_a_pdf_is_accepted_without_image_checks(self) -> None:
        validated = validate_upload(b"%PDF-1.7\n" + b"x" * 100, max_bytes=10_000)

        assert validated.kind is MediaKind.PDF
        assert validated.width is None

    def test_a_mismatch_between_declared_and_actual_type_does_not_help_the_uploader(
        self,
    ) -> None:
        validated = validate_upload(_png(), max_bytes=10_000_000, declared_type="application/pdf")

        assert validated.kind is MediaKind.IMAGE
        assert validated.mime_type == "image/png"
