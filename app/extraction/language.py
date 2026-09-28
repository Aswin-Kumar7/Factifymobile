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
    """Scope is what we can evaluate. Anything else is named and abstained on.

    English, Hindi and ten more Indian languages (2026-09-28): a claim in any of them
    is checked in its own words and, translated, in English - where most fact-checks
    and national reporting are published - and its explanation is written back in it.
    """

    ENGLISH = "en"
    HINDI = "hi"
    HINGLISH = "hi-Latn"
    BENGALI = "bn"
    MARATHI = "mr"
    TELUGU = "te"
    TAMIL = "ta"
    GUJARATI = "gu"
    URDU = "ur"
    KANNADA = "kn"
    ODIA = "or"
    MALAYALAM = "ml"
    PUNJABI = "pa"
    UNKNOWN = "und"


# The languages a claim can be checked in, as their ISO 639-1 codes.
CHECKED = frozenset(
    language.value for language in Language if language not in (Language.HINGLISH, Language.UNKNOWN)
)


class Script(StrEnum):
    LATIN = "Latn"
    DEVANAGARI = "Deva"
    BENGALI = "Beng"
    TAMIL = "Taml"
    TELUGU = "Telu"
    ARABIC = "Arab"
    GUJARATI = "Gujr"
    GURMUKHI = "Guru"
    ODIA = "Orya"
    KANNADA = "Knda"
    MALAYALAM = "Mlym"
    MIXED = "Zyyy"
    UNKNOWN = "Zzzz"


_SCRIPT_RANGES: tuple[tuple[Script, int, int], ...] = (
    (Script.DEVANAGARI, 0x0900, 0x097F),
    (Script.BENGALI, 0x0980, 0x09FF),
    (Script.GURMUKHI, 0x0A00, 0x0A7F),
    (Script.GUJARATI, 0x0A80, 0x0AFF),
    (Script.ODIA, 0x0B00, 0x0B7F),
    (Script.TAMIL, 0x0B80, 0x0BFF),
    (Script.TELUGU, 0x0C00, 0x0C7F),
    (Script.KANNADA, 0x0C80, 0x0CFF),
    (Script.MALAYALAM, 0x0D00, 0x0D7F),
    (Script.ARABIC, 0x0600, 0x06FF),
    (Script.ARABIC, 0x0750, 0x077F),
)

# One language per script, as Indian forwards use them. Bengali script also writes
# Assamese, and Arabic script Kashmiri and Sindhi; the larger language is named, and
# the check itself does not depend on the guess - it searches in the claim's own
# words as well as in English.
_SCRIPT_LANGUAGE = {
    Script.BENGALI: "bn",
    Script.GURMUKHI: "pa",
    Script.GUJARATI: "gu",
    Script.ODIA: "or",
    Script.TAMIL: "ta",
    Script.TELUGU: "te",
    Script.KANNADA: "kn",
    Script.MALAYALAM: "ml",
    Script.ARABIC: "ur",
}

# Hindi and Marathi share Devanagari, so their commonest grammar words tell them
# apart: "आहे", "नाही", "आणि" are Marathi, "है", "नहीं", "और" Hindi. Words both
# languages use ("ने", "ही", "हे") are left out.
_MARATHI_WORDS = frozenset(
    "आहे आहेत नाही नाहीत आणि होते होता होती केले केली करण्यात येणार असे आता मध्ये "
    "पण तर त्यांनी त्याने झाले झाली दिले मिळणार सर्व करा".split()
)
_HINDI_WORDS = frozenset(
    "है हैं नहीं और का की के में से को था थी थे गया गई किया रहा रही लिए भी यह वह कहा करें होगा मिलेगा".split()
)
_DEVANAGARI_WORD = re.compile(r"[\u0900-\u097F]+")


def devanagari_language(text: str) -> Language:
    """Hindi or Marathi, from grammar words; Hindi when it cannot tell."""
    words = _DEVANAGARI_WORD.findall(text)
    marathi = sum(1 for word in words if word in _MARATHI_WORDS)
    hindi = sum(1 for word in words if word in _HINDI_WORDS)
    return Language.MARATHI if marathi >= 2 and marathi > hindi else Language.HINDI


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
            language=devanagari_language(stripped),
            script=script,
            confident=True,
            method="script_range",
        )

    if script in _SCRIPT_LANGUAGE:
        return Detection(
            language=Language(_SCRIPT_LANGUAGE[script]),
            script=script,
            confident=True,
            method="script_range",
        )

    # Devanagari presence decides before script dominance does. A sentence that is
    # mostly romanised but carries real Devanagari was written by someone who reads
    # Devanagari, and rendering the reply in Latin script would be the wrong call
    # even though the character count says Latin won.
    total_alpha = sum(counts.values())
    devanagari = counts.get(Script.DEVANAGARI, 0)
    if total_alpha and devanagari / total_alpha >= _DEVANAGARI_PRESENCE:
        return Detection(
            language=devanagari_language(stripped),
            script=script,
            confident=True,
            method="devanagari_present",
        )

    # The same for the other Indian scripts: an English headline quoted inside a
    # Tamil forward is a Tamil forward.
    indian = {k: v for k, v in counts.items() if k in _SCRIPT_LANGUAGE}
    if total_alpha and indian:
        leading = max(indian, key=lambda k: indian[k])
        if indian[leading] / total_alpha >= _DEVANAGARI_PRESENCE:
            return Detection(
                language=Language(_SCRIPT_LANGUAGE[leading]),
                script=script,
                confident=True,
                method="script_present",
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
