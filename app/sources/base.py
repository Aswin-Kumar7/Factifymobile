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

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class SearchDepth:
    """How hard one check looks: the normal check, or the deep one a person asked for.

    Set for the length of a check like `current_check`, and read where each limit
    applies — the orchestrator for claims and time, the web-search resolver for
    queries and pages — so a deep check changes how much is done, never how it is
    judged.
    """

    name: str
    claims: int  # claims searched on the open web
    queries: int  # search queries per claim
    pages: int  # pages read per claim
    seconds: float  # the check's time budget


NORMAL = SearchDepth("normal", claims=5, queries=4, pages=6, seconds=55.0)
# About two and a half times the searching of a normal check, for three credits; long
# enough that it runs in the background while the app shows its progress.
DEEP = SearchDepth("deep", claims=10, queries=5, pages=10, seconds=180.0)

current_depth: ContextVar[SearchDepth] = ContextVar("current_depth", default=NORMAL)


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

    # How this text was obtained: our own fetch, a vendor's extraction endpoint, or a
    # search snippet. Recorded because the three are not equivalent evidence and were
    # being presented as though they were — a 209-character snippet cannot support a
    # quote that genuinely exists on the page, so "we could not read this" and "the
    # page does not say this" must stay distinguishable in the ledger.
    extraction_route: str = ""

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
