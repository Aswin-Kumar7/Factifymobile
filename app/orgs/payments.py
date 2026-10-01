"""Buying credits with Razorpay, and proving a domain with a DNS TXT record.

Razorpay: the server creates an order for a credit pack; the website opens
Razorpay Checkout for it; the payment is confirmed either by the website handing
back Razorpay's signed result or by Razorpay's webhook, whichever arrives first,
and the credits are added once (`OrgStore.mark_paid`). Both signatures are
HMAC-SHA256, checked here in constant time. Test keys (`rzp_test_`) move no money.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from app.security.fetcher import FetchResult, SecureFetcher

_API = "https://api.razorpay.com/v1"


@dataclass(frozen=True, slots=True)
class Pack:
    id: str
    name: str
    credits: int
    price_inr: int


# Priced from what a check costs us (measured 2026-10-01): a check answered from the
# cache is free to serve, one our own records settle about Rs 0.6, and a full
# open-web check about Rs 5-6 (some 49,000 model tokens and five searches). The
# first prices - Rs 0.50 to Rs 1 a check - were set for testing and lost money on
# every new question. Every organisation price covers even a full open-web check
# today; every pack covers the blended cost of a check at launch (about Rs 2.9),
# with the margin growing as more answers come from the cache and our own records.
PACKS: tuple[Pack, ...] = (
    Pack("starter", "Starter", 1_000, 5_999),
    Pack("team", "Team", 5_000, 24_999),
    Pack("newsroom", "Newsroom", 20_000, 89_999),
    Pack("enterprise", "Enterprise", 100_000, 399_999),
)


# For one person's own credits: smaller packs, priced for people rather than
# companies, and still above what a check costs on average.
PERSONAL_PACKS: tuple[Pack, ...] = (
    Pack("p50", "50 checks", 50, 249),
    Pack("p150", "150 checks", 150, 599),
    Pack("p400", "400 checks", 400, 1_399),
)


def pack(pack_id: str) -> Pack | None:
    return next((p for p in PACKS if p.id == pack_id), None)


def personal_pack(pack_id: str) -> Pack | None:
    return next((p for p in PERSONAL_PACKS if p.id == pack_id), None)


class PaymentsUnavailable(Exception):
    pass


class Razorpay:
    def __init__(self, key_id: str, key_secret: str, webhook_secret: str | None) -> None:
        self.key_id = key_id
        self._secret = key_secret
        self._webhook_secret = webhook_secret

    @property
    def test_mode(self) -> bool:
        return self.key_id.startswith("rzp_test_")

    async def create_order(self, *, amount_paise: int, receipt: str, notes: dict[str, str]) -> str:
        basic = base64.b64encode(f"{self.key_id}:{self._secret}".encode()).decode()
        result = await SecureFetcher(timeout_seconds=20.0).post_json(
            f"{_API}/orders",
            {"amount": amount_paise, "currency": "INR", "receipt": receipt[:40], "notes": notes},
            provider="razorpay",
            headers={"Authorization": f"Basic {basic}"},
        )
        if not isinstance(result, FetchResult):
            raise PaymentsUnavailable(f"Razorpay refused or could not be reached: {result}")
        order_id = json.loads(result.body or b"{}").get("id")
        if not order_id:
            raise PaymentsUnavailable("Razorpay did not return an order id")
        return str(order_id)

    def payment_is_genuine(self, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(
            self._secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def webhook_is_genuine(self, body: bytes, signature: str) -> bool:
        if not self._webhook_secret:
            return False
        expected = hmac.new(self._webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")


def failed_order(event: dict[str, Any]) -> str | None:
    """The order id of a webhook event that means "this payment failed", else None."""
    if event.get("event") != "payment.failed":
        return None
    payment = ((event.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_id = payment.get("order_id")
    return str(order_id) if order_id else None


def paid_order(event: dict[str, Any]) -> tuple[str, str] | None:
    """(order id, payment id) from a webhook event that means "paid", else None."""
    kind = event.get("event")
    payload = event.get("payload") or {}
    if kind in ("payment.captured", "order.paid"):
        payment = (payload.get("payment") or {}).get("entity") or {}
        order_id = payment.get("order_id") or (
            (payload.get("order") or {}).get("entity") or {}
        ).get("id")
        if order_id and payment.get("id"):
            return str(order_id), str(payment["id"])
    return None


async def txt_records(name: str) -> list[str]:
    """The TXT records of `name`, via Google's DNS-over-HTTPS resolver."""
    from urllib.parse import urlencode

    result = await SecureFetcher(timeout_seconds=10.0).get_json(
        f"https://dns.google/resolve?{urlencode({'name': name, 'type': 'TXT'})}",
        provider="dns",
    )
    if not isinstance(result, FetchResult) or result.status_code >= 400:
        raise PaymentsUnavailable("DNS could not be asked")
    answers = json.loads(result.body or b"{}").get("Answer") or []
    return [str(a.get("data", "")).strip('"') for a in answers if a.get("type") == 16]
