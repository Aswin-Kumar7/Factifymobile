"""Checks run in the background while the app watches them progress.

Every claim is searched and read, which takes one to three minutes for an article -
longer than the app waits on one request. So the request returns at once with a case
id, the check runs here, and the app polls the case: progress ("3 of 7 claims
checked") while it runs, the verdict when it is done. Videos are checked this way too.

Held in memory. A restart loses the checks in flight, and a finished one is kept for a
quarter of an hour for the app to collect; neither is a place anything is recorded.

A check can be stopped by the person who started it (`DELETE /v1/cases/{id}`). Its
task is cancelled, so it stops spending searches, and it is never charged: a check
is charged only once it has its answer, and once it has one it can no longer be
stopped (`settling`).
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
    status: str = "running"  # running | done | failed | cancelled
    # Who started it (the signed-in person's id), the only one who may stop it. None
    # for an anonymous check, which only its case id - unguessable - can stop.
    owner: str | None = None
    # The answer is in and being charged for: too late to stop it.
    settling: bool = False
    # Run when it is stopped: gives back what was held for it.
    on_cancel: Callable[[], Awaitable[None]] | None = field(default=None, repr=False)
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

    def start(
        self,
        case_id: str,
        work: Callable[[Progress], Awaitable[Any]],
        *,
        owner: str | None = None,
        on_cancel: Callable[[], Awaitable[None]] | None = None,
    ) -> BackgroundRun:
        """Start `work` in the background. It is handed a progress callback."""
        self._forget_collected()
        run = BackgroundRun(
            case_id=case_id, started=self._clock(), owner=owner, on_cancel=on_cancel
        )

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
            except asyncio.CancelledError:
                run.status = "cancelled"
                raise
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

    async def cancel(self, run: BackgroundRun) -> bool:
        """Stop a running check. False when it is too late: finished, or settling.

        The task is cancelled at once and then waited for, briefly, so whatever it
        held is given back before this returns; `on_cancel` gives it back too, for a
        task cancelled before it ever ran (a hold that was never released otherwise
        stays held until it expires).
        """
        if run.status == "cancelled":
            return True
        if run.status != "running" or run.settling or run.task is None:
            return False
        run.task.cancel()
        run.status = "cancelled"
        await asyncio.wait({run.task}, timeout=5.0)
        if run.on_cancel is not None:
            try:
                await run.on_cancel()
            except Exception:
                logger.exception("background check %s: could not give back its hold", run.case_id)
        run.finished = run.finished or self._clock()
        return True

    def elapsed(self, run: BackgroundRun) -> int:
        return int((run.finished or self._clock()) - run.started)

    def _forget_collected(self) -> None:
        now = self._clock()
        self._runs = {
            key: run
            for key, run in self._runs.items()
            if run.finished is None or now - run.finished < _KEEP_SECONDS
        }
