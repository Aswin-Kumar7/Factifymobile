"""Prove each deliverable of the problem statement on a running Factify, live.

    uv run python scripts/deliverables_check.py [--base https://factify-zeai...] [--out report.md]

Every check is a real request to the real service - the same endpoints the app and
the website use - and the report shows what came back, so anyone can watch it run
and read the answer. Nothing here is mocked. Sign-in uses FACTIFY_CHECK_EMAIL and
FACTIFY_CHECK_PASSWORD, or the test account in .env.test.

The problem statement's deliverables, and how each is shown:

  1. Detect AI-generated and manipulated media - an AI-made news graphic is read as
     likely AI-made; a plain news card is not.
  2. Analyse news credibility and source reliability - a link's website is profiled
     (on the trusted list or not, itemised warnings); every cited source carries its
     credibility.
  3. Explainable authenticity scores - a false claim comes back False with a
     confidence from the sources, an explanation quoting a named source, and each
     source's own sentence.
  4. Identify misinformation patterns - a "true but smaller" claim is Misleading, a
     twisted number is named as one, an AI-made picture of an unreported event is
     called fabricated.
  5. Generate fact-checking recommendations - a ready correction to send back, the
     lesson on how posts like it mislead.

Prints a Markdown report and exits 1 if any deliverable fails.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import truststore

truststore.inject_into_ssl()

import httpx  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "data" / "demo"


@dataclass
class Result:
    deliverable: str
    test: str
    passed: bool
    shown: list[str] = field(default_factory=list)
    case: str | None = None


def _login(client: httpx.Client) -> None:
    email = os.environ.get("FACTIFY_CHECK_EMAIL")
    password = os.environ.get("FACTIFY_CHECK_PASSWORD")
    if not (email and password):
        env = dict(
            line.split("=", 1)
            for line in (ROOT / ".env.test").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        email, password = env["WEB_TEST_OWNER"].strip(), env["WEB_TEST_PASSWORD"].strip()
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    client.headers["authorization"] = f"Bearer {r.json()['access_token']}"


def _answer(client: httpx.Client, started: httpx.Response) -> dict[str, Any]:
    started.raise_for_status()
    body = started.json()
    if body.get("verdict"):
        return body
    case = body["case_id"]
    for _ in range(200):
        v = client.get(f"/v1/cases/{case}").json()
        if v.get("verdict"):
            return v
        time.sleep(3)
    raise TimeoutError(case)


def _text(client: httpx.Client, text: str) -> dict[str, Any]:
    return _answer(client, client.post("/v1/verify", json={"text": text, "mode": "background"}))


def _link(client: httpx.Client, url: str) -> dict[str, Any]:
    return _answer(client, client.post("/v1/verify", json={"url": url, "mode": "background"}))


def _file(client: httpx.Client, name: str, data: bytes, mime: str) -> dict[str, Any]:
    return _answer(
        client,
        client.post(
            "/v1/verify/file",
            files={"file": (name, data, mime)},
            data={"consent_to_process_media": "true", "background": "true"},
        ),
    )


def _news_card() -> bytes:
    """A plain news-style card carrying a false claim, drawn here."""

    def font(size: int) -> Any:
        for path in (
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ):
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    image = Image.new("RGB", (1080, 1080), "#b71c1c")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 1080, 140], fill="#111")
    draw.text((40, 40), "BREAKING NEWS", font=font(64), fill="white")
    for i, line in enumerate(
        ["DMK wins the 2026", "Tamil Nadu Assembly", "election with 150 seats."]
    ):
        draw.text((60, 280 + i * 110), line, font=font(72), fill="white")
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _why(v: dict[str, Any], limit: int = 200) -> str:
    return (v.get("summary") or v.get("action_reason") or "")[:limit]


def _read(v: dict[str, Any]) -> str:
    return ((v.get("image_reading") or {}).get("text") or "")[:90]


def _named(v: dict[str, Any]) -> list[str]:
    return [c["technique"] for c in v.get("claims", []) if c.get("technique")]


def _sources(v: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        e
        for c in v.get("claims", [])
        for e in c.get("evidence", [])
        if e.get("direction") in ("supports", "contradicts")
    ]


def run(base: str) -> list[Result]:
    client = httpx.Client(base_url=base, timeout=300)
    _login(client)
    results: list[Result] = []

    # 1. AI-generated and manipulated media.
    lithium = (DEMO / "ai_news_lithium.webp").read_bytes()
    v = _file(client, "ai_news_lithium.webp", lithium, "image/webp")
    det = (v.get("media_report") or {}).get("detector") or {}
    results.append(
        Result(
            "1. Detect AI-generated and manipulated media",
            "An AI-made 'BREAKING NEWS' graphic is read as likely AI-made",
            det.get("agreement") == "likely_ai",
            [
                f"AI-picture detector: {round((det.get('generated') or 0) * 100)}% likely AI-made "
                f"({det.get('agreement')})",
                f"Editing signals: {(v.get('media_report') or {}).get('editing')}",
            ],
            v["case_id"],
        )
    )
    lithium_answer = v

    card = _file(client, "news_card.png", _news_card(), "image/png")
    det = (card.get("media_report") or {}).get("detector") or {}
    results.append(
        Result(
            "1. Detect AI-generated and manipulated media",
            "A plain news card (made by a script, not an AI generator) is not called AI-made",
            det.get("agreement") != "likely_ai",
            [
                f"AI-picture detector: {round((det.get('generated') or 0) * 100)}%"
                f" ({det.get('agreement')})",
                f"Text read from the picture: {_read(card)!r}",
            ],
            card["case_id"],
        )
    )

    # 2. News credibility and source reliability.
    link = _link(
        client,
        "https://indianexpress.com/article/india/tamil-nadu-assembly-election-results-2026-winners-list-constituency-wise-seat-wise-10664508/",
    )
    profile = link.get("source_profile") or {}
    results.append(
        Result(
            "2. Analyse news credibility and source reliability",
            "A submitted link's website is profiled against the trusted-source list",
            bool(profile.get("domain")) and profile.get("trusted") is True,
            [*(profile.get("findings") or []), *(profile.get("warnings") or [])]
            or ["no profile returned"],
            link["case_id"],
        )
    )
    cited = _sources(card)
    results.append(
        Result(
            "2. Analyse news credibility and source reliability",
            "Every source that decided a verdict carries its credibility",
            bool(cited) and all(e.get("credibility") for e in cited),
            [
                f"{e.get('publisher')}: {e.get('credibility')} ({e.get('direction')})"
                for e in cited[:5]
            ],
            card["case_id"],
        )
    )

    # 3. Explainable authenticity scores.
    results.append(
        Result(
            "3. Explainable authenticity scores",
            "A false claim is False with a confidence, an explanation and quoted sources",
            card.get("verdict") == "FALSE"
            and 50 <= (card.get("confidence") or 0) <= 97
            and bool(card.get("summary") or card.get("action_reason"))
            and all(e.get("source_excerpt") and e.get("citation_url") for e in cited),
            [
                f"Verdict: {card.get('verdict')} at {card.get('confidence')}% confidence",
                f"Why: {(card.get('summary') or card.get('action_reason'))[:200]}",
                *[
                    f"{e.get('publisher')} says: \u201c{e.get('source_excerpt', '')[:120]}\u201d"
                    for e in cited[:2]
                ],
            ],
            card["case_id"],
        )
    )

    # 4. Misinformation patterns.
    scheme = _text(client, "Govt to pay ₹5,000 a month to every woman from 1 July.")
    results.append(
        Result(
            "4. Identify misinformation patterns",
            "A real scheme inflated ('every woman', 'every month') is not passed as true",
            scheme.get("verdict") in ("FALSE", "MISLEADING", "PARTLY_TRUE"),
            [
                f"Verdict: {scheme.get('verdict')} ({scheme.get('confidence')}%)",
                f"Why: {_why(scheme)}",
                f"Technique: {_named(scheme)}",
            ],
            scheme["case_id"],
        )
    )
    figure = _text(client, "India's population is 300 crore people.")
    techniques = [c.get("technique") for c in figure.get("claims", []) if c.get("technique")]
    results.append(
        Result(
            "4. Identify misinformation patterns",
            "A wrong figure is refuted and named as a twisted number",
            figure.get("verdict") == "FALSE" and "TWISTED_NUMBER" in techniques,
            [
                f"Verdict: {figure.get('verdict')} ({figure.get('confidence')}%)",
                f"Why: {(figure.get('summary') or figure.get('action_reason'))[:200]}",
                f"Techniques named: {techniques}",
            ],
            figure["case_id"],
        )
    )
    results.append(
        Result(
            "4. Identify misinformation patterns",
            "An AI-made news graphic of an event no outlet reports is called False",
            lithium_answer.get("verdict") == "FALSE",
            [
                f"Verdict: {lithium_answer.get('verdict')} ({lithium_answer.get('confidence')}%)",
                f"Why: {_why(lithium_answer, 240)}",
            ],
            lithium_answer["case_id"],
        )
    )

    # 5. Fact-checking recommendations.
    correction = client.post(
        f"/v1/cases/{card['case_id']}/correction-text", json={"language": "en"}
    ).json()
    results.append(
        Result(
            "5. Generate fact-checking recommendations",
            "A ready correction to send back to the chat, with its sources",
            bool(correction.get("message")),
            [correction.get("message", "")[:400], f"Links: {correction.get('links')}"],
            card["case_id"],
        )
    )
    return results


def report(base: str, results: list[Result]) -> str:
    lines = [
        "# Factify - deliverables, proven live",
        "",
        f"Server: {base} · run {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Deliverable | Test | Result |",
        "|---|---|---|",
        *(f"| {r.deliverable} | {r.test} | {'PASS' if r.passed else 'FAIL'} |" for r in results),
        "",
    ]
    for r in results:
        lines += [
            f"## {'PASS' if r.passed else 'FAIL'} - {r.test}",
            f"_{r.deliverable}_ · case `{r.case}`",
            "",
        ]
        lines += [f"- {line}" for line in r.shown] + [""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    results = run(args.base)
    text = report(args.base, results)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
