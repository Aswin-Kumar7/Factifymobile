"""PDF extraction (M17).

Forged government circulars and fake scheme notices circulate as PDFs on WhatsApp, so
a PDF is treated as a document with anchorable text rather than as a picture of one.

**Licensing note.** The plan named PyMuPDF. It is not used here: PyMuPDF is AGPL-3.0
unless separately licensed, which is a genuine problem for a product whose stated
destination is a commercial API. `pypdf` is BSD-3, pure Python, and sufficient for
text with page and character offsets. The one thing it cannot do is rasterise a page,
which matters only for image-only PDFs — handled below by extracting the embedded
images and sending those to OCR instead.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Anything longer is a document nobody forwards on WhatsApp, and a decompression
# surface we have no reason to expose.
DEFAULT_MAX_PAGES = 50

# Below this, a page is effectively blank — a scan whose text layer is missing.
_MIN_TEXT_CHARS_PER_PAGE = 30


class PdfRejected(Exception):
    def __init__(self, reason: str, *, kind: str = "invalid") -> None:
        self.reason = reason
        self.kind = kind
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class PdfPage:
    """One page, with the offsets a claim anchor will cite."""

    number: int
    text: str
    char_start: int
    char_end: int

    @property
    def has_text_layer(self) -> bool:
        return len(self.text.strip()) >= _MIN_TEXT_CHARS_PER_PAGE


@dataclass(frozen=True, slots=True)
class ExtractedPdf:
    """Text, page anchors, embedded images and what could not be read."""

    text: str
    pages: tuple[PdfPage, ...]
    page_count: int
    title: str | None = None
    author: str | None = None
    producer: str | None = None
    is_encrypted: bool = False
    embedded_images: tuple[bytes, ...] = ()
    limitations: tuple[str, ...] = field(default=())

    @property
    def needs_ocr(self) -> bool:
        """True when the document is scanned rather than typed.

        A forged circular is very often a photograph of a printout, which has no
        text layer at all — the claim lives in pixels and only OCR will reach it.
        """
        return not any(page.has_text_layer for page in self.pages)

    @property
    def is_usable(self) -> bool:
        return bool(self.text.strip()) or bool(self.embedded_images)


def extract(
    data: bytes, *, max_pages: int = DEFAULT_MAX_PAGES, extract_images: bool = True
) -> ExtractedPdf:
    """Extract text and page anchors from a PDF.

    Never executes embedded content: this reads the document structure only. An
    encrypted PDF is reported rather than attacked — refusing is correct, and
    circumventing protection is not something this service does.
    """
    limitations: list[str] = []

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except (PdfReadError, ValueError, OSError) as exc:
        raise PdfRejected(f"not a readable PDF: {exc}") from exc

    if reader.is_encrypted:
        # An empty-password PDF is encrypted only nominally and is fine to read.
        try:
            if reader.decrypt("") == 0:
                raise PdfRejected("PDF is password protected", kind="encrypted")
        except (NotImplementedError, PdfReadError) as exc:
            raise PdfRejected(f"PDF uses unsupported encryption: {exc}", kind="encrypted") from exc

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise PdfRejected("PDF has no pages")

    pages_to_read = min(total_pages, max_pages)
    if total_pages > max_pages:
        limitations.append(f"read {max_pages} of {total_pages} pages")

    pages: list[PdfPage] = []
    parts: list[str] = []
    cursor = 0

    for number in range(pages_to_read):
        try:
            page_text = reader.pages[number].extract_text() or ""
        except (PdfReadError, KeyError, ValueError):
            page_text = ""
            limitations.append(f"page {number + 1} could not be read")

        start = cursor
        end = start + len(page_text)
        pages.append(PdfPage(number=number + 1, text=page_text, char_start=start, char_end=end))
        parts.append(page_text)
        cursor = end + 1

    text = "\n".join(parts)
    images: tuple[bytes, ...] = ()

    if extract_images and not any(page.has_text_layer for page in pages):
        images = _embedded_images(reader, pages_to_read)
        if images:
            limitations.append("no text layer; extracted embedded images for OCR")
        else:
            limitations.append("no text layer and no embedded images")

    metadata: dict[str, object] = dict(reader.metadata or {})

    return ExtractedPdf(
        text=text,
        pages=tuple(pages),
        page_count=total_pages,
        title=_clean(metadata.get("/Title")),
        author=_clean(metadata.get("/Author")),
        producer=_clean(metadata.get("/Producer")),
        is_encrypted=reader.is_encrypted,
        embedded_images=images,
        limitations=tuple(limitations),
    )


def _embedded_images(reader: PdfReader, page_count: int) -> tuple[bytes, ...]:
    """Pull embedded images out of a scanned document so OCR has something to read.

    This is the alternative to rasterising a page, which would need a renderer we
    have deliberately not taken a licence for.
    """
    collected: list[bytes] = []

    for number in range(page_count):
        try:
            for image in reader.pages[number].images:
                collected.append(image.data)
                if len(collected) >= page_count:
                    break
        except (PdfReadError, KeyError, ValueError, NotImplementedError, AttributeError):
            continue

    return tuple(collected)


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
