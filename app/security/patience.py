"""How long a call may wait for a busy provider, for the check running now.

A person waiting on one request has seconds to spare, so a provider that says "too
many requests" is given a short wait and then the source is dropped. A check that
runs in the background, while the app shows its progress, has minutes: dropping a
source there to save ten seconds turned into claims read as "we ran out of time" with
time left over (2026-09-28). In a patient check the per-minute pacing waits longer
and a provider's own "try again" is honoured more times, for longer.

Set for the length of one check, like `current_check`, and inherited by every task
it starts.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Patience:
    # Longest wait for room under our own per-minute ceiling for a provider.
    pace_seconds: float
    # How many times a provider's 429/5xx is retried, and the longest single wait.
    retries: int
    retry_after_cap: float


# A request someone is waiting on.
BRIEF = Patience(pace_seconds=20.0, retries=2, retry_after_cap=10.0)
# A check in the background: Azure's per-minute token limit clears within a minute.
PATIENT = Patience(pace_seconds=90.0, retries=5, retry_after_cap=30.0)

current_patience: ContextVar[Patience] = ContextVar("current_patience", default=BRIEF)
