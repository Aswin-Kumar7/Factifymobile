"""Publisher credibility for the open-web path.

Source **selection**, not verdict determination. The design law keeps source risk about
the publisher and never lets it make a claim false (`app/verdict/engine.py`, rule 6),
and nothing here touches that. What this decides is narrower and upstream: which of the
pages a web search returned are worth a reasoning call and a citation at all. A
fact-checker does not cite a conspiracy blog as evidence; neither should the web-search
resolver, and dropping those pages before the reasoner reads them removes the false
conflict a junk "SUPPORTS" would create *and* saves the metered read.

Deliberately an allowlist, not a blocklist. Maintaining a register of "bad" domains is
editorial whack-a-mole; naming the sources whose reporting is citable is a smaller,
more honest, and more defensible commitment — and an unknown domain is simply not cited
from the open web, rather than judged. Government, education and international-body TLDs
are trusted by pattern so the list need not chase every institution.

The list lives in `data/source_credibility.json` — data, not code, so it grows without a
deploy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger("facify.sources.credibility")

# TLD suffixes whose operators are governments, universities or international bodies —
# credible by their nature rather than by enumeration.
_TRUSTED_SUFFIXES = (
    ".gov",
    ".mil",
    ".int",
    ".edu",
    ".gov.in",
    ".nic.in",
    ".ac.in",
    ".ac.uk",
    ".gov.uk",
    ".edu.au",
    ".gov.au",
    ".edu.pk",
    ".who.int",
)


class SourceCredibility:
    """Whether a domain's reporting is credible enough to cite as web evidence."""

    def __init__(self, trusted: frozenset[str]) -> None:
        self._trusted = trusted

    @classmethod
    def load(cls, path: Path | str | None = None) -> SourceCredibility:
        """Load the curated allowlist, or an empty one if it cannot be read.

        An unreadable list is not fatal: web search then trusts only the TLD patterns,
        which is stricter, not looser — it never makes an unknown domain citable.
        """
        default = Path(__file__).resolve().parents[2] / "data" / "source_credibility.json"
        location = Path(path) if path else default
        try:
            raw = json.loads(location.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("source credibility list not readable; trusting TLD patterns only")
            return cls(frozenset())

        domains: set[str] = set()
        for key, value in raw.items():
            if key.startswith("_") or not isinstance(value, list):
                continue
            domains.update(d.lower().removeprefix("www.") for d in value if isinstance(d, str))
        return cls(frozenset(domains))

    def is_credible(self, url_or_domain: str | None) -> bool:
        """Whether this source may be cited as open-web evidence."""
        domain = self._domain_of(url_or_domain)
        if not domain:
            return False
        # A trusted TLD pattern: either the domain is the pattern itself (gov.uk) or it
        # sits under it (pib.gov.in, mit.edu).
        for suffix in _TRUSTED_SUFFIXES:
            bare = suffix.lstrip(".")
            if domain == bare or domain.endswith("." + bare):
                return True
        # A registrable match: news.bbc.co.uk is credible because bbc.co.uk is listed.
        return any(domain == trusted or domain.endswith("." + trusted) for trusted in self._trusted)

    @staticmethod
    def _domain_of(url_or_domain: str | None) -> str:
        if not url_or_domain:
            return ""
        value = url_or_domain.strip().lower()
        host = urlsplit(value).netloc if "://" in value else value
        return host.removeprefix("www.").split(":")[0]
