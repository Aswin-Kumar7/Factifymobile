"""A mixed true/false accuracy run against a live Facify.

    uv run python scripts/accuracy_suite.py

Each case is submitted exactly as a person would submit it — the raw sentence, or
the bare link, and nothing else. No hints, no expected answer, no topic, no
steering. Whatever the service knows it has to find for itself.

**The cases are dated.** They were assembled on 2026-09-23 from material published
in the days before, half of it true and half of it debunked by a named authority,
so that "did it find the evidence" is a question with a checkable answer today. News
ages; re-check the ground truth before trusting a later run.

Scoring follows the project's own audit rule rather than a single accuracy number,
because the two ways of being wrong are not equally bad:

  - a true claim blocked is a **false positive** — the worst outcome this system has
  - a false claim cleared is a **false negative**
  - anything routed to review is a **miss**: honest, unhelpful, and not an error

A verdict is only counted correct when the evidence is there to support it, so a
lucky guess with no citations does not pass.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field

import truststore

truststore.inject_into_ssl()

import httpx  # noqa: E402

BASE = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class Case:
    ref: str
    kind: str  # "text" | "url"
    payload: str
    truth: str  # "TRUE" | "FALSE"
    note: str  # where the ground truth comes from
    thin: bool = False  # true claim whose coverage may be genuinely thin


CASES: tuple[Case, ...] = (
    Case(
        ref="T1",
        kind="text",
        payload=(
            "India defeated Sri Lanka by 147 runs to win the women's cricket gold "
            "medal at the 2026 Asian Games in Japan on 22 September 2026."
        ),
        truth="TRUE",
        note="Final at Korogi Sports Park, Nisshin; covered by Olympics.com, ANI, The Tribune",
    ),
    Case(
        ref="F1",
        kind="text",
        payload=(
            "A massive fire broke out at an India-Israel joint defence facility in "
            "Delhi, killing several workers from both countries."
        ),
        truth="FALSE",
        note="Debunked by the MEA Fact Check Unit, 12 March 2026",
    ),
    Case(
        ref="F2",
        kind="text",
        payload=(
            "Banks have been asked to stock up ATMs ahead of the UPI fee rollout on "
            "15 October."
        ),
        truth="FALSE",
        note="Debunked by PIB Fact Check, 23 September 2026 — neither RBI nor MoF issued it",
    ),
    Case(
        ref="T2",
        kind="url",
        payload=(
            "https://www.olympics.com/en/news/"
            "asian-games-2026-live-scores-updates-results-india-september-22"
        ),
        truth="TRUE",
        note="Olympics.com live report of the same gold medal",
    ),
    Case(
        ref="F3",
        kind="text",
        payload=(
            "Chinese President Xi Jinping fainted during the BRICS Summit in New Delhi "
            "and suffered a stroke."
        ),
        truth="FALSE",
        note="Flagged false by the MEA Fact Check Unit, September 2026",
    ),
    Case(
        ref="T3",
        kind="text",
        payload=(
            "IIT Madras inaugurated a robotics laboratory costing 3.30 crore rupees in "
            "September 2026."
        ),
        truth="TRUE",
        note="Reported 22 September 2026; regional coverage, so corroboration may be thin",
        thin=True,
    ),
    Case(
        ref="T4",
        kind="url",
        payload=(
            "https://www.newsonair.gov.in/"
            "government-debunks-false-claims-of-massive-fire-in-india-israel-joint-"
            "defense-facility-in-delhi"
        ),
        truth="TRUE",
        note=(
            "A government debunk. States the false claim in order to refute it — the "
            "page must not be read as asserting it"
        ),
    ),
)


@dataclass
class Result:
    case: Case
    action: str = ""
    seconds: float = 0.0
    claims: int = 0
    citations: int = 0
    statuses: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    error: str = ""


def _grade(result: Result) -> str:
    """correct | miss | FALSE POSITIVE | FALSE NEGATIVE | error."""
    if result.error:
        return "error"

    action = result.action
    if result.case.truth == "TRUE":
        if action == "SAFE_TO_SHARE":
            # A clearance nobody can check is not a clearance.
            return "correct" if result.citations else "miss"
        if action in ("DO_NOT_SHARE", "SHARE_WITH_CORRECTION"):
            return "FALSE POSITIVE"
        return "miss"

    if action in ("DO_NOT_SHARE", "SHARE_WITH_CORRECTION"):
        return "correct" if result.citations else "miss"
    if action == "SAFE_TO_SHARE":
        return "FALSE NEGATIVE"
    return "miss"


async def _run(client: httpx.AsyncClient, case: Case) -> Result:
    result = Result(case=case)
    body = {case.kind: case.payload, "language": "en"}

    started = asyncio.get_running_loop().time()
    try:
        response = await client.post(f"{BASE}/v1/verify", json=body, timeout=300)
        result.seconds = asyncio.get_running_loop().time() - started
        if response.status_code != 200:
            result.error = f"HTTP {response.status_code}"
            return result

        data = response.json()
        result.action = data.get("action", "")
        claims = data.get("claims", ())
        result.claims = len(claims)
        for claim in claims:
            result.statuses.append(claim.get("status", "?"))
            for item in claim.get("evidence", ()):
                result.citations += 1
                publisher = item.get("publisher") or "?"
                if publisher not in result.publishers:
                    result.publishers.append(publisher)
    except Exception as error:  # a harness must report a failure, not raise through it
        result.seconds = asyncio.get_running_loop().time() - started
        result.error = f"{type(error).__name__}: {error}"

    return result


async def main() -> int:
    async with httpx.AsyncClient() as client:
        try:
            ready = await client.get(f"{BASE}/readyz", timeout=20)
        except Exception as error:
            print(f"no Facify at {BASE}: {error}")
            return 2
        if ready.status_code != 200 or not ready.json().get("ready"):
            print(f"Facify at {BASE} is not ready: {ready.text}")
            return 2

        results: list[Result] = []
        for case in CASES:
            print(f"  running {case.ref} ({case.kind}) ...", flush=True)
            results.append(await _run(client, case))

    print()
    print(f"{'ref':<4} {'truth':<6} {'verdict':<22} {'grade':<15} {'s':>5} {'cites':>6}  sources")
    print("-" * 104)
    for result in results:
        grade = _grade(result)
        sources = ", ".join(result.publishers[:3]) or ("— " + result.error if result.error else "—")
        print(
            f"{result.case.ref:<4} {result.case.truth:<6} "
            f"{(result.action or 'ERROR'):<22} {grade:<15} "
            f"{result.seconds:5.1f} {result.citations:6}  {sources[:44]}"
        )

    grades = [_grade(r) for r in results]
    correct = grades.count("correct")
    print()
    print(f"correct          {correct}/{len(results)}")
    print(f"missed (review)  {grades.count('miss')}")
    print(f"FALSE POSITIVES  {grades.count('FALSE POSITIVE')}   (a true claim blocked)")
    print(f"FALSE NEGATIVES  {grades.count('FALSE NEGATIVE')}   (a false claim cleared)")
    if grades.count("error"):
        print(f"errors           {grades.count('error')}")

    print()
    for result, grade in zip(results, grades, strict=True):
        if grade != "correct":
            flag = " [thin coverage expected]" if result.case.thin else ""
            print(f"  {result.case.ref} {grade}{flag}: {result.case.note}")
            print(f"       claim statuses: {', '.join(result.statuses) or 'none'}")

    return 0 if not (grades.count("FALSE POSITIVE") or grades.count("FALSE NEGATIVE")) else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(main()))
