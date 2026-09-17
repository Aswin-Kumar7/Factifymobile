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

Two refinements keep the allowlist honest at the edges:

- **Pattern exceptions.** A suffix is trusted because its registry is restricted, but a
  few registrations predate the restriction. `academia.edu` is a commercial upload site,
  not a university, and "anything under .edu" would otherwise cite whatever a stranger
  uploaded there. These are held in code so they apply even when the data file is
  unreadable.
- **User-content paths.** A credible publisher can host a section where anyone may post
  — a reader blog, a citizen-journalism page. The host's reporting is citable; a
  stranger's post under its masthead is not. Those path prefixes are data, listed per
  host in `user_content_paths`.

The list lives in `data/source_credibility.json` — data, not code, so it grows without a
deploy.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger("facify.sources.credibility")

# TLD suffixes whose operators are governments, universities or international bodies —
# credible by their nature rather than by enumeration. Held in code, not data, so they
# still apply when the data file cannot be read: that failure makes the gate stricter,
# never looser.
_TRUSTED_SUFFIXES = frozenset(
    {
        "gov",
        "mil",
        "int",
        "edu",
        "gov.in",
        "nic.in",
        "ac.in",
        "ac.uk",
        "gov.uk",
        "edu.au",
        "gov.au",
        "edu.pk",
    }
)

# Registrations under a trusted suffix that are not what the suffix promises. Checked
# before anything else, so neither a pattern nor an explicit listing can make them
# citable.
_NOT_INSTITUTIONAL = frozenset(
    {
        # A commercial paper-sharing network holding a pre-2001 .edu registration.
        "academia.edu",
    }
)

# The one non-list key the loader reads: host -> path prefixes that are open to anyone.
_USER_CONTENT_KEY = "user_content_paths"


class SourceCredibility:
    """Whether a domain's reporting is credible enough to cite as web evidence."""

    def __init__(
        self,
        trusted: frozenset[str],
        user_content_paths: Mapping[str, tuple[str, ...]] | None = None,
        fact_checkers: frozenset[str] = frozenset(),
    ) -> None:
        self._trusted = trusted
        self._user_content_paths = dict(user_content_paths or {})
        # Publishers whose business is adjudicating claims. A page of theirs is a
        # published fact-check wherever it was found, which is a stronger class of
        # evidence than a news report that happens to bear on the claim.
        self._fact_checkers = fact_checkers

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
        fact_checkers: set[str] = set()
        for key, value in raw.items():
            if key.startswith("_") or not isinstance(value, list):
                continue
            hosts = {_normalise_host(d) for d in value if isinstance(d, str)}
            domains.update(hosts)
            # Every `fact_checkers_*` category, including the formerly accredited
            # ones: a lapsed IFCN renewal does not turn a published adjudication into
            # something else.
            if key.startswith("fact_checkers"):
                fact_checkers.update(hosts)

        user_paths: dict[str, tuple[str, ...]] = {}
        declared = raw.get(_USER_CONTENT_KEY)
        if isinstance(declared, dict):
            for host, prefixes in declared.items():
                if isinstance(host, str) and isinstance(prefixes, list):
                    user_paths[_normalise_host(host)] = tuple(
                        p.lower() for p in prefixes if isinstance(p, str) and p.startswith("/")
                    )

        return cls(frozenset(domains), user_paths, frozenset(fact_checkers))

    def is_credible(self, url_or_domain: str | None) -> bool:
        """Whether this source may be cited as open-web evidence."""
        domain = self._domain_of(url_or_domain)
        if not domain:
            return False

        names = list(_suffixes(domain))
        if any(name in _NOT_INSTITUTIONAL for name in names):
            return False

        # A trusted pattern (pib.gov.in under gov.in) or a listed host (news.bbc.co.uk
        # under bbc.co.uk) — the domain itself or anything beneath it.
        if not any(name in _TRUSTED_SUFFIXES or name in self._trusted for name in names):
            return False

        return not self._is_user_content(names, url_or_domain or "")

    def is_fact_checker(self, url_or_domain: str | None) -> bool:
        """Whether this source publishes fact-checks, rather than reporting generally.

        Used to classify what a page found on the open web *is*: an adjudication from a
        verified fact-checker is the same class of evidence the fact-check API returns,
        reached by another route, and is treated as such.
        """
        domain = self._domain_of(url_or_domain)
        if not domain:
            return False
        return any(name in self._fact_checkers for name in _suffixes(domain))

    def _is_user_content(self, names: list[str], url: str) -> bool:
        """Whether the URL falls in a section of a credible host that anyone can post to."""
        if not self._user_content_paths or "://" not in url:
            return False
        path = urlsplit(url.strip()).path.lower() or "/"
        for name in names:
            prefixes = self._user_content_paths.get(name)
            if prefixes and any(path.startswith(prefix) for prefix in prefixes):
                return True
        return False

    @staticmethod
    def _domain_of(url_or_domain: str | None) -> str:
        if not url_or_domain:
            return ""
        value = url_or_domain.strip().lower()
        if "://" in value:
            # `hostname`, not `netloc`: it drops userinfo and port, so
            # https://thehindu.com@evil.com/ is judged as evil.com — where it goes.
            try:
                host = urlsplit(value).hostname or ""
            except ValueError:  # a malformed netloc, e.g. an unclosed IPv6 bracket
                return ""
        else:
            host = value.split("/")[0].split(":")[0]
        return _normalise_host(host)


def _normalise_host(host: str) -> str:
    return host.strip().lower().removeprefix("www.").rstrip(".")


def _suffixes(domain: str) -> Iterator[str]:
    """The domain and every parent: a.b.example.com, b.example.com, example.com, com."""
    labels = domain.split(".")
    for index in range(len(labels)):
        yield ".".join(labels[index:])
