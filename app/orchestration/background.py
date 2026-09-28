"""Checks run in the background while the app watches them progress.

Every claim is searched and read, which takes one to three minutes for an article -
longer than the app waits on one request. So the request returns at once with a case
id, the check runs here, and the app polls the case: progress ("3 of 7 claims
checked") while it runs, the verdict when it is done. Videos are checked this way too.

Held in memory. A restart loses the checks in flight, and a finished one is kept for a
quarter of an hour for the app to collect; neither is a place anything is recorded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger("factify.background")

# How long a finished check waits to be collected.
_KEEP_SECONDS = 900.0

Progress = Callable[[int, int], None]


@dataclass(slots=True)
class BackgroundRun:
    case_id: str
    started: float
    status: str = "running"  # running | done | failed
    claims_done: int = 0
    claims_total: int = 0
    response: Any = None
    error_status: int = 500
    error_detail: str = "the check did not finish"
    finished: float | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class BackgroundChecks:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._runs: dict[str, BackgroundRun] = {}

    def start(self, case_id: str, work: Callable[[Progress], Awaitable[Any]]) -> BackgroundRun:
        """Start `work` in the background. It is handed a progress callback."""
        self._forget_collected()
        run = BackgroundRun(case_id=case_id, started=self._clock())

        def progress(done: int, total: int) -> None:
            run.claims_done, run.claims_total = done, total

        async def _go() -> None:
            try:
                run.response = await work(progress)
                run.status = "done"
            except HTTPException as refused:
                # The check's own answer, such as "nothing on that page to check",
                # delivered when the app collects it rather than lost.
                run.status = "failed"
                run.error_status = refused.status_code
                run.error_detail = str(refused.detail)
            except Exception:
                logger.exception("background check %s failed", case_id)
                run.status = "failed"
            finally:
                run.finished = self._clock()

        run.task = asyncio.create_task(_go())
        self._runs[case_id] = run
        return run

    def get(self, case_id: str) -> BackgroundRun | None:
        return self._runs.get(case_id)

    def elapsed(self, run: BackgroundRun) -> int:
        return int((run.finished or self._clock()) - run.started)

    def _forget_collected(self) -> None:
        now = self._clock()
        self._runs = {
            key: run
            for key, run in self._runs.items()
            if run.finished is None or now - run.finished < _KEEP_SECONDS
        }
