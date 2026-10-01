"""Billing a month's extra usage, once, after the month ends (0008).

`bill_month` sends every person and organisation with extra usage in a month a
Razorpay payment link for it; a month already billed for someone is never billed
again (the store skips it, and `usage_bill` is unique per owner and month).

`MonthlyBilling` runs it in the background: a little after startup and then every
few hours it bills last month (India time). Nothing is sent before a month is over,
and a link that could not be made is simply tried again on the next run.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.orgs import payments

logger = logging.getLogger("factify.orgs.month_close")

INDIA = timedelta(hours=5, minutes=30)


def india_today(now: datetime | None = None) -> date:
    return ((now or datetime.now(UTC)) + INDIA).date()


def last_month(today: date) -> date:
    """The first day of the month before `today`'s."""
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


@dataclass(frozen=True, slots=True)
class Billed:
    month: date
    sent: int
    failed: int


async def bill_month(store: Any, razorpay: Any, month: date) -> Billed:
    """Send a payment link to everyone with extra usage in `month` not yet billed."""
    if month >= india_today().replace(day=1):
        raise ValueError("a month can be billed only after it ends")
    sent = failed = 0
    for row in await store.extra_usage_to_bill(month):
        checks = int(row["checks"])
        amount = checks * int(row["price_paise"])
        if checks <= 0 or amount <= 0:
            continue
        owner = row.get("user_id") or row.get("org_id")
        try:
            link = await razorpay.create_payment_link(
                amount_paise=amount,
                description=f"Factify extra usage, {month:%B %Y}: {checks:,} checks",
                email=row.get("email"),
                reference=f"extra-{month:%Y%m}-{str(owner)[:8]}",
                notes={"month": f"{month:%Y-%m}", "owner": str(owner)},
            )
        except payments.PaymentsUnavailable:
            logger.exception("could not bill extra usage for %s", owner)
            failed += 1
            continue
        await store.create_usage_bill(
            user_id=row.get("user_id"), org_id=row.get("org_id"), month=month, checks=checks,
            amount_paise=amount, payment_link_id=str(link["id"]),
            short_url=link.get("short_url"), test_mode=razorpay.test_mode,
        )  # fmt: skip
        sent += 1
    if sent or failed:
        logger.info("billed extra usage for %s: %d sent, %d failed", month, sent, failed)
    return Billed(month=month, sent=sent, failed=failed)


class MonthlyBilling:
    """Bills last month's extra usage in the background, every `interval_seconds`."""

    def __init__(self, *, store: Any, razorpay: Any, interval_seconds: float) -> None:
        self._store = store
        self._razorpay = razorpay
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def run_once(self) -> Billed:
        return await bill_month(self._store, self._razorpay, last_month(india_today()))

    def start(self) -> None:
        if self._interval <= 0 or self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        await asyncio.sleep(min(120.0, self._interval))
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("billing last month's extra usage failed; trying again later")
            await asyncio.sleep(self._interval)
