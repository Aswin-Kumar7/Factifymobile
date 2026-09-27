"""The message sent back to the chat with a correction (v5, 4.6).

Short and polite, because it is read by family and friends: "Hi! I checked this
before forwarding..." A correction that arrives as an accusation gets argued with; one
that arrives as a shared check gets read.

Built from templates, never from a model, so every message says exactly what the
answer says and nothing more:

  - False, Misleading and True name the source that decided them, with its link. A
    verdict word never travels without the source behind it.
  - Unconfirmed says it could not be confirmed and suggests holding off. It never says
    "false": not finding a source is not the same as finding it wrong.

The English message carries the first sentence of the result's summary. The summary is written in
English, so the Hindi message leaves it out rather than mix languages mid-sentence; it
says the verdict and names the source, which is the part that matters. The Hindi
templates should be read by a native speaker before they are relied on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.domain.enums import ClaimStatus, Verdict

# The summary is cut here, at a word boundary.
_SUMMARY_CHARACTERS = 280
# Where one sentence ends and the next begins. A dot inside a name (factcheck.afp.com)
# has no space after it, so it is not an end.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")
# Links sent beside the message.
_LINKS = 2

# How a sentence ends: a full stop in English, a purna viram in Hindi.
_STOP = {"en": ".", "hi": "।"}
_OPENING = {
    "en": "Hi! I checked this before forwarding.",
    "hi": "नमस्ते! आगे भेजने से पहले मैंने इसे जाँचा।",
}
_SAYS = {
    "en": {
        Verdict.FALSE: "Factify says it's false",
        Verdict.MISLEADING: "Factify says it's misleading",
        Verdict.TRUE: "Factify says it's true",
    },
    "hi": {
        Verdict.FALSE: "Factify के अनुसार यह झूठ है",
        Verdict.MISLEADING: "Factify के अनुसार यह भ्रामक है",
        Verdict.TRUE: "Factify के अनुसार यह सच है",
    },
}
_UNCONFIRMED = {
    "en": (
        "Hi! I tried to check this before forwarding. Factify couldn't find reliable "
        "sources confirming it yet, so it may be best not to forward it for now."
    ),
    "hi": (
        "नमस्ते! आगे भेजने से पहले मैंने इसे जाँचने की कोशिश की। Factify को अभी तक "
        "भरोसेमंद स्रोतों से इसकी पुष्टि नहीं मिली, इसलिए फ़िलहाल इसे आगे न भेजना "
        "बेहतर होगा।"
    ),
}

# The claim statuses and source directions that carry each verdict.
_CARRIED_BY: dict[Verdict, tuple[set[ClaimStatus], set[str]]] = {
    Verdict.FALSE: ({ClaimStatus.CONTRADICTED}, {"contradicts"}),
    Verdict.MISLEADING: (
        {ClaimStatus.MISLEADING_CONTEXT, ClaimStatus.CONTRADICTED},
        {"contradicts", "contextualizes"},
    ),
    Verdict.TRUE: ({ClaimStatus.SUPPORTED}, {"supports"}),
}
_IMPORTANCE = {"HEADLINE": 0, "MAIN_THESIS": 1, "SUPPORTING_DETAIL": 2, "BACKGROUND": 3}
_TIER = {"A": 0, "B": 1, "C": 2, "D": 3}
_CREDIBILITY = {"HIGH": 0, "MEDIUM": 1}


@dataclass(frozen=True, slots=True)
class CorrectionMessage:
    message: str
    links: tuple[str, ...]


def correction_message(case: Any, language: str) -> CorrectionMessage:
    """The polite message for a stored case, in English ("en") or Hindi ("hi")."""
    language = language if language in _OPENING else "en"
    verdict = Verdict(case.verdict)
    sources = _sources(case, verdict)
    if verdict is Verdict.UNCONFIRMED or not sources:
        # A decided verdict always has a source by the contract; if one ever did
        # not, the message falls back to claiming nothing rather than naming none.
        return CorrectionMessage(message=_UNCONFIRMED[language], links=())

    top = sources[0]
    who = (top.publisher or "").strip() or urlsplit(top.citation_url).netloc.removeprefix("www.")
    says = _SAYS[language][verdict]
    summary = _shortened(case.summary or "") if language == "en" else ""
    said = f"{says}: {summary}" if summary else f"{says}{_STOP[language]}"
    links = tuple(dict.fromkeys(e.citation_url for e in sources))[:_LINKS]
    return CorrectionMessage(
        message=f"{_OPENING[language]} {said} {who}: {top.citation_url}",
        links=links,
    )


def _sources(case: Any, verdict: Verdict) -> list[Any]:
    """The citations behind the verdict, best first: from the most important deciding
    claim, stronger tiers before weaker, credible publishers before others."""
    carried = _CARRIED_BY.get(verdict)
    if carried is None:
        return []
    statuses, directions = carried
    claims = sorted(
        (c for c in case.claims if ClaimStatus(c.status) in statuses),
        key=lambda c: _IMPORTANCE.get(str(c.importance), 4),
    )
    for claim in claims:
        cited = [e for e in claim.evidence if str(e.direction) in directions]
        if cited:
            return sorted(
                cited,
                key=lambda e: (
                    _TIER.get(str(e.tier), 4),
                    _CREDIBILITY.get(str(e.credibility or ""), 2),
                ),
            )
    return []


def _shortened(summary: str) -> str:
    """The summary's first sentence, cut at a word if it is still long. A summary
    can run to several sentences; a note to family should not."""
    text = " ".join(summary.split())
    first = _SENTENCE_END.split(text, maxsplit=1)[0]
    # A first "sentence" this short is an abbreviation ("Dr."), not a sentence.
    if len(first) >= 20:
        text = first
    if len(text) > _SUMMARY_CHARACTERS:
        text = text[:_SUMMARY_CHARACTERS].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    elif text and text[-1] not in ".!?…":
        text += "."
    return text
