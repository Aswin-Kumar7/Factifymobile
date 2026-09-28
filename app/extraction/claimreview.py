"""A fact-checker's own verdict, read from its page's ClaimReview markup.

Fact-checkers that follow the IFCN code - PIB Fact Check, BOOM, Alt News, Factly,
Newschecker, India Today's fact-check desk and most others - publish each verdict as
schema.org `ClaimReview` JSON-LD in the page itself: the claim they reviewed, their
rating ("False", "Misleading", "Fake"), who they are and when. It is there for search
engines to read, and it is the most exact statement of a fact-check there is.

Until this existed, a fact-check's rating was read out of its headline, which works
for "Fact Check: This video is NOT from Delhi" and for nothing else: 8 of the 76
fact-checks in the corpus had a rating anyone could read. The markup has one on
nearly every page that has markup at all.

Plain JSON, never a model: nothing on the page is interpreted beyond the fields the
schema defines.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_LD_JSON = re.compile(
    r"<script[^>]+type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

# The most reviews read from one page. A roundup can review many claims; past a
# handful it is a listing page, not a fact-check.
_MOST = 8


@dataclass(frozen=True, slots=True)
class ClaimReview:
    """One verdict: the claim reviewed, the rating given, by whom and when."""

    claim_reviewed: str
    rating: str | None
    publisher: str | None
    published_at: datetime | None
    url: str | None


def read_claim_reviews(html: str, *, page_url: str | None = None) -> list[ClaimReview]:
    """Every ClaimReview on a page, in the order they appear. Empty when none."""
    reviews: list[ClaimReview] = []
    for block in _LD_JSON.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _nodes(data):
            review = _review(node, page_url)
            if review is not None:
                reviews.append(review)
            if len(reviews) >= _MOST:
                return reviews
    return reviews


def _nodes(data: Any) -> list[dict[str, Any]]:
    """Every object in a JSON-LD document: top level, arrays and `@graph`."""
    found: list[dict[str, Any]] = []
    stack = [data]
    while stack:
        item = stack.pop(0)
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            found.append(item)
            graph = item.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
    return found


def _is_claim_review(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return any(str(k).lower() == "claimreview" for k in kinds)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("alternateName") or "")
    if isinstance(value, list) and value:
        return _text(value[0])
    return ""


def _review(node: dict[str, Any], page_url: str | None) -> ClaimReview | None:
    if not _is_claim_review(node):
        return None
    claim = _text(node.get("claimReviewed"))
    if not claim:
        # Some pages put the claim in the reviewed item instead.
        item = node.get("itemReviewed")
        if isinstance(item, dict):
            claim = _text(item.get("name") or item.get("description"))
    if not claim:
        return None
    rating = node.get("reviewRating")
    verdict = ""
    if isinstance(rating, dict):
        verdict = _text(rating.get("alternateName") or rating.get("name"))
    publisher = _organisation(node) or None
    return ClaimReview(
        claim_reviewed=claim[:500],
        rating=verdict[:80] or None,
        publisher=publisher[:120] if publisher else None,
        published_at=_date(node.get("datePublished")),
        url=str(node.get("url") or page_url or "").strip() or None,
    )


def _organisation(node: dict[str, Any]) -> str:
    """Who published the verdict: an organisation among its authors, else its publisher.

    The schema asks for the fact-checking organisation as the author; BOOM names the
    writer there instead, and "a fact-check by Anmol Alphonso" is not who rated it.
    """
    author = node.get("author")
    for item in author if isinstance(author, list) else [author]:
        if isinstance(item, dict) and str(item.get("@type", "")).casefold() == "organization":
            return _text(item)
    return _text(node.get("publisher")) or _text(author)


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text[:10])
        except ValueError:
            return None
