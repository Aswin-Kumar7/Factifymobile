"""Language and script detection (M19).

Deterministic first, model only as a fallback that rarely fires. This runs on every
input, and spending a model call on something a character-range check answers would
be spending the scarcest budget in the system on the cheapest question.

Hinglish is treated as its own register rather than as bad English. It is the default
way Indian WhatsApp is written — Hindi words in Latin script, English syntax — and a
detector that calls it "English" will hand an English-only prompt a sentence it
cannot segment, and route the output to the wrong response template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Language(StrEnum):
    """Scope is what we can evaluate. Anything else is named and abstained on."""

    ENGLISH = "en"
    HINDI = "hi"
    HINGLISH = "hi-Latn"
    UNKNOWN = "und"


class Script(StrEnum):
    LATIN = "Latn"
    DEVANAGARI = "Deva"
    BENGALI = "Beng"
    TAMIL = "Taml"
    TELUGU = "Telu"
    ARABIC = "Arab"
    MIXED = "Zyyy"
    UNKNOWN = "Zzzz"


_SCRIPT_RANGES: tuple[tuple[Script, int, int], ...] = (
    (Script.DEVANAGARI, 0x0900, 0x097F),
    (Script.BENGALI, 0x0980, 0x09FF),
    (Script.TAMIL, 0x0B80, 0x0BFF),
    (Script.TELUGU, 0x0C00, 0x0C7F),
    (Script.ARABIC, 0x0600, 0x06FF),
)

# Hindi function words as they are actually typed in Latin script. Function words
# rather than nouns on purpose: nouns are borrowed in both directions and prove
# nothing, while "hai", "nahi" and "kya" appear in almost every Hinglish sentence and
# essentially never in English prose.
# Words that are also common English words are deliberately absent, however useful
# they look as Hindi function words. "the" is Hindi past-tense plural and the single
# most common word in English; including it made every English sentence read as
# Hinglish. The same goes for "me", "par", "wo", "share" and "forward". A marker that
# fires on English is worse than a marker that is missing, because the failure is
# silent and routes the reply to the wrong template.
_HINGLISH_MARKERS = frozenset(
    {
        "hai",
        "hain",
        "nahi",
        "nahin",
        "kya",
        "kar",
        "karo",
        "karke",
        "kiya",
        "ke",
        "ki",
        "ka",
        "ko",
        "se",
        "mein",
        "aur",
        "bhi",
        "yeh",
        "ye",
        "woh",
        "hum",
        "aap",
        "tum",
        "mera",
        "tera",
        "unka",
        "raha",
        "rahi",
        "rahe",
        "tha",
        "thi",
        "gaya",
        "gayi",
        "sab",
        "kuch",
        "bahut",
        "abhi",
        "phir",
        "lekin",
        "kyunki",
        "jab",
        "bhejo",
        "karein",
        "dekho",
        "suno",
    }
)

# Enough Latin words to make the ratio meaningful. Below this, a two-word fragment
# with one Hindi marker would read as confidently Hinglish.
_MIN_TOKENS_FOR_HINGLISH = 4
_HINGLISH_RATIO = 0.15

# Enough Devanagari to mean the author reads it, not an incidental stray character.
_DEVANAGARI_PRESENCE = 0.10

_WORD = re.compile(r"[a-z]+")


@dataclass(frozen=True, slots=True)
class Detection:
    """What was detected, how, and whether it is worth asking a model."""

    language: Language
    script: Script
    confident: bool
    method: str
    marker_ratio: float = 0.0

    @property
    def needs_model_fallback(self) -> bool:
        """Only when the deterministic path genuinely could not tell."""
        return not self.confident


def detect_script(text: str) -> tuple[Script, dict[Script, int]]:
    """Identify the dominant script and return the full distribution."""
    counts: dict[Script, int] = {}

    for character in text:
        code = ord(character)
        if not character.isalpha():
            continue
        for script, low, high in _SCRIPT_RANGES:
            if low <= code <= high:
                counts[script] = counts.get(script, 0) + 1
                break
        else:
            if code < 0x0250:
                counts[Script.LATIN] = counts.get(Script.LATIN, 0) + 1

    if not counts:
        return Script.UNKNOWN, counts

    dominant = max(counts, key=lambda script: counts[script])
    total = sum(counts.values())

    # A script needs a clear majority to be called dominant; otherwise the text is
    # genuinely mixed, which is common in Indian forwards that quote English
    # headlines inside Hindi commentary.
    if counts[dominant] / total < 0.6:
        return Script.MIXED, counts

    return dominant, counts


def hinglish_ratio(text: str) -> float:
    """Share of Latin tokens that are Hindi function words."""
    tokens = _WORD.findall(text.lower())
    if len(tokens) < _MIN_TOKENS_FOR_HINGLISH:
        return 0.0
    markers = sum(1 for token in tokens if token in _HINGLISH_MARKERS)
    return markers / len(tokens)


def detect(text: str) -> Detection:
    """Detect language deterministically. No model call, ever, from this function."""
    stripped = text.strip()

    if not stripped:
        return Detection(
            language=Language.UNKNOWN,
            script=Script.UNKNOWN,
            confident=True,
            method="empty",
        )

    script, counts = detect_script(stripped)

    if script is Script.DEVANAGARI:
        return Detection(
            language=Language.HINDI, script=script, confident=True, method="script_range"
        )

    if script in {Script.BENGALI, Script.TAMIL, Script.TELUGU, Script.ARABIC}:
        # Correctly identified and honestly out of scope: naming the script is more
        # useful than guessing a language we cannot evaluate.
        return Detection(
            language=Language.UNKNOWN, script=script, confident=True, method="script_out_of_scope"
        )

    # Devanagari presence decides before script dominance does. A sentence that is
    # mostly romanised but carries real Devanagari was written by someone who reads
    # Devanagari, and rendering the reply in Latin script would be the wrong call
    # even though the character count says Latin won.
    total_alpha = sum(counts.values())
    devanagari = counts.get(Script.DEVANAGARI, 0)
    if total_alpha and devanagari / total_alpha >= _DEVANAGARI_PRESENCE:
        return Detection(
            language=Language.HINDI, script=script, confident=True, method="devanagari_present"
        )

    if script is Script.LATIN:
        ratio = hinglish_ratio(stripped)
        if ratio >= _HINGLISH_RATIO:
            return Detection(
                language=Language.HINGLISH,
                script=script,
                confident=True,
                method="romanised_markers",
                marker_ratio=round(ratio, 4),
            )

        tokens = _WORD.findall(stripped.lower())
        if len(tokens) >= _MIN_TOKENS_FOR_HINGLISH:
            return Detection(
                language=Language.ENGLISH,
                script=script,
                confident=True,
                method="latin_default",
                marker_ratio=round(ratio, 4),
            )

        # Too short to judge. This is the one case worth a model call — and it is
        # rare enough that the budget survives it.
        return Detection(
            language=Language.ENGLISH,
            script=script,
            confident=False,
            method="too_short",
            marker_ratio=round(ratio, 4),
        )

    return Detection(
        language=Language.UNKNOWN, script=script, confident=False, method="undetermined"
    )
