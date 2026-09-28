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

import hashlib
import json
import logging
from collections.abc import Iterator, Mapping
from pathlib import Path
from urllib.parse import urlsplit

from app.domain.enums import Credibility
from app.domain.publishers import is_official

logger = logging.getLogger("factify.sources.credibility")

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

# Which categories of the curated list carry which weight.
#
# HIGH is for publishers whose job is to get this kind of claim right and who answer
# for it: accredited fact-checkers, wire services, public broadcasters, official and
# intergovernmental bodies, and the medical and scientific literature. MEDIUM is the
# rest of the named newsrooms and reference works. Anything the gate admits without
# naming — an institution trusted only by its domain suffix — is LOW until someone
# lists it.
_HIGH_CATEGORY_PREFIXES = (
    "fact_checkers",
    "wire_services",
    "public_broadcasters",
    "international_organisations",
    "india_official_and_legal",
    "health_and_medicine",
    "science_and_research",
)
_MEDIUM_CATEGORY_PREFIXES = (
    "india_",
    "news_",
    "south_asia_news",
    "investigative_and_explainers",
    "reference",
    "sports_news",
    "climate_and_environment",
    "disinformation_research",
    "government_and_academic_domains",
)

# Which categories are read first when a search returns more credible pages than there
# are read slots. The publishers most people mean by "the news" — wires, the national
# press, public broadcasters, the major international papers — plus the bodies whose
# word settles a claim outright: official and intergovernmental sources, the health and
# science literature, and fact-checkers, who are how a fake gets refuted. Regional
# papers, reference works and everything else are still read when there is room; this
# orders the queue, it does not shorten the list.
_PROMINENT_CATEGORY_PREFIXES = (
    "fact_checkers",
    "wire_services",
    "public_broadcasters",
    "india_national_news",
    "india_official_and_legal",
    "news_",
    "sports_news",
    "international_organisations",
    "health_and_medicine",
    "science_and_research",
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
        high: frozenset[str] = frozenset(),
        medium: frozenset[str] = frozenset(),
        prominent: frozenset[str] = frozenset(),
        certified: frozenset[str] = frozenset(),
    ) -> None:
        self._trusted = trusted
        # The fact-checkers verified by IFCN or EFCSN now: `fact_checkers` less the
        # formerly verified.
        self._certified = certified
        self._high = high
        self._medium = medium
        self._prominent = prominent
        self._user_content_paths = dict(user_content_paths or {})
        # Publishers whose business is adjudicating claims. A page of theirs is a
        # published fact-check wherever it was found, which is a stronger class of
        # evidence than a news report that happens to bear on the claim.
        self._fact_checkers = fact_checkers
        # What this list says, in eight characters. The verdict cache is keyed on
        # the search resolver's version, which carries this: a host added or removed
        # changes which pages a check may read, so answers cached under the old list
        # must not be served. Adding News18 without it would have kept serving the
        # "Unconfirmed" cached before News18 could be read.
        self.fingerprint = hashlib.sha256(
            json.dumps(
                [
                    sorted(trusted),
                    sorted(fact_checkers),
                    sorted(high),
                    sorted(medium),
                    sorted(prominent),
                    sorted((k, list(v)) for k, v in self._user_content_paths.items()),
                ]
            ).encode()
        ).hexdigest()[:8]

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
        high: set[str] = set()
        medium: set[str] = set()
        prominent: set[str] = set()
        certified: set[str] = set()
        for key, value in raw.items():
            if key.startswith("_") or not isinstance(value, list):
                continue
            hosts = {_normalise_host(d) for d in value if isinstance(d, str)}
            domains.update(hosts)
            if key.startswith(_HIGH_CATEGORY_PREFIXES):
                high.update(hosts)
            elif key.startswith(_MEDIUM_CATEGORY_PREFIXES):
                medium.update(hosts)
            if key.startswith(_PROMINENT_CATEGORY_PREFIXES):
                prominent.update(hosts)
            # Every `fact_checkers_*` category, including the formerly accredited
            # ones: a lapsed IFCN renewal does not turn a published adjudication into
            # something else.
            if key.startswith("fact_checkers"):
                fact_checkers.update(hosts)
                if not key.startswith("fact_checkers_formerly"):
                    certified.update(hosts)

        user_paths: dict[str, tuple[str, ...]] = {}
        declared = raw.get(_USER_CONTENT_KEY)
        if isinstance(declared, dict):
            for host, prefixes in declared.items():
                if isinstance(host, str) and isinstance(prefixes, list):
                    user_paths[_normalise_host(host)] = tuple(
                        p.lower() for p in prefixes if isinstance(p, str) and p.startswith("/")
                    )

        return cls(
            frozenset(domains),
            user_paths,
            frozenset(fact_checkers),
            frozenset(high),
            frozenset(medium),
            frozenset(prominent),
            frozenset(certified),
        )

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

    def credibility(self, url_or_domain: str | None) -> Credibility:
        """How much this publisher's word weighs, for a source already found relevant.

        Only ever asked of a source that passed `is_credible`, so LOW means "citable
        but unranked", not "untrustworthy". Government and intergovernmental domains
        rank HIGH by suffix because their registries are restricted; a university
        ranks MEDIUM, since the domain vouches for the institution and not for
        every page published under it.
        """
        domain = self._domain_of(url_or_domain)
        names = list(_suffixes(domain)) if domain else []
        if any(name in self._high or name in self._fact_checkers for name in names):
            return Credibility.HIGH
        if url_or_domain and is_official(url_or_domain):
            return Credibility.HIGH
        if any(name in self._medium for name in names):
            return Credibility.MEDIUM
        if any(name in _TRUSTED_SUFFIXES for name in names):
            return Credibility.MEDIUM
        return Credibility.LOW

    def is_prominent(self, url_or_domain: str | None) -> bool:
        """Whether this publisher is read first when read slots are scarce.

        Government and intergovernmental domains count by suffix, as they do for
        credibility. A university or an unlisted institution does not: it is citable,
        not a first read.
        """
        domain = self._domain_of(url_or_domain)
        if not domain:
            return False
        if any(name in self._prominent for name in _suffixes(domain)):
            return True
        return bool(url_or_domain) and is_official(url_or_domain or "")

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

    def is_certified_fact_checker(self, url_or_domain: str | None) -> bool:
        """Whether this fact-checker is verified by IFCN or EFCSN now, as the list says."""
        domain = self._domain_of(url_or_domain)
        if not domain:
            return False
        return any(name in self._certified for name in _suffixes(domain))

    # Subdomains conventionally given over to individuals. A university is credible
    # about what the university did; a lecturer's own page on the same domain is one
    # person writing, and the registrable domain cannot tell them apart.
    #
    # Live: "IIT Madras inaugurated a robotics laboratory" was carried by PIB, the
    # Times of India and the Indian Express, and abstained under
    # `rule.conflicting_evidence` because `home.iitm.ac.in/samuelgl/inauguration.html`
    # — a faculty page about a different inauguration — was read as contradicting it.
    # Not "web.": `web.mit.edu` is MIT's own site, which a test in this repo already
    # asserted and which this list briefly broke.
    _PERSONAL_HOSTS = ("home.", "people.", "users.", "sites.", "staff.", "faculty.")

    def _is_user_content(self, names: list[str], url: str) -> bool:
        """Whether the URL falls in a section of a credible host that anyone can post to."""
        host = url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
        host = host.split(":", 1)[0].lower().removeprefix("www.")
        if host.startswith(self._PERSONAL_HOSTS):
            return True
        # A tilde path is the oldest convention for the same thing.
        if "/~" in url:
            return True

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
