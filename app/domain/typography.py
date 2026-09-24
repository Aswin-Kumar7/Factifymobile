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


# Quotation marks and dashes, one character for one, so offsets into the text survive.
_PLAIN = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "‐": "-",
        "‑": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
    }
)


def plain_punctuation(text: str) -> str:
    """The text with typographic quotes and dashes written plainly, nothing else changed.

    For text shown to a model that will be asked to copy from it. Asked to quote The
    Hindu's `for “undermining” voter rights`, the model returned
    `for \u00147undermining\u00148`, and from another page an em dash came back as a
    tab and a `6` — control characters and digits where the typography was — so the
    quotes failed the verbatim check. Plain marks are copied faithfully. Same length,
    so a position in one is a position in the other.
    """
    return text.translate(_PLAIN)


def fold(text: str) -> str:
    """Lowercased, whitespace-flattened and typography-folded, for locating text."""
    return " ".join(text.lower().translate(_TYPOGRAPHY).split())


def unquoted(folded: str) -> str:
    """Folded text without quotation or blockquote marks, whitespace flattened again.

    The second try when a quote is not found as written. Reporting splices a quoted
    remark into its attribution — `"...before coming to Delhi," Mr. Dipke said` — and
    a model copying the sentence drops the marks around the remark. Every word must
    still be there, in order: only the marks are ignored.
    """
    return " ".join(folded.replace('"', "").replace("'", "").replace(">", " ").split())
