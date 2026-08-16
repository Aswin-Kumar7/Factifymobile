"""Web article extraction (M16).

Turns a fetched public page into structured content with anchors. Priority order is
structured metadata first, then a main-content extractor — because a publisher's own
JSON-LD is a statement of fact about their article, while boilerplate removal is a
heuristic about their HTML.

Paragraph anchors are computed here rather than downstream. A claim has to point back
at the exact paragraph and character range it came from, and only the code that
segmented the body knows where those boundaries were.

One thing worth noticing while reading: the **absence** of structured metadata is
itself a weak signal. Real publishing systems emit JSON-LD automatically; sites built
to look like publishers frequently do not. It is recorded, never decisive.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import trafilatura
from lxml import html as lxml_html

_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# Long enough to carry a checkable claim. Shorter fragments are captions, bylines and
# navigation text, which produce anchors nobody can act on.
_MIN_PARAGRAPH_CHARS = 40


@dataclass(frozen=True, slots=True)
class Paragraph:
    """One body paragraph with the offsets a claim anchor will cite."""

    index: int
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class ExtractedArticle:
    """Structured content plus an honest account of what could not be read."""

    title: str | None = None
    body: str = ""
    paragraphs: tuple[Paragraph, ...] = ()
    author: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    modified_at: datetime | None = None
    canonical_url: str | None = None
    images: tuple[str, ...] = ()
    quotes: tuple[str, ...] = ()
    outbound_links: tuple[str, ...] = ()
    has_structured_metadata: bool = False
    extraction_route: str = ""
    limitations: tuple[str, ...] = field(default=())

    @property
    def is_usable(self) -> bool:
        """Whether there is enough here to extract a claim from."""
        return bool(self.paragraphs) or bool(self.title)

    @property
    def excerpt(self) -> str:
        """A short quotation for the evidence ledger — never the whole body.

        Storing full article text would be republishing someone else's work; a
        citation plus the sentence that matters is what evidence actually needs.
        """
        return self.body[:500]


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for pattern in ("%Y-%m-%d", "%d %B %Y", "%B %d, %Y"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _flatten(node: object) -> list[dict[str, object]]:
    """JSON-LD arrives as an object, a list, or a @graph. Flatten all three."""
    if isinstance(node, list):
        return [item for child in node for item in _flatten(child)]
    if isinstance(node, dict):
        if "@graph" in node:
            return _flatten(node["@graph"])
        return [node]
    return []


def parse_structured_metadata(html: str) -> dict[str, object]:
    """Read schema.org article metadata, if the publisher emitted any."""
    for block in _JSON_LD.findall(html):
        try:
            payload = json.loads(block.strip())
        except json.JSONDecodeError:
            continue

        for node in _flatten(payload):
            node_type = node.get("@type", "")
            types = node_type if isinstance(node_type, list) else [node_type]
            if any(str(t).endswith(("Article", "NewsArticle", "BlogPosting")) for t in types):
                return node

    return {}


def _text_of(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        name = value.get("name")
        return str(name).strip() if name else None
    if isinstance(value, list) and value:
        return _text_of(value[0])
    return None


def _segment(body: str) -> tuple[Paragraph, ...]:
    """Split into paragraphs, recording the offsets a claim will anchor to."""
    paragraphs: list[Paragraph] = []
    cursor = 0
    index = 0

    for block in body.split("\n"):
        start = body.find(block, cursor)
        if start == -1:
            start = cursor
        end = start + len(block)
        cursor = end

        stripped = block.strip()
        if len(stripped) >= _MIN_PARAGRAPH_CHARS:
            paragraphs.append(Paragraph(index=index, text=stripped, char_start=start, char_end=end))
            index += 1

    return tuple(paragraphs)


def _links_and_quotes(html: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Outbound citations and quoted material — the inputs to the two killer checks.

    Outbound links are what the attribution check fetches; quotes are what the quote
    check searches for. Both come from the raw DOM because a content extractor
    deliberately discards them as boilerplate.
    """
    try:
        tree = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        return (), ()

    links = tuple(
        dict.fromkeys(
            href
            for href in (a.get("href", "") for a in tree.iter("a"))
            if href.startswith(("http://", "https://"))
        )
    )

    quotes = tuple(
        dict.fromkeys(
            text
            for element in tree.iter("blockquote", "q")
            # itertext() can yield bytes for comment and processing-instruction
            # nodes, which is why the pieces are filtered rather than joined blindly.
            if (
                text := " ".join(
                    "".join(piece for piece in element.itertext() if isinstance(piece, str)).split()
                )
            )
            and len(text) > 20
        )
    )

    return links, quotes


def extract(html: str, *, url: str | None = None) -> ExtractedArticle:
    """Extract an article from fetched HTML.

    Returns a value even when extraction largely fails, with `limitations` naming
    what went wrong. A partially-parsed page must never be presented as a fully-read
    one — downstream has to know it is working from fragments.
    """
    limitations: list[str] = []
    metadata = parse_structured_metadata(html)
    has_structured = bool(metadata)

    if not has_structured:
        limitations.append("no structured article metadata")

    body = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )

    if not body:
        limitations.append("main-content extraction found no body")
        body = ""

    paragraphs = _segment(body)
    if body and not paragraphs:
        limitations.append("body has no paragraph long enough to anchor a claim")

    links, quotes = _links_and_quotes(html)

    title = _text_of(metadata.get("headline")) or _text_of(metadata.get("name"))
    if title is None:
        try:
            tree = lxml_html.fromstring(html)
            element = tree.find(".//title")
            title = (element.text or "").strip() or None if element is not None else None
        except (ValueError, lxml_html.etree.ParserError):
            title = None

    published = _parse_date(metadata.get("datePublished"))
    if published is None and has_structured:
        limitations.append("structured metadata carries no publication date")

    images: tuple[str, ...] = ()
    image_value = metadata.get("image")
    if isinstance(image_value, str):
        images = (image_value,)
    elif isinstance(image_value, list):
        images = tuple(item for item in image_value if isinstance(item, str))
    elif isinstance(image_value, dict) and isinstance(image_value.get("url"), str):
        images = (str(image_value["url"]),)

    route = "web.jsonld+trafilatura" if has_structured else "web.trafilatura"

    return ExtractedArticle(
        title=title,
        body=body,
        paragraphs=paragraphs,
        author=_text_of(metadata.get("author")),
        publisher=_text_of(metadata.get("publisher")),
        published_at=published,
        modified_at=_parse_date(metadata.get("dateModified")),
        canonical_url=_text_of(metadata.get("mainEntityOfPage")) or url,
        images=images,
        quotes=quotes,
        outbound_links=links,
        has_structured_metadata=has_structured,
        extraction_route=route,
        limitations=tuple(limitations),
    )
