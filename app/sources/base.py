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

import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol
from urllib.parse import urlsplit

from app.domain.claim import Claim
from app.domain.enums import Direction, EvidenceKind, Method, Relation, Tier
from app.domain.evidence import Evidence, MatchBasis, SourceAnchor
from app.domain.typography import fold, unquoted

# Which check is running. Set by the orchestrator for the length of one verification,
# and inherited by every task it starts, so a resolver that keeps working state can
# keep it per check: nothing one check found or read is visible to another.
current_check: ContextVar[str] = ContextVar("current_check", default="")


# How long the check running now may take, when it runs in the background while the
# app shows its progress: every claim is searched and read, however long that takes,
# up to this. None for a check someone waits on in one request, which keeps the
# orchestrator's own shorter budget. Set for the length of a check like
# `current_check`.
#
# There used to be two kinds of check: a normal one that searched only its three most
# important claims inside 55 seconds, and a deep one for everything. On a phone, most
# claims came back "not checked in a quick check" or "we ran out of time", which read
# as a verdict problem when it was a time limit (2026-09-28). There is one check now.
check_seconds: ContextVar[float | None] = ContextVar("check_seconds", default=None)


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


_MONTHS = {
    name: number
    for number, name in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
        start=1,
    )
}
# /2026/04/28/, /2026/9/25/, /2026/Sep/09/, -2026-02-25, _20260925. Separated so a
# story id that merely contains "2026" is not read as a date.
_URL_DATE = re.compile(
    r"(?<![0-9])(20[0-9]{2})(?:[/_-]([0-9]{1,2}|[A-Za-z]{3})[/_-]([0-9]{1,2})(?![0-9])"
    r"|([01][0-9])([0-3][0-9])(?![0-9]))"
)


def date_in_url(url: str) -> date | None:
    """The publication date a news address carries in its path, if it carries one.

    Most news sites date their URLs, and the date is the one fact about a page that
    tells an old story from a new one. A Politico page on King Charles's state dinner
    in April was read as contradicting the menu of Xi Jinping's in September - both
    are "the White House state dinner" - and its address said 2026/04/28 all along.
    """
    path = urlsplit(url if "://" in url else f"https://{url}").path
    for match in _URL_DATE.finditer(path):
        year = int(match.group(1))
        if match.group(2):
            raw_month, raw_day = match.group(2), match.group(3)
        else:
            raw_month, raw_day = match.group(4), match.group(5)
        month = _MONTHS.get(raw_month.lower()) if raw_month.isalpha() else int(raw_month)
        if month is None:
            continue
        try:
            return date(year, month, int(raw_day))
        except ValueError:
            continue
    return None


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

    # How this text was obtained: our own fetch, a vendor's extraction endpoint, or a
    # search snippet. Recorded because the three are not equivalent evidence and were
    # being presented as though they were — a 209-character snippet cannot support a
    # quote that genuinely exists on the page, so "we could not read this" and "the
    # page does not say this" must stay distinguishable in the ledger.
    extraction_route: str = ""

    @property
    def published_on(self) -> date | None:
        """When the page appeared: the provider's date, else the one in its address."""
        if self.published_at is not None:
            return self.published_at.date()
        return date_in_url(self.final_url or self.url)

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

    `tier`, `kind` and `method` are declared by the resolver rather than assigned by
    whatever assembles the evidence. A resolver knows what class of finding it can
    produce; an assembler that decided per-item would be free to promote a weak
    finding into a strong tier, which is exactly the judgement the tier system exists
    to take away from any single component.
    """

    name: str
    version: str
    allowed_domains: frozenset[str]

    tier: Tier
    kind: EvidenceKind
    method: Method

    async def candidates(self, claim: Claim) -> list[SourceCandidate]: ...

    async def snapshot(self, candidate: SourceCandidate) -> SourceSnapshot | None: ...

    async def relate(self, claim: Claim, snapshot: SourceSnapshot) -> SourceRelation: ...


_DIRECTION_FOR = {
    Relation.SUPPORTS: Direction.SUPPORTS,
    Relation.CONTRADICTS: Direction.CONTRADICTS,
    Relation.CONTEXTUALIZES: Direction.CONTEXTUALIZES,
}


def build_evidence(
    *,
    resolver: SourceResolver,
    claim_id: str,
    snapshot: SourceSnapshot,
    relation: SourceRelation,
) -> Evidence | None:
    """Turn a relation and its snapshot into one citable evidence item.

    Returns `None` rather than raising when the relation is not citable, because a
    resolver finding nothing is the ordinary case and not an error.

    Every field here comes from something recorded: the excerpt was located in the
    fetched text, the anchor is its offsets, the basis is the metric the resolver
    measured. Nothing is asserted by the assembler, and `match_quality` is derived
    from the basis by the model itself — so this function cannot upgrade a finding
    even if it wanted to.

    A resolver whose sources are not all one class may implement `classify(snapshot)`
    and return the tier, kind and method for that particular source — the open-web
    resolver reaches both verified fact-checkers and ordinary reporting. The producer
    still decides, which is the point of declaring these on the resolver: this
    function only asks, and has no branch that could promote a finding on its own.
    """
    if not relation.is_citable:
        return None

    direction = _DIRECTION_FOR.get(relation.relation)
    if direction is None:
        return None

    anchor = SourceAnchor(
        char_start=relation.anchor.get("char_start"),
        char_end=relation.anchor.get("char_end"),
    )

    classify = getattr(resolver, "classify", None)
    tier, kind, method = (
        classify(snapshot)
        if classify is not None
        else (resolver.tier, resolver.kind, resolver.method)
    )

    return Evidence.build(
        id=f"ev:{resolver.name}:{snapshot.content_hash[:16]}:{claim_id}",
        claim_id=claim_id,
        tier=tier,
        kind=kind,
        direction=direction,
        method=method,
        finding=relation.excerpt[:400],
        citation_url=snapshot.final_url or snapshot.url,
        snapshot_id=snapshot.id,
        source_excerpt=relation.excerpt,
        source_anchor=anchor,
        match_basis=MatchBasis(
            metric=relation.metric or "unspecified",
            value=relation.value,
            threshold=relation.threshold,
        ),
        publisher=snapshot.publisher,
        title=snapshot.title,
        published_on=snapshot.published_on,
        provider=relation.validator,
        provider_version=relation.validator_version,
        observed_at=snapshot.fetched_at,
    )


def locate_excerpt(text: str, needle: str, *, window: int = 220) -> tuple[str, dict[str, int]]:
    """Find a phrase in a source and return it with its offsets.

    Returns an empty excerpt when the phrase is absent, which callers turn into
    `INSUFFICIENT`. A resolver must never invent the excerpt it cites — that is the
    one thing this function exists to make impossible to do by accident.

    Matched with the same tolerance as the quote gate in `reasoning.verify_quote`:
    typography folded, and quotation marks ignored on a second try. It used to match
    only case and whitespace, so a quote the gate had accepted — curly marks on the
    page, straight in the model's copy — was dropped here without a word. Live: both
    of The Hindu's reports of the story a person pasted were read, judged SUPPORTS,
    passed the gate, and vanished at this line.
    """
    haystack = fold(text)
    target = fold(needle)

    if not target or not haystack:
        return "", {}

    position = haystack.find(target)
    if position == -1:
        haystack, target = unquoted(haystack), unquoted(target)
        position = haystack.find(target) if target else -1
        if position == -1:
            return "", {}

    start = max(0, position - window // 2)
    end = min(len(haystack), position + len(target) + window // 2)

    # Snap the window out to whitespace so the quotation does not begin or end
    # mid-word. A citation rendered as "om hereon is simple" reads as a broken
    # excerpt and invites doubt about whether the rest was quoted faithfully.
    # Only the displayed window moves; the offsets below still point at the match.
    if start > 0:
        space = haystack.rfind(" ", 0, start)
        start = 0 if space == -1 else space + 1
    if end < len(haystack):
        space = haystack.find(" ", end)
        end = len(haystack) if space == -1 else space

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
    # Every Indian script and Arabic, as in corpus.py's word pattern.
    tokenise = re.compile(r"[a-z0-9\u0900-\u0d7f\u0600-\u06ff\u0750-\u077f]+")

    claim_words = {
        word
        for word in tokenise.findall(claim_text.lower())
        if word not in stop and len(word) >= minimum_length
    }
    if not claim_words:
        return 0.0

    source_words = set(tokenise.findall(source_text.lower()))
    shared = claim_words & source_words
    # Numbers alone are not a match: "2023" is in half the news.
    if all(word.isdigit() for word in shared):
        return 0.0
    return len(shared) / len(claim_words)
