"""A company's own list of locations, read for a claim that it opened one somewhere.

"Bugatti opens a new showroom at Chennai, the first in India" came back Unconfirmed
(2026-09-30): no news outlet reports it, and silence is never a contradiction (rule
5, `app/sources/reasoning.py`). But the company publishes where it is. Bugatti's own
site lists every partner showroom it has, and Chennai - India - is not among them.
That is not silence; it is the one source that would know, saying where it is.

So, for a claim that a named company opened (or has) a showroom, store, dealership,
branch or office in a named place, and only once nothing else has decided it:

  - the model names the company, its own website and the place (`presence_claim`);
  - the website must be the brand's own: its registrable domain's first label is the
    brand's name, so a dealer's or a news site's domain is never taken for it;
  - that site alone is searched for its list of locations, and the list page is
    fetched as served. Many keep the list as data in the page's script rather than
    as text, so the locations are read from the markup's own `city` and `country`
    fields;
  - a page with at least `_MIN_LOCATIONS` of them is a list. If the place (in any of
    its spellings) or its country appears anywhere on that page, the claim is not
    contradicted and the check stops. Otherwise the page is cited as contradicting
    the claim;
  - when no list page can be read (a site behind a bot check, as bugatti.com is),
    the site's own location pages as the search index holds them stand in for it -
    at least `_MIN_INDEXED` under one list address - and one more search of the site
    for the place itself must come back with pages, none naming the place or its
    country. A search that returned nothing proves nothing, and is not used.

Limited on purpose: the engine caps what this can carry at `OFFICIAL_ABSENCE_CAP`
(`app/verdict/engine.py`), because a list can lag a brand-new opening. And the rule
yields to any fresh news page and to any source that reports the opening.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.domain.claim import Claim
from app.domain.enums import Direction, EvidenceKind, Method, Tier
from app.domain.evidence import OFFICIAL_ABSENCE, Evidence, MatchBasis, SourceAnchor
from app.domain.publishers import registrable_domain
from app.observability.logging import event

logger = logging.getLogger("factify.sources.official_presence")

NAME = "official_presence"
VERSION = "2026.10.01.1"

# Fewer named locations than this is a page about a location, not a list of them.
_MIN_LOCATIONS = 5

# Pages read per claim, at most.
_MAX_PAGES = 3

# Where a list of locations lives in a site's addresses.
_LIST_WORDS = (
    "partner",
    "dealer",
    "locat",
    "showroom",
    "store",
    "retail",
    "branch",
    "network",
    "find",
    "office",
)
# And where it does not: a press release about one showroom is not the list.
_NOT_A_LIST = ("press", "news", "blog", "article", "story", "career", "job")

# A location kept as data: `city:"Toronto"`, `"addressCountry": "Canada"`.
_FIELD = re.compile(
    r"""["']?(?:city|country|addressLocality|addressCountry|locality|countryName)["']?"""
    r"""\s*:\s*["']([^"'<>{}\\]{2,60})["']""",
    re.IGNORECASE,
)


# Words without which a claim cannot be about a new location; the model is asked only
# when one appears, so an ordinary claim costs nothing here.
_PRESENCE_WORDS = re.compile(
    r"\b(showrooms?|stores?|dealers?|dealerships?|outlets?|branch(?:es)?|offices?|"
    r"boutiques?|flagship|experience cent(?:re|er))\b",
    re.IGNORECASE,
)


def might_apply(text: str) -> bool:
    """Whether a claim could be about a company's location at all."""
    return bool(_PRESENCE_WORDS.search(text))


def _letters(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def official_domain(company: str, website: str) -> str | None:
    """The brand's own registrable domain, or None when `website` is not plainly it."""
    site = website.strip().lower()
    if not site:
        return None
    if "://" not in site:
        site = f"https://{site}"
    domain = registrable_domain(site)
    if not domain:
        return None
    label = _letters(domain.split(".")[0])
    brand = _letters(company)
    if len(label) < 3 or not brand:
        return None
    return domain if label == brand or (brand.startswith(label) and len(label) >= 4) else None


def _same_site(url: str, domain: str) -> bool:
    return registrable_domain(url) == domain


def list_pages(rows: list[dict[str, Any]], domain: str) -> list[str]:
    """The addresses on the brand's site most likely to be its list of locations.

    A result for one location (`/en/partners/toronto`) points at the list above it
    (`/en/partners`), so the parent is tried first.
    """
    found: list[str] = []
    for row in rows:
        url = str(row.get("url") or "")
        if not url or not _same_site(url, domain):
            continue
        parts = urlsplit(url)
        path = parts.path.rstrip("/")
        if any(word in path.lower() for word in _NOT_A_LIST):
            continue
        segments = path.split("/")
        options = []
        if len(segments) > 2:
            options.append("/".join(segments[:-1]))
        options.append(path)
        for option in options:
            if any(word in option.lower() for word in _LIST_WORDS):
                candidate = urlunsplit((parts.scheme, parts.netloc, option or "/", "", ""))
                if candidate not in found:
                    found.append(candidate)
    return found


def locations(markup: str) -> list[str]:
    """The distinct places a page keeps as data, in the order they first appear."""
    seen: dict[str, str] = {}
    for match in _FIELD.finditer(markup):
        value = " ".join(match.group(1).split()).strip(" ,")
        key = value.lower()
        if len(key) >= 2 and not key.isdigit() and key not in seen:
            seen[key] = value
    return list(seen.values())


def mentions(markup: str, names: list[str]) -> bool:
    """Whether any of the names appears on the page as a word."""
    for name in names:
        name = " ".join(name.split())
        word = rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])"
        if len(name) >= 3 and re.search(word, markup, re.IGNORECASE):
            return True
    return False


# Location pages the search index must hold under one list before it stands in for
# the list itself (the second route, below).
_MIN_INDEXED = 3


def indexed_locations(
    rows: list[dict[str, Any]], domain: str, company: str = ""
) -> tuple[str | None, list[str]]:
    """The brand's list address and the locations under it, from search results alone.

    The second route, for a list page that refuses to be read: bugatti.com answers
    every request of ours, its sitemap included, with a bot check (2026-10-01). Its
    location pages are still in the search index, one per showroom -
    `/en/partners/riyadh`, `/en/partners/miami` - and named in their titles.
    """
    children: dict[str, list[str]] = {}
    for row in rows:
        url = str(row.get("url") or "")
        if not url or not _same_site(url, domain):
            continue
        parts = urlsplit(url)
        segments = parts.path.rstrip("/").split("/")
        if len(segments) < 3:
            continue
        parent = "/".join(segments[:-1])
        if not any(word in parent.lower() for word in _LIST_WORDS):
            continue
        if any(word in parent.lower() for word in _NOT_A_LIST):
            continue
        title = str(row.get("title") or "").split("|")[0]
        name = " ".join(title.split()).strip(" -")
        if company:
            name = re.sub(rf"\b{re.escape(company)}\b", "", name, flags=re.IGNORECASE)
            name = " ".join(name.split()).strip(" -")
        name = name or segments[-1].replace("-", " ").title()
        key = urlunsplit((parts.scheme, parts.netloc, parent, "", ""))
        if name not in children.setdefault(key, []):
            children[key].append(name)
    if not children:
        return None, []
    best = max(children, key=lambda key: len(children[key]))
    return best, children[best]


def _row_mentions(row: dict[str, Any], names: list[str]) -> bool:
    text = f"{row.get('url') or ''} {row.get('title') or ''} {row.get('content') or ''}"
    return mentions(text.replace("-", " ").replace("/", " "), names)


class OfficialPresenceCheck:
    """Contradicts a claim of a new location with the company's own list, when that
    list leaves the place out. Returns one piece of evidence or nothing."""

    def __init__(self, *, web: Any, reasoner: Any) -> None:
        self._web = web
        self._reasoner = reasoner

    async def check(self, claim: Claim) -> Evidence | None:
        try:
            return await self._check(claim)
        except Exception:  # an extra check that fails leaves the claim as it was
            logger.exception("official presence check failed")
            return None

    async def _check(self, claim: Claim) -> Evidence | None:
        if not might_apply(claim.reading_text):
            return None
        facts = await self._reasoner.presence_claim(claim.reading_text)
        if not facts:
            return None
        company = str(facts.get("company") or "").strip()
        place = str(facts.get("place") or "").strip()
        country = str(facts.get("country") or "").strip()
        domain = official_domain(company, str(facts.get("website") or ""))
        if not company or not place or domain is None:
            self._event("not checked", company=company, reason="no official site")
            return None
        names = [place, *[str(n) for n in facts.get("place_names") or []]]

        rows = await self._web.search_site(
            f"{company} showrooms dealers locations find a partner", domain
        )
        for url in list_pages(rows, domain)[:_MAX_PAGES]:
            page = await self._web.fetch_page(url)
            if page is None:
                continue
            markup = page.text
            listed = locations(markup)
            if len(listed) < _MIN_LOCATIONS:
                continue
            if mentions(markup, names) or (country and mentions(markup, [country])):
                # The list has it: nothing here contradicts the claim.
                self._event("place listed", company=company, url=page.final_url)
                return None
            self._event("place not listed", company=company, url=page.final_url)
            return self._evidence(
                claim,
                company=company,
                place=place,
                country=country,
                listed=listed,
                url=page.final_url or url,
                body=page.body,
                fetched_at=page.fetched_at,
            )

        # The list page could not be read: the site's own location pages, as the
        # search index holds them, and one search of the site for the place itself.
        list_url, listed = indexed_locations(rows, domain, company)
        if list_url is None or len(listed) < _MIN_INDEXED:
            self._event("not checked", company=company, reason="no list of locations found")
            return None
        found = await self._web.search_site(f"{company} {place} {country} showroom", domain)
        if not found:
            # A search that returned nothing may not have run at all.
            self._event("not checked", company=company, reason="place search empty")
            return None
        if any(
            _row_mentions(row, names) or (country and _row_mentions(row, [country]))
            for row in [*rows, *found]
        ):
            self._event("place listed", company=company, url=list_url)
            return None
        self._event("place not listed", company=company, url=list_url, route="index")
        seen = "\n".join(str(row.get("url") or "") for row in [*rows, *found])
        return self._evidence(
            claim,
            company=company,
            place=place,
            country=country,
            listed=listed,
            url=list_url,
            body=seen.encode(),
            fetched_at=None,
        )

    def _evidence(
        self,
        claim: Claim,
        *,
        company: str,
        place: str,
        country: str,
        listed: list[str],
        url: str,
        body: bytes,
        fetched_at: datetime | None,
    ) -> Evidence:
        digest = hashlib.sha256(body).hexdigest()
        where = (
            place
            if not country or country.lower() == place.lower()
            else (f"{place} or anywhere in {country}")
        )
        shown = ", ".join(listed[:12]) + ("…" if len(listed) > 12 else "")
        return Evidence.build(
            id=f"ev:{NAME}:{digest[:16]}:{claim.id}",
            claim_id=claim.id,
            tier=Tier.D,
            kind=EvidenceKind.CORROBORATION,
            direction=Direction.CONTRADICTS,
            method=Method.OFFICIAL_SOURCE,
            finding=f"{company}'s own website lists its locations, and none is in {where}.",
            citation_url=url,
            snapshot_id=f"sha256:{digest}",
            source_excerpt=f"Locations on {registrable_domain(url)}: {shown}",
            source_anchor=SourceAnchor(),
            match_basis=MatchBasis(metric=OFFICIAL_ABSENCE, value=1.0, threshold=0.5),
            publisher=registrable_domain(url),
            title=f"{company} - official locations",
            provider=NAME,
            provider_version=VERSION,
            observed_at=fetched_at or datetime.now(UTC),
        )

    def _event(self, what: str, **fields: Any) -> None:
        event(
            logger,
            f"official presence {what}",
            module="sources.official_presence",
            outcome="ok",
            **fields,
        )
