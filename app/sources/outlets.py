"""What an outlet is called, for showing it by name rather than by address.

From the feed registry (`data/feeds.json`), where every outlet read on a schedule is
listed with its name. A site not listed there is shown by its domain: a name is never
guessed from an address, because a wrong name on a source is worse than none.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

_FEEDS = Path(__file__).resolve().parents[2] / "data" / "feeds.json"


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    try:
        feeds = json.loads(_FEEDS.read_text(encoding="utf-8")).get("feeds", [])
    except (OSError, ValueError):
        return {}
    names: dict[str, str] = {}
    for feed in feeds:
        host = urlsplit(str(feed.get("url", ""))).netloc.lower().removeprefix("www.")
        publisher = feed.get("publisher")
        if host and isinstance(publisher, str) and publisher:
            names.setdefault(host, publisher)
    return names


def outlet_name(domain: str) -> str | None:
    """The outlet's name for a domain or any of its subdomains, or None."""
    host = domain.lower().removeprefix("www.")
    names = _names()
    while host:
        if host in names:
            return names[host]
        _, _, host = host.partition(".")
        if "." not in host:
            return None
    return None
