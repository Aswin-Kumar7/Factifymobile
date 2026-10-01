"""What an organisation has left, its alerts, invoices with GST, payment handoffs
that expire, the shared history's names and kinds, and the admin's review queue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.api.orgs import _alerts
from app.orgs import invoices, plans
from app.orgs.store import OrgStore, Payer, month_summary
from tests.conftest import requires_database

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


def _org(**fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "plan": "credits",
        "seats": 0,
        "plan_renews_at": None,
        "plan_cancel_at_end": False,
        "extra_usage": False,
        "extra_cap_paise": None,
        "balance": 0,
        "held_credits": 0,
        "held_plan": 0,
        "held_extra": 0,
        "plan_used": 0,
        "extra_checks": 0,
        "extra_blocked": False,
        "status": "active",
        "month_spend": 0,
        "monthly_spend_limit": None,
    }
    base.update(fields)
    base["month"] = month_summary(base, NOW)
    return base


class TestWhatIsLeft:
    def test_a_team_org_with_no_credits_still_has_its_plan(self) -> None:
        org = _org(plan="team", seats=3, plan_renews_at=NOW + timedelta(days=10), plan_used=100)
        m = org["month"]
        assert isinstance(m, dict)
        assert m["allowance"] == 3 * plans.TEAM.monthly_checks
        assert m["checks_left"] == 3 * plans.TEAM.monthly_checks - 100
        assert _alerts(org) == []

    def test_running_checks_count_as_used(self) -> None:
        org = _org(plan="team", seats=3, plan_renews_at=NOW + timedelta(days=10), held_plan=5)
        assert org["month"]["plan_used"] == 5  # type: ignore[index]

    def test_a_pay_per_check_org_is_not_out_of_credits(self) -> None:
        org = _org(plan="api", extra_usage=True)
        m = org["month"]
        assert m["pay_per_check"] and m["extra_open"]  # type: ignore[index]
        assert not any(a["level"] == "error" for a in _alerts(org))

    def test_a_packs_org_with_nothing_left_is_refused(self) -> None:
        alerts = _alerts(_org())
        assert alerts and alerts[0]["level"] == "error"
        assert "refused" in alerts[0]["text"]

    def test_an_api_org_at_its_cap_is_refused(self) -> None:
        org = _org(plan="api", extra_usage=True, extra_cap_paise=800, extra_checks=2)
        assert org["month"]["extra_checks_left"] == 0  # type: ignore[index]
        assert any("cap" in a["text"] and a["level"] == "error" for a in _alerts(org))

    def test_a_team_org_past_its_plan_goes_to_extra_usage(self) -> None:
        org = _org(
            plan="team", seats=3, plan_renews_at=NOW + timedelta(days=10), plan_used=900,
            extra_usage=True,
        )  # fmt: skip
        alerts = _alerts(org)
        assert [a["level"] for a in alerts] == ["warning"]
        assert "extra usage" in alerts[0]["text"]


class TestInvoices:
    def test_gst_is_split_out_of_the_price_exactly(self) -> None:
        taxable, gst = invoices.gst_split(29_900)
        assert taxable + gst == 29_900
        assert taxable == 25_339 and gst == 4_561

    def test_a_plan_invoice_shows_the_split_and_both_gstins(self) -> None:
        html = invoices.for_plan(
            {
                "id": str(uuid4()), "plan": "team", "interval": "month", "seats": 3,
                "amount_paise": 179_700, "current_start": "2026-10-01T00:00:00+00:00",
                "current_end": "2026-11-01T00:00:00+00:00", "order_id": "order_x",
                "test_mode": True, "org_name": "Desk", "billing_email": "b@example.org",
                "gst_number": "29ABCDE1234F1Z5",
            },
            "33AAAAA0000A1Z5",
        )  # fmt: skip
        assert "Taxable value" in html and "GST @ 18%" in html
        assert "29ABCDE1234F1Z5" in html and "33AAAAA0000A1Z5" in html
        assert "Team plan" in html and "3 members" in html

    def test_an_extra_usage_invoice_names_the_month(self) -> None:
        html = invoices.for_usage_bill(
            {
                "id": str(uuid4()), "month": "2026-09-01", "checks": 12, "amount_paise": 3_600,
                "paid_at": "2026-10-02", "payment_link_id": "plink_1", "test_mode": False,
                "org_name": "Asha", "billing_email": "a@example.org", "gst_number": None,
            },
            None,
        )  # fmt: skip
        assert "Extra usage, 2026-09" in html and "12 checks" in html
        assert "GSTIN" not in html


async def _person(database: object, email: str, name: str | None = None) -> str:
    user_id = str(uuid4())
    async with database.connection() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            "INSERT INTO app_user (id, email, display_name) VALUES (%s, %s, %s)",
            (user_id, email, name),
        )
    return user_id


async def _cleanup(database: object, org_id: str | None, users: list[str]) -> None:
    async with database.connection() as conn:  # type: ignore[attr-defined]
        if org_id:
            await conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (org_id,))
            await conn.execute("DELETE FROM organisation WHERE id = %s", (org_id,))
        for u in users:
            await conn.execute("DELETE FROM app_user WHERE id = %s", (u,))


@requires_database
@pytest.mark.asyncio
class TestInTheDatabase:
    async def test_a_team_org_shows_its_plan_and_this_months_split(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        owner = await _person(database, f"owner-{tag}@example.org", "Asha")
        org = await store.create_org(user_id=owner, name=f"Test {tag}", billing_email=None)
        try:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute(
                    "UPDATE organisation SET plan = 'team', seats = 3,"
                    " plan_renews_at = now() + interval '20 days' WHERE id = %s",
                    (org["id"],),
                )
            payer = Payer(org_id=org["id"], user_id=owner, role="owner")
            await store.settle(await store.hold(payer, 1))
            _, key = await store.create_key(org["id"], owner, name="ci")
            keyed, _ = await store.authenticate_key(key, None)
            await store.settle(await store.hold(keyed, 3))

            got = await store.org(org["id"])
            assert got["balance"] == 0
            assert got["month"]["checks_left"] == 900 - 4
            mine = next(o for o in await store.my_orgs(owner) if o["id"] == org["id"])
            assert mine["checks_left"] == 896 and mine["allowance"] == 900

            split = await store.month_breakdown(org["id"])
            assert split["total"] == 4 and split["via_keys"] == 3 and split["via_web"] == 1
            assert split["plan"] == 4 and split["credits"] == 0
        finally:
            await _cleanup(database, org["id"], [owner])

    async def test_shared_history_names_the_member_and_the_kind(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        owner = await _person(database, f"owner-{tag}@example.org", "Asha Rao")
        org = await store.create_org(user_id=owner, name=f"Test {tag}", billing_email=None)
        case_id = str(uuid4())
        try:
            await store.update_org(org["id"], owner, {"shared_history": True})
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute(
                    "INSERT INTO verification_case (id, request_id, input_type)"
                    " VALUES (%s, %s, 'url')",
                    (case_id, f"req-{tag}"),
                )
            payer = Payer(org_id=org["id"], user_id=owner, role="owner")
            await store.record_check(
                payer, case_id=case_id, input_type=None, title="A claim", verdict="FALSE"
            )
            [row] = await store.history(org["id"])
            assert row["name"] == "Asha Rao" and row["input_type"] == "link"
        finally:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute("DELETE FROM verification_case WHERE id = %s", (case_id,))
            await _cleanup(database, org["id"], [owner])

    async def test_an_opened_payment_link_expires(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        user = await _person(database, f"buyer-{tag}@example.org")
        try:
            handoff, token = await store.create_handoff(user, None)
            await store.use_handoff(token)
            assert not (await store.handoff(user, handoff["id"]))["expired"]
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute(
                    "UPDATE payment_handoff SET used_at = now() - interval '31 minutes'"
                    " WHERE id = %s",
                    (handoff["id"],),
                )
            assert (await store.handoff(user, handoff["id"]))["expired"]
            # A finished one is not "expired": it is what it finished as.
            await store.finish_handoff(user, handoff["id"], "cancelled")
            state = await store.handoff(user, handoff["id"])
            assert state["status"] == "cancelled" and not state["expired"]
        finally:
            await _cleanup(database, None, [user])

    async def test_reported_cases_reach_the_admin(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        case_id = str(uuid4())
        try:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute(
                    "INSERT INTO verification_case (id, request_id, input_type)"
                    " VALUES (%s, %s, 'text')",
                    (case_id, f"req-{tag}"),
                )
                await conn.execute(
                    "INSERT INTO review_item (case_id, reason) VALUES (%s, 'user_reported')",
                    (case_id,),
                )
            counts = await store.admin_counts()
            assert counts["reports"] >= 1
            pending = await store.admin_reviews()
            assert any(r["case_id"] == case_id and r["reason"] == "user_reported" for r in pending)
        finally:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute("DELETE FROM verification_case WHERE id = %s", (case_id,))
