"""Monthly plans (0008): what pays for a check, Razorpay's subscription signals, and
- against the test database - a Team organisation's pool, a person's plan, a
subscription starting and replacing another, and a month's extra usage to bill."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.repositories import AccountRepository
from app.orgs import plans
from app.orgs.errors import ApiError
from app.orgs.payments import Razorpay, payment_link_event, subscription_event
from app.orgs.store import OrgStore, Payer, org_month
from tests.conftest import requires_database

NOW = datetime(2026, 10, 15, tzinfo=UTC)


class TestWhatPaysForACheck:
    def test_the_plan_pays_first_then_credits_then_extra_usage(self) -> None:
        month = plans.Month(allowance=120, used=119, balance=2, paid=True, extra_enabled=True)

        assert plans.source_for(month, 1) == "plan"
        # A check is paid whole from one place: one plan check left is not enough for two.
        assert plans.source_for(month, 2) == "credits"
        assert plans.source_for(month, 3) == "extra"
        closed = plans.Month(allowance=120, used=120, balance=0, paid=True)
        assert plans.source_for(closed, 1) is None

    def test_extra_usage_stops_at_its_cap(self) -> None:
        month = plans.Month(
            allowance=0, used=0, balance=0, paid=True, extra_enabled=True,
            extra_cap_paise=900, extra_used_paise=600,
        )  # fmt: skip

        assert plans.source_for(month, 1) == "extra"
        assert plans.source_for(month, 2) is None

    def test_extra_usage_needs_a_paid_plan_and_no_unpaid_bill(self) -> None:
        free = plans.Month(allowance=30, used=30, balance=0, paid=False, extra_enabled=True)
        unpaid = plans.Month(
            allowance=120, used=120, balance=0, paid=True, extra_enabled=True, extra_blocked=True
        )

        assert plans.source_for(free, 1) is None
        assert plans.source_for(unpaid, 1) is None

    def test_a_lapsed_plan_is_free_after_its_grace(self) -> None:
        assert plans.effective_plan("plus", NOW + timedelta(days=3), NOW) is plans.PLUS
        assert plans.effective_plan("plus", NOW - timedelta(days=2), NOW) is plans.PLUS
        assert plans.effective_plan("plus", NOW - timedelta(days=4), NOW) is plans.FREE
        assert plans.effective_plan("nonsense", None, NOW) is plans.FREE

    def test_team_gives_three_hundred_checks_a_member(self) -> None:
        team = org_month({"plan": "team", "seats": 5, "plan_used": 10, "credits": 7}, NOW)
        api = org_month({"plan": "api", "seats": 0, "credits": 0}, NOW)

        assert team.allowance == 1_500 and plans.checks_left(team) == 1_497
        assert api.allowance == 0 and api.extra_open
        assert api.extra_price_paise == plans.API_CHECK_PAISE

    def test_the_price_list(self) -> None:
        listed = plans.catalogue()

        assert [p["id"] for p in listed["personal"]] == ["free", "plus", "pro"]  # type: ignore[index]
        assert plans.PLUS.price_paise("month") == 29_900
        assert plans.TEAM.price_paise("year", seats=3) == 5_988 * 100 * 3


class TestRazorpaySubscriptions:
    def test_a_subscriptions_checkout_signature(self) -> None:
        pay = Razorpay("rzp_test_x", "secret", "hook")
        good = hmac.new(b"secret", b"pay_1|sub_1", hashlib.sha256).hexdigest()

        assert pay.subscription_is_genuine("pay_1", "sub_1", good)
        assert not pay.subscription_is_genuine("pay_1", "sub_2", good)

    def test_webhook_events_say_what_happened_to_a_subscription(self) -> None:
        def event(kind: str) -> dict[str, object]:
            return {
                "event": kind,
                "payload": {"subscription": {"entity": {
                    "id": "sub_9", "current_start": 1_790_000_000, "current_end": 1_792_600_000,
                }}},
            }  # fmt: skip

        charged = subscription_event(event("subscription.charged"))
        assert charged is not None and charged[:2] == ("sub_9", "active")
        assert charged[3] == datetime.fromtimestamp(1_792_600_000, UTC)
        assert subscription_event(event("subscription.cancelled"))[1] == "cancelled"  # type: ignore[index]
        assert subscription_event(event("subscription.pending")) is None

    def test_a_paid_payment_link_names_its_link(self) -> None:
        paid = {
            "event": "payment_link.paid",
            "payload": {"payment_link": {"entity": {"id": "pl_1"}}},
        }

        assert payment_link_event(paid) == ("pl_1", "paid")
        assert payment_link_event({"event": "payment.captured"}) is None


async def _person(database: object, email: str) -> str:
    user_id = str(uuid4())
    async with database.connection() as conn:  # type: ignore[attr-defined]
        await conn.execute("INSERT INTO app_user (id, email) VALUES (%s, %s)", (user_id, email))
    return user_id


async def _drop(database: object, *, orgs: list[str], users: list[str]) -> None:
    async with database.connection() as conn:  # type: ignore[attr-defined]
        for o in orgs:
            await conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (o,))
            await conn.execute("DELETE FROM organisation WHERE id = %s", (o,))
        for u in users:
            await conn.execute("DELETE FROM app_user WHERE id = %s", (u,))


@requires_database
@pytest.mark.asyncio
class TestPlansInTheDatabase:
    async def test_a_team_pays_from_its_plan_then_credits_then_refuses(
        self, database: object
    ) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        owner = await _person(database, f"owner-{tag}@example.org")
        org = await store.create_org(user_id=owner, name=f"Plan {tag}", billing_email=None)
        try:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute(
                    "UPDATE organisation SET plan = 'team', seats = 3,"
                    " plan_renews_at = now() + interval '20 days' WHERE id = %s",
                    (org["id"],),
                )
                # All but two of this month's 900 Team checks are used.
                await conn.execute(
                    "INSERT INTO org_ledger (org_id, delta, reason, request_key, source)"
                    " VALUES (%s, -898, 'check', 'used', 'plan')",
                    (org["id"],),
                )
            await store.add_credits(org["id"], 1, reason="grant", actor=owner, request_key="g")
            payer = Payer(org_id=org["id"], user_id=owner, role="owner")

            first = await store.hold(payer, 2)
            assert first.source == "plan"
            await store.settle(first)
            second = await store.hold(payer, 1)
            assert second.source == "credits"
            await store.settle(second)
            with pytest.raises(ApiError) as refused:
                await store.hold(payer, 1)
            assert refused.value.error_code == "insufficient_credits"

            row = await store.org(org["id"])
            assert row["balance"] == 0  # the plan's checks never touched the credits
            assert row["plan_used"] == 900
        finally:
            await _drop(database, orgs=[org["id"]], users=[owner])

    async def test_a_persons_plan_pays_before_their_credits(self, database: object) -> None:
        tag = uuid4().hex[:8]
        user = await _person(database, f"plus-{tag}@example.org")
        try:
            async with database.transaction() as conn:  # type: ignore[attr-defined]
                accounts = AccountRepository(conn)
                await accounts.record(user_id=user, delta=5, reason="grant", request_key="g")
                await conn.execute(
                    "UPDATE app_user SET plan = 'plus', plan_renews_at = now() + interval '9 days'"
                    " WHERE id = %s",
                    (user,),
                )
                source = await accounts.charge_check(
                    user_id=user, cost=1, reason="check", request_key="check:1"
                )
                balance, used, checks = await accounts.totals(user_id=user)
                month = await accounts.month(user_id=user)
            assert source == "plan"
            assert (balance, used, checks) == (5, 1, 1)
            assert month is not None and month["used"] == 1
            assert month["resets_at"] > datetime.now(UTC)
        finally:
            await _drop(database, orgs=[], users=[user])

    async def test_a_subscription_starts_the_plan_and_replaces_the_old_one(
        self, database: object
    ) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        user = await _person(database, f"sub-{tag}@example.org")
        end = datetime.now(UTC) + timedelta(days=30)
        try:
            for n, plan in enumerate(("plus", "pro")):
                await store.create_subscription(
                    user_id=user, org_id=None, plan=plan, interval="month", seats=1,
                    amount_paise=29_900, razorpay_subscription_id=f"sub_{tag}_{n}",
                    razorpay_plan_id="plan_x", test_mode=True, actor=user,
                )  # fmt: skip
            await store.activate_subscription(
                f"sub_{tag}_0", current_start=None, current_end=end, actor="razorpay"
            )
            switched = await store.activate_subscription(
                f"sub_{tag}_1", current_start=None, current_end=end, actor="razorpay"
            )
            assert switched is not None and switched["replaced"] == [f"sub_{tag}_0"]

            async with database.connection() as conn:  # type: ignore[attr-defined]
                month = await AccountRepository(conn).month(user_id=user)
            assert month is not None and month["plan"] == "pro"
            current = await store.current_subscription(user_id=user)
            assert current is not None and current["razorpay_subscription_id"] == f"sub_{tag}_1"

            # A plan bought from the phone tells the app waiting on it.
            handoff, _token = await store.create_handoff(user, None)
            await store.create_subscription(
                user_id=user, org_id=None, plan="plus", interval="year", seats=1,
                amount_paise=299_000, razorpay_subscription_id=f"sub_{tag}_2",
                razorpay_plan_id="plan_y", test_mode=True, actor=user,
                handoff_id=handoff["id"],
            )  # fmt: skip
            await store.activate_subscription(
                f"sub_{tag}_2", current_start=None, current_end=end, actor="razorpay"
            )
            assert (await store.handoff(user, handoff["id"]))["status"] == "paid"

            await store.end_subscription(f"sub_{tag}_2", "cancelling")
            async with database.connection() as conn:  # type: ignore[attr-defined]
                ending = await AccountRepository(conn).month(user_id=user)
            assert ending is not None and ending["plan_cancel_at_end"] is True
        finally:
            await _drop(database, orgs=[], users=[user])

    async def test_last_months_extra_usage_is_billed_once(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        user = await _person(database, f"extra-{tag}@example.org")
        month = date(2026, 8, 1)
        try:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute(
                    "INSERT INTO credit_ledger (user_id, delta, reason, request_key, source,"
                    " created_at) VALUES (%s, -4, 'check', 'x', 'extra', '2026-08-10 12:00+05:30')",
                    (user,),
                )
            due = [r for r in await store.extra_usage_to_bill(month) if r["user_id"] == user]
            assert len(due) == 1 and due[0]["checks"] == 4
            assert due[0]["price_paise"] == plans.EXTRA_CHECK_PAISE

            await store.create_usage_bill(
                user_id=user, org_id=None, month=month, checks=4, amount_paise=1_200,
                payment_link_id=f"pl_{tag}", short_url=None, test_mode=True,
            )  # fmt: skip
            again = [r for r in await store.extra_usage_to_bill(month) if r["user_id"] == user]
            assert again == []
            await store.mark_bill(f"pl_{tag}", "paid")
            assert (await store.usage_bills(user_id=user))[0]["status"] == "paid"
        finally:
            await _drop(database, orgs=[], users=[user])


class TestThePriceListEndpoint:
    def test_anyone_can_read_the_price_list(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import create_app

        body = TestClient(create_app()).get("/v1/plans").json()

        assert [p["id"] for p in body["personal"]] == ["free", "plus", "pro"]
        assert body["team"][0]["min_seats"] == 3 and body["extra_check_inr"] == 3.0

    def test_subscribing_needs_you_to_be_signed_in(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import create_app

        response = TestClient(create_app()).post("/v1/me/plan/subscribe", json={"plan": "plus"})

        assert response.status_code in (401, 503)


class TestBillingAMonth:
    def test_last_month_is_the_month_before_in_india_time(self) -> None:
        from app.orgs.month_close import india_today, last_month

        assert last_month(date(2026, 10, 1)) == date(2026, 9, 1)
        assert last_month(date(2026, 1, 15)) == date(2025, 12, 1)
        # 20:00 UTC on 31 Oct is already 1 Nov in India.
        assert india_today(datetime(2026, 10, 31, 20, 0, tzinfo=UTC)) == date(2026, 11, 1)

    @pytest.mark.asyncio
    async def test_each_owner_gets_one_link_and_a_failure_is_tried_again(self) -> None:
        from app.orgs.month_close import bill_month
        from app.orgs.payments import PaymentsUnavailable

        class _Store:
            def __init__(self) -> None:
                self.bills: list[dict[str, object]] = []

            async def extra_usage_to_bill(self, month: date) -> list[dict[str, object]]:
                return [
                    {
                        "user_id": "u1",
                        "org_id": None,
                        "email": "a@x.in",
                        "checks": 4,
                        "price_paise": 300,
                    },
                    {
                        "user_id": None,
                        "org_id": "o1",
                        "email": "b@x.in",
                        "checks": 10,
                        "price_paise": 400,
                    },
                ]

            async def create_usage_bill(self, **kwargs: object) -> None:
                self.bills.append(kwargs)

        class _Razorpay:
            test_mode = True

            async def create_payment_link(self, **kwargs: object) -> dict[str, object]:
                if kwargs["email"] == "b@x.in":
                    raise PaymentsUnavailable("down")
                return {"id": "pl_1", "short_url": "https://rzp.io/x"}

        store = _Store()
        billed = await bill_month(store, _Razorpay(), date(2026, 8, 1))

        assert (billed.sent, billed.failed) == (1, 1)
        assert store.bills[0]["amount_paise"] == 1_200 and store.bills[0]["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_a_month_not_over_is_never_billed(self) -> None:
        from app.orgs.month_close import bill_month, india_today

        with pytest.raises(ValueError):
            await bill_month(object(), object(), india_today().replace(day=1))


@requires_database
@pytest.mark.asyncio
class TestPlansPaidAPeriodAtATime:
    async def test_paying_again_for_the_same_plan_adds_the_next_month(
        self, database: object
    ) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        user = await _person(database, f"prepaid-{tag}@example.org")
        try:
            handoff, _token = await store.create_handoff(user, None)
            for n in range(2):
                await store.create_subscription(
                    user_id=user, org_id=None, plan="plus", interval="month", seats=1,
                    amount_paise=29_900, razorpay_subscription_id=None, razorpay_plan_id=None,
                    test_mode=True, actor=user, kind="prepaid", order_id=f"order_{tag}_{n}",
                    handoff_id=handoff["id"] if n == 0 else None,
                )  # fmt: skip
            first = await store.activate_prepaid(f"order_{tag}_0", "pay_1", user)
            again = await store.activate_prepaid(f"order_{tag}_0", "pay_1", "razorpay")
            second = await store.activate_prepaid(f"order_{tag}_1", "pay_2", user)
            assert first is not None and second is not None and again is not None
            assert again["status"] == "active"  # the webhook after the website: once only
            one = datetime.fromisoformat(first["current_end"])
            two = datetime.fromisoformat(second["current_end"])
            assert 27 <= (two - one).days <= 31  # the second month follows the first

            async with database.connection() as conn:  # type: ignore[attr-defined]
                month = await AccountRepository(conn).month(user_id=user)
            assert month is not None and month["plan"] == "plus"
            assert month["plan_renews_at"] == two
            assert month["plan_cancel_at_end"] is True  # paid for, not renewing by itself
            assert (await store.handoff(user, handoff["id"]))["status"] == "paid"
            statuses = {s["order_id"]: s["status"] for s in await store.subscriptions(user_id=user)}
            assert statuses == {f"order_{tag}_0": "ended", f"order_{tag}_1": "active"}
            assert await store.activate_prepaid("order_not_a_plan", "pay_x", "razorpay") is None
        finally:
            await _drop(database, orgs=[], users=[user])

    async def test_a_team_paid_for_a_year(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        owner = await _person(database, f"teamyear-{tag}@example.org")
        org = await store.create_org(user_id=owner, name=f"Year {tag}", billing_email=None)
        try:
            await store.create_subscription(
                user_id=None, org_id=org["id"], plan="team", interval="year", seats=4,
                amount_paise=5_988 * 400, razorpay_subscription_id=None, razorpay_plan_id=None,
                test_mode=True, actor=owner, kind="prepaid", order_id=f"order_{tag}",
            )  # fmt: skip
            row = await store.activate_prepaid(f"order_{tag}", "pay_1", owner)
            assert row is not None
            ends = datetime.fromisoformat(row["current_end"])
            assert 360 <= (ends - datetime.now(UTC)).days <= 366
            info = await store.org(org["id"])
            assert (info["plan"], info["seats"]) == ("team", 4)
            payer = Payer(org_id=org["id"], user_id=owner, role="owner")
            hold = await store.hold(payer, 1)
            assert hold.source == "plan"
            await store.release(hold)
        finally:
            await _drop(database, orgs=[org["id"]], users=[owner])


class TestAPlanPaidAMonthAtATime:
    def test_it_stops_on_its_end_date_while_a_renewing_one_gets_grace(self) -> None:
        ended = NOW - timedelta(hours=1)

        assert plans.effective_plan("plus", ended, NOW, ending=True) is plans.FREE
        assert plans.effective_plan("plus", ended, NOW, ending=False) is plans.PLUS
        assert plans.effective_plan("plus", NOW + timedelta(days=1), NOW, ending=True) is plans.PLUS
        team = org_month(
            {"plan": "team", "seats": 3, "plan_renews_at": ended, "plan_cancel_at_end": True}, NOW
        )
        assert team.allowance == 0
