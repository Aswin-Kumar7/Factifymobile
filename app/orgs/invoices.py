# ruff: noqa: E501
"""Printable invoices for every kind of payment: a credit pack, a plan (personal or
Team, paid by one order or a subscription's payment) and a month's extra usage.

Prices are said to include GST, so every invoice splits its total into the taxable
value and GST at 18% (`gst_split`). The buyer's GSTIN (an organisation's GST number)
is printed when it was given; Factify's own when the server has one configured
(FACTIFY_BILLING__GSTIN).
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

GST_RATE_PERCENT = 18


def gst_split(total_paise: int, rate_percent: int = GST_RATE_PERCENT) -> tuple[int, int]:
    """(taxable value, GST) in paise for a GST-inclusive total; they add up exactly."""
    taxable = round(total_paise * 100 / (100 + rate_percent))
    return taxable, total_paise - taxable


@dataclass(frozen=True, slots=True)
class Line:
    description: str
    quantity: str
    amount_paise: int


def _rupees(paise: int) -> str:
    return f"&#8377;{paise / 100:,.2f}"


def render(
    *,
    number: str,
    date: str,
    billed_to: dict[str, Any],
    lines: list[Line],
    references: list[str],
    test_mode: bool,
    seller_gstin: str | None,
) -> str:
    total = sum(line.amount_paise for line in lines)
    taxable, gst = gst_split(total)
    test = (
        "<p style='color:#b45309'><b>Test mode: no money was charged.</b></p>" if test_mode else ""
    )
    seller = "Factify" + (f"<br>GSTIN: {escape(seller_gstin)}" if seller_gstin else "")
    buyer_gst = billed_to.get("gst_number")
    rows = "".join(
        f"<tr><td>{escape(line.description)}</td><td>{escape(line.quantity)}</td>"
        f"<td class='n'>{_rupees(line.amount_paise)}</td></tr>"
        for line in lines
    )
    refs = "<br>".join(escape(r) for r in references if r)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Invoice {escape(number)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:15px/1.6 system-ui,sans-serif;max-width:680px;margin:40px auto;padding:0 20px;color:#1c1b18}}
table{{width:100%;border-collapse:collapse;margin:20px 0}}td,th{{border-bottom:1px solid #e2ded4;padding:8px;text-align:left}}
.n{{text-align:right;white-space:nowrap}}.sub td{{color:#5c5a52;border-bottom:none;padding:4px 8px}}
.grid{{display:flex;gap:40px;flex-wrap:wrap}}h1{{font-family:Georgia,serif}}@media print{{button{{display:none}}}}</style></head><body>
<h1>Factify - Tax invoice</h1>{test}
<p>Invoice no. {escape(number)}<br>Date: {escape(date)}</p>
<div class="grid"><p><b>From</b><br>{seller}</p>
<p><b>Billed to</b><br>{escape(str(billed_to.get("org_name") or ""))}<br>{escape(str(billed_to.get("billing_email") or ""))}
{("<br>GSTIN: " + escape(str(buyer_gst))) if buyer_gst else ""}</p></div>
<table><tr><th>Item</th><th>Quantity</th><th class="n">Amount</th></tr>{rows}
<tr class="sub"><td colspan="2">Taxable value</td><td class="n">{_rupees(taxable)}</td></tr>
<tr class="sub"><td colspan="2">GST @ {GST_RATE_PERCENT}% (included in the price)</td><td class="n">{_rupees(gst)}</td></tr>
<tr><th colspan="2">Total (INR, including GST)</th><th class="n">{_rupees(total)}</th></tr></table>
<p>{refs}</p>
<button onclick="print()">Print or save as PDF</button></body></html>"""


def _day(value: Any) -> str:
    return str(value or "")[:10]


def for_pack(p: dict[str, Any], pack_name: str, seller_gstin: str | None) -> str:
    return render(
        number=f"FCT-{str(p['id'])[:8].upper()}",
        date=_day(p.get("paid_at")),
        billed_to=p,
        lines=[
            Line(
                f"{pack_name} credit pack", f"{int(p['credits']):,} credits", int(p["amount_paise"])
            )
        ],
        references=[
            f"Razorpay order {p.get('order_id') or ''}",
            f"Payment {p.get('payment_id') or ''}",
        ],
        test_mode=bool(p.get("test_mode")),
        seller_gstin=seller_gstin,
    )


_PLAN_NAMES = {"plus": "Plus", "pro": "Pro", "team": "Team"}


def for_plan(s: dict[str, Any], seller_gstin: str | None) -> str:
    name = _PLAN_NAMES.get(str(s.get("plan")), str(s.get("plan")).title())
    period = "1 month" if s.get("interval") == "month" else "1 year"
    start, end = _day(s.get("current_start")), _day(s.get("current_end"))
    what = f"Factify {name} plan, {period}" + (f" ({start} to {end})" if start and end else "")
    quantity = f"{int(s.get('seats') or 1)} members" if s.get("plan") == "team" else "1"
    refs = []
    if s.get("order_id"):
        refs.append(f"Razorpay order {s['order_id']}")
    if s.get("razorpay_subscription_id"):
        refs.append(f"Razorpay subscription {s['razorpay_subscription_id']}")
    if s.get("payment_id"):
        refs.append(f"Payment {s['payment_id']}")
    return render(
        number=f"FCT-P-{str(s['id'])[:8].upper()}",
        date=start or _day(s.get("updated_at")),
        billed_to=s,
        lines=[Line(what, quantity, int(s["amount_paise"]))],
        references=refs,
        test_mode=bool(s.get("test_mode")),
        seller_gstin=seller_gstin,
    )


def for_usage_bill(b: dict[str, Any], seller_gstin: str | None) -> str:
    month = _day(b.get("month"))[:7]
    return render(
        number=f"FCT-U-{str(b['id'])[:8].upper()}",
        date=_day(b.get("paid_at")),
        billed_to=b,
        lines=[
            Line(f"Extra usage, {month}", f"{int(b['checks']):,} checks", int(b["amount_paise"]))
        ],
        references=[f"Razorpay payment link {b.get('payment_link_id') or ''}"],
        test_mode=bool(b.get("test_mode")),
        seller_gstin=seller_gstin,
    )
