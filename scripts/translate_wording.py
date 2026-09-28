"""Write app/verdict/wording.py: our fixed wording in the ten newer Indian languages.

The English (and hand-written Hindi) templates stay where they are; this translates
the English ones once with Google Translate and writes the results as a plain module,
so the service never translates its own wording at run time and every line can be
read and corrected by hand. Placeholders such as {who} are kept as they are; a
translation that loses or invents one is refused, and that key falls back to English.

    uv run --extra models python scripts/translate_wording.py

Machine translation: have a native speaker read each language before a public
release.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

import truststore

truststore.inject_into_ssl()

from app.extraction.translate import GoogleTranslator  # noqa: E402
from app.security.fetcher import SecureFetcher  # noqa: E402

LANGUAGES = ("bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa")

ENGLISH = {
    # app/verdict/explain.py
    # Worded for translation: "fact-checked ... found it" came back garbled in Tamil.
    "explain.factcheck": "{who} checked this claim and rated it false: “{quote}”",
    "explain.contradicts": "{who} reports otherwise: “{quote}”",
    "explain.supports": "{who} confirms it: “{quote}”",
    "explain.shared_certified": (
        "This link is a fact-check by {who}, a certified fact-checker. "
        "Its rating of this claim: “{rating}”."
    ),
    "explain.shared_listed": (
        "This link is a fact-check by {who}. Its rating of this claim: “{rating}”."
    ),
    # "Narrower" came back as "brief" or "condensed" in four languages.
    "explain.narrower": (
        "Only a smaller, partial version of this claim is reported. {who}: “{quote}”"
    ),
    "explain.media": "The picture is real but older: {who} published it on {date}.",
    "explain.others": "{n} other sources say the same.",
    "explain.other": "1 other source says the same.",
    # app/orchestration/pipeline.py
    "pipeline.unreported": (
        "We searched official sources and reliable news outlets and found nothing "
        "reporting this. Something this big would be widely reported if it were true, "
        "so treat it as likely false until an official source confirms it."
    ),
    # app/orchestration/correction.py
    "correction.opening": "Hi! I checked this before forwarding.",
    "correction.false": "Factify says it's false",
    "correction.partly": "Factify says it's only partly true",
    "correction.misleading": "Factify says it's misleading",
    "correction.true": "Factify says it's true",
    "correction.unconfirmed": (
        "Hi! I tried to check this before forwarding. Factify couldn't find reliable "
        "sources confirming it yet, so it may be best not to forward it for now."
    ),
}

# How a sentence ends in each script.
STOP = {
    "bn": "।",
    "mr": ".",
    "te": ".",
    "ta": ".",
    "gu": ".",
    "ur": "۔",
    "kn": ".",
    "or": "।",
    "ml": ".",
    "pa": "।",
}

_PLACEHOLDER = re.compile(r"\{[a-z]+\}")


def _tidy(language: str, text: str) -> str:
    """Google writes the danda of Odia, Bengali and Punjabi as "|"."""
    if STOP[language] != "।":
        return text
    text = re.sub(r"\s*\|\s*$", "।", text.strip())
    return re.sub(r"\s+\|\s+", "। ", text)


class _Governor:
    """The script's own calls are few; no daily budget to guard here."""

    async def acquire(self, _provider: str) -> object:
        return object()


def _translator() -> Any:
    """Google, and the configured model when Google refuses - as the service does."""
    from app.config import Settings
    from app.extraction.model_wire import WireFormat
    from app.extraction.translate import FallbackTranslator, ModelTranslator

    settings = Settings()
    model = (
        ModelTranslator(
            fetcher=SecureFetcher(timeout_seconds=30.0),
            governor=_Governor(),
            endpoint=settings.llm.endpoint,
            api_key=settings.llm.api_key.get_secret_value(),
            model_id=settings.models.extraction,
            api_format=WireFormat(settings.llm.api_format),
        )
        if settings.llm.enabled and settings.llm.api_key
        else None
    )
    google = GoogleTranslator(fetcher=SecureFetcher(timeout_seconds=15.0), per_minute=200)
    return FallbackTranslator(google, model)


async def main() -> None:
    from app.verdict.wording import WORDING

    translator = _translator()
    only = next((arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--only=")), "")
    # Kept, not replaced, when a translation fails: a rate-limited run once wrote a
    # file with 65 lines missing.
    wording: dict[str, dict[str, str]] = {lang: dict(WORDING.get(lang, {})) for lang in LANGUAGES}
    refused = 0
    for language in LANGUAGES:
        for key, english in ENGLISH.items():
            if only and not key.startswith(only):
                continue
            # Placeholders are sent three ways until one comes back whole: as they are,
            # as single letters, as numbered markers. {who} was itself translated into
            # Kannada, Odia and Malayalam; a letter was taken as a word in Bengali.
            # The product's name is kept in Latin letters, as a placeholder; it was
            # transliterated into Kannada, Odia and Malayalam script otherwise.
            english = english.replace("Factify", "{brand}")
            names = list(dict.fromkeys(_PLACEHOLDER.findall(english)))
            text = ""
            for style in ("{name}", "{letter}", "__{number}__"):
                marks = {
                    name: style.format(name=name[1:-1], letter=chr(65 + i), number=i + 1)
                    if style != "{name}"
                    else name
                    for i, name in enumerate(names)
                }
                marks = {
                    name: (f"{{{mark}}}" if style == "{letter}" else mark)
                    for name, mark in marks.items()
                }
                sent = english
                for name, mark in marks.items():
                    sent = sent.replace(name, mark)
                result = await translator.translate(sent, target=language, source="en")
                text = result.text if result else ""
                for name, mark in marks.items():
                    text = text.replace(mark, name)
                if text and set(_PLACEHOLDER.findall(text)) == set(names):
                    break
            if not text or set(_PLACEHOLDER.findall(text)) != set(names):
                refused += 1
                print(f"refused {language} {key}: {text!r}", file=sys.stderr)
                continue
            wording[language][key] = text.replace('"{quote}"', "“{quote}”").replace(
                "{brand}", "Factify"
            )
        wording[language]["correction.stop"] = STOP[language]
        wording[language] = {k: _tidy(language, v) for k, v in wording[language].items()}
        await asyncio.sleep(0.5)

    lines = [
        "# ruff: noqa: E501  (generated data: one translated line per entry)",
        '"""Our fixed wording in the ten newer Indian languages (generated).',
        "",
        "Machine-translated from the English templates by scripts/translate_wording.py",
        "(Google Translate, 2026-09-28). Placeholders were checked; the words were not",
        "reviewed by native speakers yet. A missing key falls back to English. Edit by",
        "hand freely - regenerating overwrites this file.",
        '"""',
        "",
        "WORDING: dict[str, dict[str, str]] = {",
    ]
    for language, entries in wording.items():
        lines.append(f"    {language!r}: {{")
        for key, text in entries.items():
            lines.append(f"        {key!r}: {text!r},")
        lines.append("    },")
    lines.append("}")
    await asyncio.to_thread(_write, lines)
    print(f"wrote {TARGET} ({refused} refused)")


TARGET = Path(__file__).resolve().parent.parent / "app" / "verdict" / "wording.py"


def _write(lines: list[str]) -> None:
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def review() -> None:
    """Translate every line back into English and flag the ones whose meaning moved.

    No native speaker has read these yet; this is the check a machine can do. A line
    whose back-translation drifts from the English it came from is printed for a
    person to look at, with its similarity (multilingual MiniLM, 0-1).
    """
    from app.embeddings.text import TextEmbedder
    from app.verdict.wording import WORDING

    translator = _translator()
    embedder = TextEmbedder()
    flagged = 0
    for language, lines in WORDING.items():
        for key, text in lines.items():
            if key not in ENGLISH:
                continue
            back = await translator.translate(text, target="en", source=language)
            if back is None:
                continue
            english = ENGLISH[key]
            vectors = embedder.embed([english, back.text], language="en").vectors
            if len(vectors) != 2:
                continue
            # Cosine: the embeddings are not unit length.
            dot = sum(a * b for a, b in zip(vectors[0], vectors[1], strict=True))
            norms = (sum(a * a for a in vectors[0]) * sum(b * b for b in vectors[1])) ** 0.5
            similarity = dot / norms if norms else 0.0
            if similarity < REVIEW_BELOW:
                flagged += 1
                print(f"{language} {key} {similarity:.2f}")
                print(f"  en:   {english}")
                print(f"  back: {back.text}")
    print(f"{flagged} lines flagged below {REVIEW_BELOW}")


REVIEW_BELOW = 0.8


if __name__ == "__main__":
    asyncio.run(review() if "--review" in sys.argv else main())
