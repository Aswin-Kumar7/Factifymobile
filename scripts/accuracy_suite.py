"""A mixed true/false accuracy run against a live Factify.

    uv run python scripts/accuracy_suite.py [one|two]

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


# ---------------------------------------------------------------- suite one
#
# Assembled 2026-09-23. The service has since been fixed against these, so they
# measure regression rather than accuracy: once a case has been debugged it can
# only tell you the fix still holds.
SUITE_ONE: tuple[Case, ...] = (
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


# ---------------------------------------------------------------- suite two
#
# Assembled 2026-09-23 as well, and deliberately **not** looked at while anything
# was being fixed. Different subjects from suite one — a satellite launch, two
# government-scheme scams, a geopolitical report, a health myth, an encyclopedia
# page and an official release — so that nothing here shares a debugged path.
#
# This is the one that measures accuracy. Suite one no longer can.
SUITE_TWO: tuple[Case, ...] = (
    Case(
        ref="S1",
        kind="text",
        payload=(
            "ISRO launched the EOS-05 earth observation satellite on a GSLV Mk II "
            "from Satish Dhawan Space Centre on 4 September 2026."
        ),
        truth="TRUE",
        note=(
            "Heaviest satellite a GSLV has carried. Dated 4 September because that is "
            "2:55 am IST, the date ISRO, The Hindu and Wikipedia all use; the first "
            "draft of this case said 3 September, taking the UTC date from a search "
            "summary, and the service contradicted it correctly off those three "
            "sources. The case was wrong, not the verdict"
        ),
    ),
    Case(
        ref="S2",
        kind="text",
        payload=(
            "Good news! The Government of India is giving free laptops to all students "
            "under the National Student Laptop Scheme 2026. Apply online before the "
            "last date."
        ),
        truth="FALSE",
        note="PIB Fact Check: no such scheme was announced and no applications invited",
    ),
    Case(
        ref="S3",
        kind="text",
        payload=(
            "Saudi Arabia said Houthi rebels tried to attack Riyadh with a ballistic "
            "missile."
        ),
        truth="TRUE",
        note="First time the Saudi capital was targeted since the escalation; NPR, wires",
    ),
    Case(
        ref="S4",
        kind="text",
        payload="Dry ginger cures the Omicron variant of the coronavirus.",
        truth="FALSE",
        note="Alt News: scientifically baseless",
    ),
    Case(
        ref="S5",
        kind="url",
        payload="https://en.wikipedia.org/wiki/EOS-05",
        truth="TRUE",
        note="Encyclopedia page on the same launch — a clean read, unlike a live blog",
    ),
    Case(
        ref="S6",
        kind="text",
        payload=(
            "Applications are open for the National Sports Scholarship 2026-27 "
            "announced by the Government of India."
        ),
        truth="FALSE",
        note="PIB Fact Check: the flyer circulating on WhatsApp is a scam",
    ),
    Case(
        ref="S7",
        kind="url",
        payload=(
            "https://www.pib.gov.in/PressNoteDetails.aspx"
            "?NoteId=158973&ModuleId=3&reg=3&lang=1"
        ),
        truth="TRUE",
        note=(
            "An official release. pib.gov.in returns 403 to our own fetcher, so this "
            "also exercises the vendor rung of the link ladder"
        ),
    ),
)

SUITES: dict[str, tuple[Case, ...]] = {"one": SUITE_ONE, "two": SUITE_TWO}


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


def _undecided(result: Result) -> str:
    """Why there is no verdict — which is two different failures, not one.

    "miss" covered both and hid the difference. A claim that was read, searched and
    cited and then declined is a bar set too high; a submission that produced no
    claims at all never reached the bar, and usually means the input could not be
    read. They need opposite responses, so they are named apart.
    """
    return "not checked" if not result.claims else "abstained"


def _grade(result: Result) -> str:
    """correct | abstained | not checked | FALSE POSITIVE | FALSE NEGATIVE | error."""
    if result.error:
        return "error"

    action = result.action
    if result.case.truth == "TRUE":
        if action == "SAFE_TO_SHARE":
            # A clearance nobody can check is not a clearance.
            return "correct" if result.citations else _undecided(result)
        if action in ("DO_NOT_SHARE", "SHARE_WITH_CORRECTION"):
            return "FALSE POSITIVE"
        return _undecided(result)

    if action in ("DO_NOT_SHARE", "SHARE_WITH_CORRECTION"):
        return "correct" if result.citations else _undecided(result)
    if action == "SAFE_TO_SHARE":
        return "FALSE NEGATIVE"
    return _undecided(result)


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
    name = sys.argv[1] if len(sys.argv) > 1 else "two"
    if name not in SUITES:
        print(f"unknown suite {name!r}; choose from {', '.join(SUITES)}")
        return 2
    cases = SUITES[name]
    print(f"suite {name}: {len(cases)} cases")
    print()

    async with httpx.AsyncClient() as client:
        try:
            ready = await client.get(f"{BASE}/readyz", timeout=20)
        except Exception as error:
            print(f"no Factify at {BASE}: {error}")
            return 2
        if ready.status_code != 200 or not ready.json().get("ready"):
            print(f"Factify at {BASE} is not ready: {ready.text}")
            return 2

        results: list[Result] = []
        for case in cases:
            print(f"  running {case.ref} ({case.kind}) ...", flush=True)
            results.append(await _run(client, case))

    print()
    print(
        f"{'ref':<4} {'truth':<6} {'verdict':<22} {'grade':<13} "
        f"{'s':>5} {'claims':>7} {'cites':>6}  sources"
    )
    print("-" * 110)
    for result in results:
        grade = _grade(result)
        sources = ", ".join(result.publishers[:3]) or ("— " + result.error if result.error else "—")
        print(
            f"{result.case.ref:<4} {result.case.truth:<6} "
            f"{(result.action or 'ERROR'):<22} {grade:<13} "
            f"{result.seconds:5.1f} {result.claims:7} {result.citations:6}  {sources[:40]}"
        )

    grades = [_grade(r) for r in results]
    correct = grades.count("correct")
    print()
    print(f"correct          {correct}/{len(results)}")
    print(f"abstained        {grades.count('abstained')}   (read it, declined to decide)")
    print(f"not checked      {grades.count('not checked')}   (no claims — input unreadable)")
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
