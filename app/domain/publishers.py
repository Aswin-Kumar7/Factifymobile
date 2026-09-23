"""Who published a citation, derived from its URL and nothing else.

Split out of the verdict engine so the rules and the corroboration count agree on
what "a different publisher" means. They were answering that question in two places
before, and a disagreement between them is invisible: the engine would see two
publishers contradicting a claim where the origin count saw one, and no test would
fail.

Deliberately dependency-free — no urllib, no network, no public-suffix list. The
verdict core may not import I/O, because a verdict reproducible from plain values is
what makes an audit possible, and splitting a URL needs no library.
"""

from __future__ import annotations

# Second-level labels that are part of the suffix rather than the name: under
# `co.in`, `ac.uk` or `gov.au` the registrable domain is the third label from the
# right. Not a public-suffix list — a short list of what appears in practice, with
# the failure mode of treating two unrelated sites as one publisher, which is the
# cautious direction.
_SUFFIX_LABELS = frozenset({"co", "com", "org", "net", "ac", "gov", "edu", "or", "go", "ne"})


def registrable_domain(url: str) -> str | None:
    """The publisher behind a URL, or `None` if there is no host to read.

    By registrable domain rather than by host: `newsnetwork.mayoclinic.org` and
    `mayoclinic.org` are one publisher saying something twice, and counting them as
    two would manufacture the independence the rules are asking about.
    """
    rest = url.split("://", 1)[-1]
    host = rest.split("/", 1)[0].split("?", 1)[0].split("@")[-1]
    host = host.split(":", 1)[0].lower().removeprefix("www.")
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return None
    keep = 3 if len(labels) >= 3 and labels[-2] in _SUFFIX_LABELS else 2
    return ".".join(labels[-keep:])


def publishers_of(urls: list[str]) -> set[str]:
    """The distinct publishers behind a set of URLs."""
    return {domain for url in urls if (domain := registrable_domain(url)) is not None}


# Hosts that are the authority on their own subject rather than a report of it.
#
# A government gazette, a ministry release, a central bank notice, an intergovernmental
# body: on what that body did, announced or found, it is the primary record and the
# only place the fact originates. Asking two of them to agree asks for something that
# does not exist — the origin rule wants independent *witnesses* to an event, and
# there is exactly one witness to a ministry's own announcement.
#
# By suffix, never by a curated list of names: a list of official domains is a list
# that goes stale, and the suffixes are administered.
_OFFICIAL_SUFFIXES = (
    ".gov",
    ".mil",
    ".int",
    ".gov.in",
    ".nic.in",
    ".gov.uk",
    ".gov.au",
    ".govt.nz",
    ".gc.ca",
    ".go.jp",
    ".go.kr",
    ".gov.sg",
    ".gob.mx",
    ".gov.br",
    ".gov.za",
    ".europa.eu",
    ".un.org",
    ".who.int",
)

# The whole domain is official, not merely a suffix match. `rbi.org.in` is the
# Reserve Bank; `something.org.in` is not, so these are matched exactly.
_OFFICIAL_DOMAINS = frozenset(
    {
        "rbi.org.in",
        "sebi.gov.in",
        "pib.gov.in",
        "who.int",
        "un.org",
        "imf.org",
        "worldbank.org",
        "europa.eu",
        "oecd.org",
        "unesco.org",
        "unicef.org",
    }
)


def is_official(url: str) -> bool:
    """Whether this URL is a government or intergovernmental primary source.

    Used by the corroboration rule, which otherwise asks for two independent origins
    before it will call a claim supported. For a fact whose origin *is* the body
    reporting it, that bar cannot be met honestly: "IIT Madras opened a laboratory"
    was carried by PIB and by IIT Madras itself and abstained for having one origin,
    while the two sources between them are the entire primary record.

    This never makes a source *credible* — the allowlist decides that, and it never
    makes an official statement true. It says only that one such source is enough to
    stop the count being the reason we abstain.
    """
    domain = registrable_domain(url)
    if domain is None:
        return False
    if domain in _OFFICIAL_DOMAINS:
        return True

    host = url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].split("@")[-1]
    host = host.split(":", 1)[0].lower().removeprefix("www.")
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in _OFFICIAL_SUFFIXES)
