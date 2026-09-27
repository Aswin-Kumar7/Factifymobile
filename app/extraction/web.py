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

# Publication date as an Open Graph / article meta tag, for pages that emit no
# JSON-LD. A fallback, not the primary path: JSON-LD is a typed record, whereas a
# meta tag is a string a template wrote. Measured on 16 real Indian article pages,
# JSON-LD alone found 8 dates and this recovered 1 more — small, but dating is the
# flagship case and the cost is one regex.
# A page's lead picture as its sharing card declares it, with the attributes in
# either order. Most news pages give it here even when their JSON-LD does not.
_META_TAG = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_ATTR = re.compile(r"""(property|name|content)\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_IMAGE_KEYS = frozenset({"og:image", "og:image:url", "og:image:secure_url", "twitter:image"})


def _card_image(html: str) -> str | None:
    """The og:image (or twitter:image) address, if the page declares one."""
    for tag in _META_TAG.findall(html):
        attrs: dict[str, str] = {str(k).lower(): str(v) for k, v in _META_ATTR.findall(tag)}
        label = (attrs.get("property") or attrs.get("name") or "").lower()
        content = attrs.get("content", "").strip()
        if label in _IMAGE_KEYS and content.startswith(("http://", "https://")):
            return content
    return None


_META_PUBLISHED = re.compile(
    r"""<meta[^>]+(?:property|name)=["'](?:article:published_time|publishdate"""
    r"""|og:published_time|datePublished)["'][^>]+content=["']([^"']+)""",
    re.IGNORECASE,
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


def headline_and_summary(html: str) -> tuple[str | None, str | None]:
    """The headline and summary a page publishes about itself, or (None, None).

    For a page whose article text nobody could read: a paywall, a script-only
    shell. Publishers put these in the page head for search engines and link
    previews, in the open, so reading them is reading what the publisher chose to
    show anyone. A schema.org `articleBody`, when a page includes one, is used
    whole. Nothing here gets past a paywall; it reads what is outside it.
    """
    metadata = parse_structured_metadata(html)
    body = _text_of(metadata.get("articleBody"))
    headline = _text_of(metadata.get("headline"))
    summary = body if body and len(body) >= 600 else _text_of(metadata.get("description"))

    try:
        doc = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        doc = None
    if doc is not None:

        def meta(*names: str) -> str | None:
            for name in names:
                found = doc.xpath(f'//meta[@property="{name}" or @name="{name}"]/@content')
                if isinstance(found, list) and found and str(found[0]).strip():
                    return " ".join(str(found[0]).split())
            return None

        headline = headline or meta("og:title", "twitter:title")
        summary = summary or meta("og:description", "twitter:description", "description")
        if headline is None:
            titles = doc.xpath("//title/text()")
            headline = (
                " ".join(str(titles[0]).split()) if isinstance(titles, list) and titles else None
            )

    # A title alone is a site name as often as a headline ("reuters.com"); a summary
    # is what makes this worth checking.
    if not summary or len(summary) < 60:
        return None, None
    return headline, summary


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

    # `favor_precision` is deliberately **not** set, and tables are kept.
    #
    # Precision-favouring extraction is right when the output is a corpus and a stray
    # nav line is noise. Ours is evidence: a citation requires locating a verbatim
    # quote in this text, so a paragraph trafilatura drops is a quote we can never
    # support, and the claim abstains for a reason that has nothing to do with the
    # evidence. Measured on a Hindu article: 197 characters with `favor_precision`,
    # 838 without — four fifths of the page discarded.
    #
    # Tables are kept for the same reason. Case counts, election results and budget
    # figures are the checkable part of exactly the claims people forward.
    body = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
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
    if published is None:
        # Fall back to the meta tag before giving up. A page that states its date
        # only in a meta tag is still a dated page, and an undated page cannot
        # participate in the temporal comparison at all.
        match = _META_PUBLISHED.search(html)
        if match:
            published = _parse_date(match.group(1))
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
    if not images:
        card = _card_image(html)
        if card:
            images = (card,)

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


# Markdown as the search vendor's extract returns it. An image first, so a linked
# image — `[![alt](img)](href)` — leaves an empty link behind rather than its alt text.
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+\"[^\"]*\")?\)")
# A link's text is kept and its target dropped. The target may itself contain one
# level of parentheses, as Wikipedia URLs do.
_MD_LINK = re.compile(r"\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))*(?:\s+\"[^\"]*\")?\)")
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_EMPHASIS = re.compile(r"\*\*+|__+")
_MD_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")
_RUNS_OF_SPACE = re.compile(r"[ \t ]{2,}")


def plain_text(markdown: str) -> str:
    """The words of a page the search vendor returned as markdown, as a reader sees them.

    The vendor's extract is the fallback reader for the publishers that refuse our own
    fetch — Reuters, AP, NDTV, PIB, the sources most worth citing — and it returns
    markdown. The reasoner quotes a sentence as it reads, and the quote check then
    looks for that sentence in the text we hold. Against markdown it is not there:

        demanded the resignation of [Chief Election Commissioner (CEC) Gyanesh
        Kumar](https://www.thehindu.com/news/...) for "undermining" voter rights

    Measured on one The Hindu article: 181 links, 34 images and 8 bold markers, and
    both of the model's quotes from it discarded as "not in the passage" — the exact
    story a person had pasted, reported in their own words, thrown away.

    A line that was nothing but links — a site's navigation menu — is dropped rather
    than kept as a row of section names; it is text a model would otherwise be paid to
    read.
    """
    lines: list[str] = []
    for line in markdown.splitlines():
        without_images = _MD_IMAGE.sub("", line)
        had_link = _MD_LINK.search(without_images) is not None
        text = _MD_LINK.sub(r"\1", without_images)
        if had_link and not _MD_LINK.sub("", without_images).strip(" \t|*-•·,"):
            continue
        text = _MD_HEADING.sub("", text)
        text = _MD_EMPHASIS.sub("", text)
        text = _MD_ESCAPE.sub(r"\1", text)
        text = _RUNS_OF_SPACE.sub(" ", text).strip()
        if text or (lines and lines[-1]):
            lines.append(text)
    return "\n".join(lines).strip()
