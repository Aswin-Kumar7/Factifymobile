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

import truststore

truststore.inject_into_ssl()

from app.extraction.translate import GoogleTranslator  # noqa: E402
from app.security.fetcher import SecureFetcher  # noqa: E402

LANGUAGES = ("bn", "mr", "te", "ta", "gu", "ur", "kn", "or", "ml", "pa")

ENGLISH = {
    # app/verdict/explain.py
    "explain.factcheck": "{who} has fact-checked this and found it false: “{quote}”",
    "explain.contradicts": "{who} reports otherwise: “{quote}”",
    "explain.supports": "{who} confirms it: “{quote}”",
    "explain.narrower": "Only a narrower version of this is reported. {who}: “{quote}”",
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


async def main() -> None:
    translator = GoogleTranslator(fetcher=SecureFetcher(timeout_seconds=15.0), per_minute=200)
    wording: dict[str, dict[str, str]] = {}
    refused = 0
    for language in LANGUAGES:
        wording[language] = {}
        for key, english in ENGLISH.items():
            # Placeholders are sent three ways until one comes back whole: as they are,
            # as single letters, as numbered markers. {who} was itself translated into
            # Kannada, Odia and Malayalam; a letter was taken as a word in Bengali.
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
            wording[language][key] = text.replace('"{quote}"', "“{quote}”")
        wording[language]["correction.stop"] = STOP[language]
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


if __name__ == "__main__":
    asyncio.run(main())
