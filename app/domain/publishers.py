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
