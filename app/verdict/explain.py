"""The one-line explanation under a verdict, written from the evidence, not by a model.

It was the model's: the source check wrote a sentence or two for every claim. It read
well and it was one more thing a hosted model decided, in words nobody could trace
back to a rule - and it once said "pib.gov.in confirms the National Sports Scholarship
portal is open" under a claim the rules had correctly declined to call true.

Now it is a template over what decided the claim: the most authoritative source among
those that carry the verdict, named, and its own sentence quoted - the same sentence
the verbatim check located in the page. So the explanation can only ever say what a
cited source says, in that source's words, and it reads the same whoever asks.

In English or Hindi, by the claim's language. The quote stays in the language of its
page.
"""

from __future__ import annotations

from app.domain.enums import ClaimStatus, Credibility, Direction, EvidenceKind, Tier
from app.domain.evidence import Evidence, is_narrower_scope
from app.domain.publishers import publishers_of

# The quote is cut here, at a word.
_QUOTE = 170

_TIER = {Tier.A: 0, Tier.B: 1, Tier.C: 2, Tier.D: 3}
_CREDIBILITY = {Credibility.HIGH: 0, Credibility.MEDIUM: 1, Credibility.LOW: 3}

_TEXT = {
    "en": {
        "factcheck": "{who} has fact-checked this and found it false: “{quote}”",
        "contradicts": "{who} reports otherwise: “{quote}”",
        "supports": "{who} confirms it: “{quote}”",
        "narrower": "Only a narrower version of this is reported. {who}: “{quote}”",
        "media": "The picture is real but older: {who} published it on {date}.",
        "others": " {n} other sources say the same.",
        "other": " 1 other source says the same.",
    },
    "hi": {
        "factcheck": "{who} ने इसकी फ़ैक्ट-चेक की है और इसे गलत पाया: “{quote}”",
        "contradicts": "{who} की रिपोर्ट कुछ और कहती है: “{quote}”",
        "supports": "{who} इसकी पुष्टि करता है: “{quote}”",
        "narrower": "इसका केवल एक सीमित रूप ही रिपोर्ट हुआ है। {who}: “{quote}”",
        "media": "तस्वीर असली है पर पुरानी है: {who} ने इसे {date} को प्रकाशित किया था।",
        "others": " {n} और स्रोत भी यही कहते हैं।",
        "other": " 1 और स्रोत भी यही कहता है।",
    },
}


def explain(
    status: ClaimStatus,
    evidence: list[Evidence],
    carrying_ids: tuple[str, ...],
    *,
    language: str | None,
) -> str | None:
    """The explanation for a decided claim, or None when nothing carries it."""
    text = _TEXT.get(language or "en", _TEXT["en"])
    carrying = [e for e in evidence if e.id in carrying_ids]
    if not carrying:
        return None
    ranked = sorted(carrying, key=_rank)
    top = ranked[0]
    others = len({_who(e) for e in ranked}) - 1

    if status is ClaimStatus.CONTRADICTED:
        template = "factcheck" if top.kind is EvidenceKind.FACT_CHECK else "contradicts"
    elif status is ClaimStatus.SUPPORTED:
        template = "supports"
    elif status is ClaimStatus.MISLEADING_CONTEXT:
        if top.kind in {EvidenceKind.MEDIA_MATCH, EvidenceKind.DATED_SOURCE} and (
            top.published_on is not None
        ):
            return text["media"].format(who=_who(top), date=top.published_on.isoformat())
        template = "narrower"
    else:
        return None

    line = text[template].format(who=_who(top), quote=_quoted(top.source_excerpt))
    if others == 1:
        line += text["other"]
    elif others > 1:
        line += text["others"].format(n=others)
    return line


def narrower_note(evidence: list[Evidence], *, language: str | None) -> str | None:
    """For a claim left undecided, when a source shows a narrower version of it: say
    so, rather than that nothing addressed it."""
    narrower = [
        e
        for e in evidence
        if e.direction is Direction.CONTEXTUALIZES and is_narrower_scope(e.match_basis.metric)
    ]
    if not narrower:
        return None
    top = sorted(narrower, key=_rank)[0]
    text = _TEXT.get(language or "en", _TEXT["en"])
    return text["narrower"].format(who=_who(top), quote=_quoted(top.source_excerpt))


def _rank(item: Evidence) -> tuple[int, int, int]:
    return (
        0 if item.kind is EvidenceKind.FACT_CHECK else 1,
        _TIER.get(item.tier, 4),
        _CREDIBILITY.get(item.credibility, 2) if item.credibility else 2,
    )


def _who(item: Evidence) -> str:
    name = (item.publisher or "").strip()
    # The site, when the page named no publisher; the pure helper the rules use.
    return name or next(iter(publishers_of([item.citation_url])), item.citation_url)


def _quoted(excerpt: str) -> str:
    line = " ".join(excerpt.split()).strip(" “”\"'")
    if len(line) <= _QUOTE:
        return line
    return line[:_QUOTE].rsplit(" ", 1)[0].rstrip(",;:") + "…"
