"""Folding typographic variants that mean the same character.

Shared by every check that asks "is this text in that text?" — the quote gate on
model citations and the anchor check on extracted claims — because the failure is the
same in both. News pages mix curly and straight quotes, en dashes and hyphens, often in
one article, so a model copying faithfully cannot reproduce "the" convention: there is
none. Folding these lets the same text match however it was set; it lets no different
text match, because it never touches a letter, a digit or a word.
"""

from __future__ import annotations

_TYPOGRAPHY = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "″": '"',
        "‐": "-",
        "‑": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "­": "",
    }
)


def fold(text: str) -> str:
    """Lowercased, whitespace-flattened and typography-folded, for locating text."""
    return " ".join(text.lower().translate(_TYPOGRAPHY).split())
