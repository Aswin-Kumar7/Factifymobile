"""Organisations: API key format, Razorpay signatures, and - against the test
database - the credit pool's hold/settle under parallel requests, limits, key
authentication and invitations."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from uuid import uuid4

import pytest

from app.orgs import keys
from app.orgs.errors import ApiError
from app.orgs.payments import Razorpay, paid_order
from app.orgs.store import OrgStore, Payer
from tests.conftest import requires_database


class TestKeyFormat:
    def test_a_new_key_has_the_prefix_and_a_valid_checksum(self) -> None:
        key = keys.new_key()
        assert key.startswith("fct_live_") and len(key) == 9 + 32 + 6
        assert keys.looks_valid(key)

    def test_a_mistyped_key_fails_the_checksum(self) -> None:
        key = keys.new_key()
        typo = key[:-8] + ("A" if key[-8] != "A" else "B") + key[-7:]
        assert not keys.looks_valid(typo)
        assert not keys.looks_valid("sk_live_whatever")

    def test_only_a_hash_and_a_short_prefix_are_kept(self) -> None:
        key = keys.new_key()
        assert keys.hash_key(key) == hashlib.sha256(key.encode()).hexdigest()
        assert keys.shown_part(key) == key[:13] and len(keys.shown_part(key)) < len(key)


class TestRazorpay:
    def test_a_genuine_payment_signature_is_accepted_and_a_forged_one_is_not(self) -> None:
        pay = Razorpay("rzp_test_x", "secret", "hook")
        good = hmac.new(b"secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
        assert pay.test_mode
        assert pay.payment_is_genuine("order_1", "pay_1", good)
        assert not pay.payment_is_genuine("order_1", "pay_2", good)

    def test_a_webhook_is_checked_against_its_own_secret(self) -> None:
        pay = Razorpay("rzp_test_x", "secret", "hook")
        body = b'{"event":"payment.captured"}'
        sig = hmac.new(b"hook", body, hashlib.sha256).hexdigest()
        assert pay.webhook_is_genuine(body, sig)
        assert not pay.webhook_is_genuine(body + b" ", sig)

    @pytest.mark.parametrize(
        ("secret", "signature", "reason"),
        [
            ("hook", "0" * 64, "signature mismatch"),
            ("hook", None, "no signature"),
            (None, "0" * 64, "no webhook secret set on this server"),
        ],
    )
    def test_a_rejected_webhook_says_why_in_the_log(
        self,
        secret: str | None,
        signature: str | None,
        reason: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from fastapi.testclient import TestClient
        from pydantic import SecretStr

        from app.main import create_app

        app = create_app()
        logging.getLogger().addHandler(caplog.handler)  # the app's logging set-up removed it
        settings = app.state.settings
        app.state.settings = settings.model_copy(update={"billing": settings.billing.model_copy(
            update={"razorpay_key_id": "rzp_test_x", "razorpay_key_secret": SecretStr("secret"),
                    "razorpay_webhook_secret": SecretStr(secret) if secret else None},
        )})  # fmt: skip
        headers = {"x-razorpay-event-id": "evt_42"}
        if signature is not None:
            headers["x-razorpay-signature"] = signature

        with caplog.at_level(logging.WARNING, logger="factify.api.orgs"):
            response = TestClient(app).post(
                "/v1/billing/razorpay/webhook", content=b'{"event":"order.paid"}', headers=headers
            )

        assert response.status_code == 400
        assert f"Razorpay webhook rejected: {reason}" in caplog.text
        assert "evt_42" in caplog.text and "0" * 64 not in caplog.text

    def test_a_captured_payment_names_its_order(self) -> None:
        event = {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_9", "order_id": "order_9"}}},
        }
        assert paid_order(event) == ("order_9", "pay_9")
        assert paid_order({"event": "payment.failed", "payload": {}}) is None


async def _person(database: object, email: str) -> str:
    user_id = str(uuid4())
    async with database.connection() as conn:  # type: ignore[attr-defined]
        await conn.execute("INSERT INTO app_user (id, email) VALUES (%s, %s)", (user_id, email))
    return user_id


async def _cleanup(database: object, org_id: str, users: list[str]) -> None:
    async with database.connection() as conn:  # type: ignore[attr-defined]
        await conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (org_id,))
        await conn.execute("DELETE FROM organisation WHERE id = %s", (org_id,))
        for u in users:
            await conn.execute("DELETE FROM app_user WHERE id = %s", (u,))


@requires_database
@pytest.mark.asyncio
class TestThePool:
    async def test_fifty_parallel_checks_against_ten_credits_run_exactly_ten(
        self, database: object
    ) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        owner = await _person(database, f"owner-{tag}@example.org")
        org = await store.create_org(user_id=owner, name=f"Test {tag}", billing_email=None)
        try:
            await store.add_credits(org["id"], 10, reason="grant", actor=owner, request_key="seed")
            payer = Payer(org_id=org["id"], user_id=owner, role="owner")

            async def attempt() -> bool:
                try:
                    hold = await store.hold(payer, 1)
                except ApiError as refused:
                    assert refused.error_code == "insufficient_credits"
                    return False
                await store.settle(hold)
                return True

            results = await asyncio.gather(*(attempt() for _ in range(50)))
            assert sum(results) == 10
            assert (await store.org(org["id"]))["balance"] == 0
        finally:
            await _cleanup(database, org["id"], [owner])

    async def test_limits_and_a_released_hold(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        owner = await _person(database, f"owner-{tag}@example.org")
        dev = await _person(database, f"dev-{tag}@example.org")
        org = await store.create_org(user_id=owner, name=f"Test {tag}", billing_email=None)
        try:
            await store.add_credits(org["id"], 100, reason="grant", actor=owner, request_key="s")
            _, token = await store.create_invite(
                org["id"], owner, email=f"dev-{tag}@example.org", role="developer",
                monthly_limit=3,
            )  # fmt: skip
            with pytest.raises(ApiError):
                await store.accept_invite(token, user_id=dev, email="someone-else@example.org")
            await store.accept_invite(token, user_id=dev, email=f"dev-{tag}@example.org")

            payer = Payer(org_id=org["id"], user_id=dev, role="developer")
            first = await store.hold(payer, 3)
            with pytest.raises(ApiError) as over:
                await store.hold(payer, 1)
            assert over.value.error_code == "member_limit_reached"
            # A failed check gives its credits back at once.
            await store.release(first)
            await store.settle(await store.hold(payer, 2))

            row, key = await store.create_key(org["id"], dev, name="ci", monthly_limit=0)
            keyed, _ = await store.authenticate_key(key, None)
            assert keyed.key_id == row["id"] and keyed.org_id == org["id"]
            with pytest.raises(ApiError) as capped:
                await store.hold(keyed, 1)
            assert capped.value.error_code in ("key_limit_reached", "member_limit_reached")

            await store.revoke_key(org["id"], row["id"], owner)
            with pytest.raises(ApiError) as revoked:
                await store.authenticate_key(key, None)
            assert revoked.value.error_code == "invalid_api_key"

            # Rotation: the old key keeps working for a day; the new one works now.
            row2, key2 = await store.create_key(org["id"], dev, name="app")
            _, new_key = await store.rotate_key(org["id"], row2["id"], dev)
            await store.authenticate_key(key2, None)
            await store.authenticate_key(new_key, None)

            # The last owner can't leave.
            with pytest.raises(ApiError) as last:
                await store.remove_member(org["id"], owner, owner)
            assert last.value.error_code == "last_owner"
            # A removed member's keys stop.
            await store.remove_member(org["id"], dev, owner)
            with pytest.raises(ApiError):
                await store.authenticate_key(new_key, None)

            usage = await store.usage(org["id"], days=30)
            assert sum(int(d["credits"]) for d in usage["by_day"]) == 2
        finally:
            await _cleanup(database, org["id"], [owner, dev])

    async def test_a_payment_is_credited_once(self, database: object) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        owner = await _person(database, f"owner-{tag}@example.org")
        org = await store.create_org(user_id=owner, name=f"Test {tag}", billing_email=None)
        try:
            await store.create_payment(
                org["id"], owner, order_id=f"order_{tag}", pack="starter", credits=1000,
                amount_paise=599900, test_mode=True,
            )  # fmt: skip
            await store.mark_paid(f"order_{tag}", "pay_1", owner)
            await store.mark_paid(f"order_{tag}", "pay_1", "razorpay")
            assert (await store.org(org["id"]))["balance"] == 1000
        finally:
            await _cleanup(database, org["id"], [owner])


@requires_database
@pytest.mark.asyncio
class TestPersonalBilling:
    async def test_a_personal_purchase_from_the_phone_is_credited_once(
        self, database: object
    ) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        user = await _person(database, f"buyer-{tag}@example.org")
        try:
            handoff, token = await store.create_handoff(user, None)
            opened = await store.use_handoff(token)
            assert opened["user_id"] == user
            # The link works once.
            with pytest.raises(ApiError) as again:
                await store.use_handoff(token)
            assert again.value.error_code == "handoff_expired"

            await store.create_payment(
                None, user, order_id=f"order_{tag}", pack="p50", credits=50,
                amount_paise=24900, test_mode=True, for_user=user, handoff_id=handoff["id"],
            )  # fmt: skip
            await store.mark_paid(f"order_{tag}", "pay_1", user)
            await store.mark_paid(f"order_{tag}", "pay_1", "razorpay")
            async with database.connection() as conn:  # type: ignore[attr-defined]
                cur = await conn.execute(
                    "SELECT COALESCE(SUM(delta), 0) AS b FROM credit_ledger WHERE user_id = %s",
                    (user,),
                )
                assert (await cur.fetchone())["b"] == 50
            state = await store.handoff(user, handoff["id"])
            assert state["status"] == "paid" and state["credits"] == 50
        finally:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                await conn.execute("DELETE FROM app_user WHERE id = %s", (user,))

    async def test_an_organisation_plan_is_granted_by_approving_a_request(
        self, database: object
    ) -> None:
        store = OrgStore(database)
        tag = uuid4().hex[:8]
        user = await _person(database, f"asker-{tag}@example.org")
        admin = await _person(database, f"admin-{tag}@example.org")
        org_id = None
        try:
            req = await store.create_org_request(user, {"org_name": f"Desk {tag}"})
            with pytest.raises(ApiError) as twice:
                await store.create_org_request(user, {"org_name": "Another"})
            assert twice.value.error_code == "request_pending"
            decided = await store.decide_org_request(
                req["id"], admin, approve=True, note="ok", grant_credits=500
            )
            org_id = decided["org_id"]
            assert (await store.member(org_id, user))["role"] == "owner"
            assert (await store.org(org_id))["balance"] == 500
            with pytest.raises(ApiError):
                await store.decide_org_request(req["id"], admin, approve=False, note=None)
        finally:
            async with database.connection() as conn:  # type: ignore[attr-defined]
                if org_id:
                    await conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (org_id,))
                    await conn.execute("DELETE FROM organisation WHERE id = %s", (org_id,))
                await conn.execute("DELETE FROM app_user WHERE id IN (%s, %s)", (user, admin))
