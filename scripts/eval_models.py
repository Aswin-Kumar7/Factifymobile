"""Measure our own detectors on labelled pictures before trusting their thresholds.

Every picture is scored as it is, after one WhatsApp-style send (long side 1600 px,
JPEG quality 70) and after a forward of a forward (1280 px, quality 60, twice) -
the three states a picture reaches us in. For each state it reports how many AI
pictures were caught and how many real photographs were wrongly flagged, at the
model's own boundary and at the boundary that flags at most 5% of real photographs.

    uv run --extra models python scripts/eval_models.py pictures .cache/eval/mllm

The folder holds one subfolder per class: `real` and any number of `*-fake` ones.
Nothing here is committed data: the pictures stay under `.cache/`.
"""

from __future__ import annotations

import io
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from app.media.detectors.common import rgb

logging.disable(logging.CRITICAL)

MODELS = ".cache/models"


def whatsapp(data: bytes, *, side: int = 1600, quality: int = 70, times: int = 1) -> bytes:
    for _ in range(times):
        picture = rgb(data)
        picture.thumbnail((side, side), Image.Resampling.BILINEAR)
        out = io.BytesIO()
        picture.save(out, "JPEG", quality=quality)
        data = out.getvalue()
    return data


STATES: dict[str, Callable[[bytes], bytes]] = {
    "as sent": lambda d: d,
    "whatsapp": lambda d: whatsapp(d),
    "forwarded": lambda d: whatsapp(d, side=1280, quality=60, times=2),
}


def _report(name: str, scores: dict[str, list[float]], boundary: float) -> None:
    real = sorted(scores.get("real", []))
    fakes = {k: v for k, v in scores.items() if k != "real"}
    at5 = real[int(len(real) * 0.95)] if real else boundary
    flagged = sum(s >= boundary for s in real)
    print(f"  {name}: real photos flagged {flagged}/{len(real)} at {boundary:.2f}", end="")
    print(f" | 5%-boundary {at5:.2f}")
    for label, values in sorted(fakes.items()):
        caught = sum(s >= boundary for s in values)
        caught5 = sum(s > at5 for s in values)
        mean = sum(values) / len(values)
        print(
            f"    {label:22s} caught {caught:3d}/{len(values)} at {boundary:.2f}"
            f"  | {caught5:3d}/{len(values)} at the 5% boundary  (mean {mean:.2f})"
        )


def pictures(folder: str) -> None:
    """Each picture model alone, and the two together as the app shows them: "likely
    AI-made" only when both are raised, "unclear" when one is."""
    from app.media.detectors.dda import DdaDetector
    from app.media.detectors.picture import AiPictureDetector

    main = AiPictureDetector(directory=MODELS, threads=4)
    second = DdaDetector(directory=MODELS, threads=4)
    main.load()
    files = {
        sub.name: sorted(
            p for p in sub.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )
        for sub in Path(folder).iterdir()
        if sub.is_dir()
    }
    for state, change in STATES.items():
        scores: dict[str, list[float]] = {}
        seconds: dict[str, list[float]] = {}
        both: dict[str, dict[str, int]] = {}
        boundary = 0.65
        started = time.perf_counter()
        count = 0
        for label, paths in files.items():
            tally = both.setdefault(label, {"likely_ai": 0, "unclear": 0, "no_sign": 0})
            for path in paths:
                data = change(path.read_bytes())
                result = main.score(data)
                if result is None:
                    continue
                boundary = result.threshold
                scores.setdefault(label, []).append(result.likelihood)
                other = second.score(data) if second.available else None
                votes = [result.raised]
                if other is not None:
                    seconds.setdefault(label, []).append(other.likelihood)
                    votes.append(other.raised)
                tally["likely_ai" if all(votes) else "unclear" if any(votes) else "no_sign"] += 1
                count += 1
        elapsed = (time.perf_counter() - started) / max(1, count) * 1000
        print(f"\n[{state}] {count} pictures, {elapsed:.0f} ms each")
        _report("Community Forensics frontier", scores, boundary)
        if seconds:
            _report("DDA", seconds, 0.5)
            print("  together (what the app shows):")
            for label, tally in sorted(both.items()):
                print(f"    {label:22s} {tally}")


def stance(pairs_file: str) -> None:
    """Relevance and support against the hosted reader's past labels.

    Pairs come from past checks: a claim and the sentence the hosted reader cited,
    labelled supports / contradicts / contextualizes, plus sentences paired with an
    unrelated claim. Reports where the relevance floor must sit to keep 99% of cited
    sentences, how many unrelated ones it would skip, and how often plain English
    "support" by the local model agrees with the hosted reader's label.
    """
    import json

    from app.sources.local_reading import _REPORTED
    from app.sources.stance import LocalStance, is_english

    rows = [json.loads(line) for line in Path(pairs_file).read_text(encoding="utf-8").splitlines()]
    model = LocalStance(directory=MODELS, threads=8)
    model.load()
    started = time.perf_counter()
    relevance: dict[str, list[float]] = {}
    for row in rows:
        [score] = model.relevance(row["claim"], [row["text"]]) or [0.0]
        row["relevance"] = score
        relevance.setdefault(row["label"], []).append(score)
    per_pair = (time.perf_counter() - started) / len(rows) * 1000
    print(f"relevance: {len(rows)} pairs, {per_pair:.0f} ms each")
    cited = sorted(s for label, v in relevance.items() if label != "unrelated" for s in v)
    for share in (0.005, 0.01, 0.02, 0.05):
        floor = cited[int(len(cited) * share)]
        skipped = sum(s < floor for s in relevance.get("unrelated", []))
        print(
            f"  floor {floor:.4f} keeps {1 - share:.1%} of cited sentences; "
            f"skips {skipped}/{len(relevance.get('unrelated', []))} unrelated"
        )
    for label, values in sorted(relevance.items()):
        values = sorted(values)
        print(f"  {label:15s} n={len(values):4d} median {values[len(values) // 2]:.3f}")

    english = [
        r
        for r in rows
        if r["label"] != "unrelated"
        and is_english(r["claim"])
        and is_english(r["text"])
        and not _REPORTED.search(r["text"])
    ]
    started = time.perf_counter()
    for row in english:
        [reading] = model.entailment([row["text"]], row["claim"]) or [None]
        row["entails"] = reading.entails if reading else 0.0
        row["contradicts"] = reading.contradicts if reading else 0.0
    per_pair = (time.perf_counter() - started) / max(1, len(english)) * 1000
    print(f"\nsupport (English, own voice): {len(english)} pairs, {per_pair:.0f} ms each")
    for boundary in (0.9, 0.95, 0.97, 0.98, 0.99):
        chosen = [r for r in english if r["entails"] >= boundary and r["contradicts"] <= 0.02]
        agree = sum(r["label"] == "supports" for r in chosen)
        total_support = sum(r["label"] == "supports" for r in english)
        wrong = {
            label: sum(r["label"] == label for r in chosen)
            for label in ("contradicts", "contextualizes", "narrower")
        }
        print(
            f"  entails >= {boundary:.2f}: {len(chosen):4d} taken locally, {agree} agree "
            f"({agree / max(1, len(chosen)):.1%}); covers {agree}/{total_support} supports; "
            f"disagreements {wrong}"
        )
    contradicting = [r for r in english if r["label"] == "contradicts"]
    caught = sum(r["contradicts"] >= 0.5 for r in contradicting)
    print(f"  contradictions the local model also sees (>= 0.5): {caught}/{len(contradicting)}")


if __name__ == "__main__":
    task, target = sys.argv[1], sys.argv[2]
    {"pictures": pictures, "stance": stance}[task](target)
