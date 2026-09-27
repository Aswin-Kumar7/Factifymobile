"""The source reader: a cited passage, shown where it sits in its article (v5, 4.2).

A result cites a sentence. The reader shows the paragraph that sentence is in and the
one on either side, the headline, the date and how long the whole article is - enough
to see the quote was not lifted out of a context that changes it - and links to the
page for the rest. Only the passage and its neighbours are returned, never the whole
article: the publisher's page is where the article is read, and republishing it here
is not ours to do.

The page is fetched again by the server, through the SSRF-guarded client, so the
person's phone never contacts the site. Its text is cleaned with the same sanitiser
used on everything a model reads (invisible characters out, look-alikes folded); it
is only displayed, but a page built to deceive a reader deserves no easier a path to
one than to a model.

A page that refuses the server's own fetch - The Hindu, PIB, Reuters and AP do - is
read through the search provider's licensed extract instead, the route the check itself
takes for them, and only when someone opens the source. A page that cannot be read
either way still gives the quote the result was built on, and says the rest could not
be opened.
"""

from __future__ import annotations

import asyncio
import io
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from app.domain.typography import fold
from app.extraction.web import extract, plain_text
from app.security.fetcher import FetchResult
from app.security.injection import sanitise

# Words a minute, for the read-time estimate.
_READING_SPEED = 200
# Paragraphs of context either side of the quote.
_NEIGHBOURS = 1


@dataclass(frozen=True, slots=True)
class SourceView:
    url: str
    domain: str
    paragraphs: tuple[str, ...]
    quote: str
    quote_paragraph: int | None = None
    quote_start: int | None = None
    quote_end: int | None = None
    headline: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    read_minutes: int | None = None
    image: bytes | None = None
    # The page was read now, and the passage found in it.
    complete: bool = False
    limitations: tuple[str, ...] = field(default_factory=tuple)


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _clean(text: str) -> str:
    return " ".join(sanitise(text).text.split())


def _locate(quote: str, paragraphs: list[str]) -> tuple[int, int, int] | None:
    """Which paragraph holds the quote, and where in it. Typography-tolerant."""
    wanted = fold(quote)
    if not wanted:
        return None
    for index, paragraph in enumerate(paragraphs):
        folded = fold(paragraph)
        at = folded.find(wanted)
        if at >= 0:
            # Folding flattens whitespace; the cleaned paragraph is already flat, so
            # positions agree up to case and typography, which are one-for-one.
            return index, at, at + len(wanted)
    # The quote's opening words, when the page's punctuation differs from ours.
    head = " ".join(wanted.split()[:8])
    if len(head.split()) >= 5:
        for index, paragraph in enumerate(paragraphs):
            if head in fold(paragraph):
                return index, 0, 0
    return None


def _shrunk(data: bytes, *, side: int = 720) -> bytes | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            picture = image.convert("RGB")
            picture.thumbnail((side, side))
            out = io.BytesIO()
            picture.save(out, "JPEG", quality=82)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        return None


async def read_source(
    fetcher: Any,
    *,
    url: str,
    quote: str,
    publisher: str | None = None,
    published_at: datetime | None = None,
    headline: str | None = None,
    vendor: Callable[[str], Awaitable[str | None]] | None = None,
) -> SourceView:
    """The quoted passage in its article, or the quote alone when the page will not open."""
    quote = _clean(quote)
    fallback = SourceView(
        url=url,
        domain=_domain(url),
        paragraphs=(quote,),
        quote=quote,
        quote_paragraph=0,
        quote_start=0,
        quote_end=len(quote),
        headline=_clean(headline) if headline else None,
        publisher=publisher,
        published_at=published_at,
    )

    response = await fetcher.fetch(url, provider="source_reader")
    article = None
    paragraphs: list[str] = []
    if isinstance(response, FetchResult) and "html" in (response.content_type or "html"):
        article = await asyncio.to_thread(extract, response.text, url=url)
        paragraphs = [_clean(p.text) for p in article.paragraphs if p.text.strip()]
        if not paragraphs and article.body.strip():
            paragraphs = [_clean(part) for part in article.body.split("\n") if part.strip()]
    if not paragraphs and vendor is not None:
        text = await _vendor_text(vendor, url)
        paragraphs = [_clean(line) for line in plain_text(text).split("\n") if line.strip()]
    if not paragraphs:
        return _limited(fallback, "the page could not be opened now")

    found = _locate(quote, paragraphs)
    if found is None:
        moved = (
            _with_article(fallback, article, response)
            if article is not None and isinstance(response, FetchResult)
            else fallback
        )
        return _limited(moved, "the passage is no longer on the page as quoted")

    index, start, end = found
    first = max(0, index - _NEIGHBOURS)
    window = tuple(paragraphs[first : index + _NEIGHBOURS + 1])
    body = article.body if article is not None else ""
    words = len(body.split()) or sum(len(p.split()) for p in paragraphs)

    image: bytes | None = None
    if article is not None and article.images:
        picture = await fetcher.fetch(article.images[0], provider="source_image")
        if isinstance(picture, FetchResult) and (picture.content_type or "").startswith("image/"):
            image = await asyncio.to_thread(_shrunk, picture.body)

    final = response.final_url if isinstance(response, FetchResult) else url
    title = article.title if article is not None and article.title else headline
    return SourceView(
        url=final,
        domain=_domain(final),
        paragraphs=window,
        quote=quote,
        quote_paragraph=index - first,
        quote_start=start if end else None,
        quote_end=end or None,
        headline=_clean(title) if title else None,
        publisher=publisher or (article.publisher if article is not None else None),
        published_at=published_at or (article.published_at if article is not None else None),
        read_minutes=max(1, round(words / _READING_SPEED)),
        image=image,
        complete=True,
    )


async def _vendor_text(vendor: Callable[[str], Awaitable[str | None]], url: str) -> str:
    try:
        return await vendor(url) or ""
    except Exception:
        return ""


def _with_article(view: SourceView, article: Any, response: FetchResult) -> SourceView:
    return SourceView(
        url=response.final_url,
        domain=_domain(response.final_url),
        paragraphs=view.paragraphs,
        quote=view.quote,
        quote_paragraph=view.quote_paragraph,
        quote_start=view.quote_start,
        quote_end=view.quote_end,
        headline=_clean(article.title) if article.title else view.headline,
        publisher=view.publisher or article.publisher,
        published_at=view.published_at or article.published_at,
    )


def _limited(view: SourceView, reason: str) -> SourceView:
    return SourceView(
        url=view.url,
        domain=view.domain,
        paragraphs=view.paragraphs,
        quote=view.quote,
        quote_paragraph=view.quote_paragraph,
        quote_start=view.quote_start,
        quote_end=view.quote_end,
        headline=view.headline,
        publisher=view.publisher,
        published_at=view.published_at,
        complete=False,
        limitations=(reason,),
    )


class SourceViews:
    """Read sources, kept for an hour so reopening one is instant and costs no fetch."""

    def __init__(self, *, keep_seconds: float = 3600.0, most: int = 200) -> None:
        self._keep = keep_seconds
        self._most = most
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None or time.monotonic() - item[0] > self._keep:
            self._items.pop(key, None)
            return None
        return item[1]

    def put(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic(), value)
        self._items.move_to_end(key)
        while len(self._items) > self._most:
            self._items.popitem(last=False)
