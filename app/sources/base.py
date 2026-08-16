"""The source resolver framework (M28).

The single mechanism by which "check the source" happens. Every evidence producer
implements this shape, so there is one place that decides what may become a citation
and one place to read when asking why something did.

Three stages, deliberately separate:

    candidates(claim)      what might answer this
    snapshot(candidate)    fetch it and record what came back
    relate(claim, snap)    what does this source actually say about the claim

The separation is the point. A resolver that fused them could return "this page
supports the claim" without ever having fetched a page, and nothing downstream could
tell. Splitting them means the snapshot exists as evidence that the fetch happened,
and `relate` has to point at text inside it.

**A model statement is not a relation.** `relate` may use structured extraction or a
bounded model proposal, but it must return the exact source excerpt and its anchor.
"The page supports this" with no excerpt is an opinion about a page, not a finding
from one.

**`INSUFFICIENT` is a correct outcome.** A source that cannot be located, fetched,
anchored and cited produces `INSUFFICIENT` and the claim stays `UNVERIFIED`. That is
the system working, not failing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import Relation


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """Something that might answer a claim. Not yet fetched, not yet evidence."""

    url: str
    publisher: str | None = None
    title: str | None = None
    published_at: datetime | None = None
    # Why this candidate was proposed — recorded so a reader can see whether the
    # shortlist was reasonable, not just what survived it.
    proposed_by: str = ""
    prior_score: float = 0.0

    @property
    def domain(self) -> str:
        return urlsplit(self.url).netloc.lower()


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Proof that a fetch happened, and what it returned.

    Every evidence object references one of these. Without it a citation is an
    assertion about a page nobody can prove was read.
    """

    id: str
    url: str
    final_url: str
    content_hash: str
    fetched_at: datetime
    text: str = ""
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    http_status: int | None = None

    @property
    def domain(self) -> str:
        return urlsplit(self.final_url).netloc.lower()


@dataclass(frozen=True, slots=True)
class SourceRelation:
    """What a snapshot says about a claim, with the text that says it."""

    relation: Relation
    validator: str
    validator_version: str
    excerpt: str = ""
    anchor: dict[str, int] = field(default_factory=dict)
    metric: str = ""
    value: float = 0.0
    threshold: float = 0.0

    def __post_init__(self) -> None:
        if self.relation is not Relation.INSUFFICIENT and not self.excerpt:
            raise ValueError(
                f"{self.validator} returned {self.relation} without an excerpt; a "
                "relation with no quoted text is an opinion about a page, not a "
                "finding from one"
            )

    @property
    def is_citable(self) -> bool:
        """Whether this can become an evidence object at all."""
        return self.relation is not Relation.INSUFFICIENT and bool(self.excerpt)


def insufficient(validator: str, version: str, reason: str) -> SourceRelation:
    """The honest empty answer, with the reason preserved for the ledger.

    Used everywhere a source could not be located, fetched, anchored or quoted. The
    reason travels in `metric` so the response can say what was attempted rather than
    only that nothing was found.
    """
    return SourceRelation(
        relation=Relation.INSUFFICIENT,
        validator=validator,
        validator_version=version,
        metric=reason or "not resolvable",
    )


class SourceResolver(Protocol):
    """Every evidence producer implements this.

    `allowed_domains` empty means the resolver works over sources proposed elsewhere
    — the corpus, or a URL the user supplied — rather than crawling. No resolver
    reaches the open web on its own.
    """

    name: str
    version: str
    allowed_domains: frozenset[str]

    async def candidates(self, claim: Claim) -> list[SourceCandidate]: ...

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None: ...

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation: ...


def locate_excerpt(text: str, needle: str, *, window: int = 220) -> tuple[str, dict[str, int]]:
    """Find a phrase in a source and return it with its offsets.

    Returns an empty excerpt when the phrase is absent, which callers turn into
    `INSUFFICIENT`. A resolver must never invent the excerpt it cites — that is the
    one thing this function exists to make impossible to do by accident.
    """
    haystack = " ".join(text.lower().split())
    target = " ".join(needle.lower().split())

    if not target or not haystack:
        return "", {}

    position = haystack.find(target)
    if position == -1:
        return "", {}

    start = max(0, position - window // 2)
    end = min(len(haystack), position + len(target) + window // 2)

    return haystack[start:end].strip(), {"char_start": position, "char_end": position + len(target)}


def keyword_overlap(claim_text: str, source_text: str, *, minimum_length: int = 4) -> float:
    """Share of a claim's significant words that appear in a source.

    A blunt instrument, used only to decide whether a source is worth a closer look.
    It never produces a relation on its own — the caller still has to find and quote
    actual text before anything becomes evidence.
    """
    import re

    stop = {
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "with",
        "by",
        "from",
        "as",
        "it",
        "its",
        "this",
        "that",
        "has",
        "have",
        "had",
        "said",
        "will",
        "after",
        "over",
    }
    tokenise = re.compile(r"[a-z0-9ऀ-ॿ]+")

    claim_words = {
        word
        for word in tokenise.findall(claim_text.lower())
        if word not in stop and len(word) >= minimum_length
    }
    if not claim_words:
        return 0.0

    source_words = set(tokenise.findall(source_text.lower()))
    return len(claim_words & source_words) / len(claim_words)
