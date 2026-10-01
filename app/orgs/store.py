# ruff: noqa: S608
# (S608: the only interpolated SQL is fixed fragments and column names from allow-lists;
# every value is a bound parameter.)
"""Organisations, members, invites, API keys and the shared credit pool (0006).

All of it is decided here, on the server, from the database: the website only
shows what these answer. The pool's credits are held before a check and settled
after it (`hold` / `settle`), inside a transaction that locks the organisation's
row, so parallel requests can never spend more than the pool, a member's limit,
a key's limit or the organisation's monthly cap allows.

Plans (0008): an organisation on Team gets 300 checks a member each month; a check
is paid from those first, then from the pool's credits, then from extra usage (on
Team, if the owner turned it on; on API, always, up to the cap). Every check is a
ledger row as before; its `source` says what paid, and the credit balance counts
only rows paid from credits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.orgs import keys as keyfmt
from app.orgs import plans
from app.orgs.errors import ApiError, bad_request, forbidden, invalid_key, not_allowed, not_found

ROLES = ("owner", "developer", "member")
# Roles that may hold API keys.
KEY_ROLES = ("owner", "developer")
# A hold nobody settled (a crashed check) stops counting after this.
HOLD_MINUTES = 30
INVITE_DAYS = 21
# After a rotation the old key keeps working this long.
ROTATION_GRACE = timedelta(hours=24)

Row = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Payer:
    """Who pays for a check made for an organisation, and through which key."""

    org_id: str
    user_id: str
    role: str
    key_id: str | None = None


@dataclass(frozen=True, slots=True)
class Hold:
    id: str
    payer: Payer
    amount: int
    remaining: int
    source: str = "credits"


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError:
        raise not_found() from None


def _jsonable(row: Row | None) -> Row | None:
    if row is None:
        return None
    out: Row = {}
    for k, v in row.items():
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _rows(rows: list[Row]) -> list[Row]:
    return [r for r in (_jsonable(x) for x in rows) if r is not None]


_MONTH = "date_trunc('month', now())"
_OPEN_HOLD = "settled_at IS NULL AND released_at IS NULL AND expires_at > now()"
# A plan's month: the calendar month in India time (0008).
_PLAN_MONTH = "(date_trunc('month', now() AT TIME ZONE 'Asia/Kolkata') AT TIME ZONE 'Asia/Kolkata')"
_PLAN_MONTH_END = (
    "((date_trunc('month', now() AT TIME ZONE 'Asia/Kolkata') + interval '1 month')"
    " AT TIME ZONE 'Asia/Kolkata')"
)
# Ledger rows that move the credit balance: everything but checks a plan or extra
# usage paid for (NULL is a row from before plans).
_CREDITS = "COALESCE(l.source, 'credits') = 'credits'"


def org_month(row: Row, now: datetime) -> plans.Month:
    """An organisation's `plans.Month` from the row `OrgStore.hold` reads."""
    plan = str(row.get("plan") or "credits")
    renews = row.get("plan_renews_at")
    lapsed = plans.lapsed(renews, now, ending=bool(row.get("plan_cancel_at_end")))
    team = plan == "team" and not lapsed
    api = plan == "api"
    cap = row.get("extra_cap_paise")
    price = plans.API_CHECK_PAISE if api else plans.EXTRA_CHECK_PAISE
    return plans.Month(
        allowance=plans.TEAM.monthly_checks * int(row.get("seats") or 0) if team else 0,
        used=int(row.get("plan_used") or 0),
        balance=int(row.get("credits") or 0),
        paid=team or api,
        extra_enabled=api or bool(row.get("extra_usage")),
        extra_cap_paise=int(cap) if cap is not None else None,
        extra_used_paise=int(row.get("extra_checks") or 0) * price,
        extra_price_paise=price,
        extra_blocked=bool(row.get("extra_blocked")),
    )


class OrgStore:
    def __init__(self, database: Any) -> None:
        self._db = database

    # ---- helpers ----------------------------------------------------------------

    async def _one(self, conn: Any, sql: str, params: Any = ()) -> Row | None:
        cur = await conn.execute(sql, params)
        row: Row | None = await cur.fetchone()
        return row

    async def _all(self, conn: Any, sql: str, params: Any = ()) -> list[Row]:
        cur = await conn.execute(sql, params)
        return list(await cur.fetchall())

    async def audit(
        self,
        conn: Any,
        *,
        org_id: str | None,
        actor: str,
        action: str,
        target: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO audit_log (tenant_id, actor, action, target, detail)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (
                _uuid(org_id) if org_id else None,
                actor,
                action,
                target,
                json.dumps(detail or {}),
            ),
        )

    async def is_staff(self, user_id: str, email: str, staff_emails: tuple[str, ...]) -> bool:
        if email.lower() in {e.lower() for e in staff_emails}:
            return True
        async with self._db.connection() as conn:
            row = await self._one(
                conn, "SELECT is_staff FROM app_user WHERE id = %s", (_uuid(user_id),)
            )
        return bool(row and row["is_staff"])

    # ---- organisations -----------------------------------------------------------

    async def create_org(self, *, user_id: str, name: str, billing_email: str | None) -> Row:
        async with self._db.transaction() as conn:
            org = await self._one(
                conn,
                """
                INSERT INTO organisation (name, billing_email, created_by)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (name.strip(), billing_email, _uuid(user_id)),
            )
            assert org is not None
            await conn.execute(
                "INSERT INTO org_member (org_id, user_id, role) VALUES (%s, %s, 'owner')",
                (org["id"], _uuid(user_id)),
            )
            await self.audit(
                conn, org_id=str(org["id"]), actor=user_id, action="org.created",
                detail={"name": name.strip()},
            )  # fmt: skip
        return await self.org(str(org["id"]))

    async def my_orgs(self, user_id: str) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                f"""
                SELECT o.id, o.name, o.status, m.role, m.monthly_limit, m.status AS member_status,
                       COALESCE((SELECT SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                                    AND {_CREDITS}), 0) AS balance,
                       o.plan, o.seats,
                       COALESCE((SELECT -SUM(delta) FROM org_ledger l
                                  WHERE l.org_id = o.id AND l.user_id = m.user_id
                                    AND l.reason = 'check' AND l.created_at >= {_MONTH}), 0)
                           AS my_month_spend
                  FROM org_member m JOIN organisation o ON o.id = m.org_id
                 WHERE m.user_id = %s AND o.status <> 'closed'
                 ORDER BY o.created_at
                """,
                (_uuid(user_id),),
            )
        return _rows(rows)

    async def org(self, org_id: str) -> Row:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                f"""
                SELECT o.*,
                  COALESCE((SELECT SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                               AND {_CREDITS}), 0) AS balance,
                  COALESCE((SELECT SUM(amount) FROM credit_hold h
                             WHERE h.org_id = o.id AND {_OPEN_HOLD}), 0) AS held,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                               AND l.source = 'plan' AND created_at >= {_PLAN_MONTH}), 0)
                      AS plan_used,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                               AND l.source = 'extra' AND created_at >= {_PLAN_MONTH}), 0)
                      AS extra_checks,
                  {_PLAN_MONTH_END} AS plan_resets_at,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                               AND reason = 'check' AND created_at >= {_MONTH}), 0)
                      AS month_spend,
                  (SELECT COUNT(*) FROM org_member m WHERE m.org_id = o.id) AS members,
                  (SELECT COUNT(*) FROM api_key k WHERE k.org_id = o.id
                      AND k.revoked_at IS NULL) AS active_keys,
                  COALESCE((SELECT SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                               AND reason IN ('purchase', 'grant')), 0) AS credits_added,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                               AND reason = 'check'), 0) AS lifetime_spend,
                  COALESCE((SELECT COUNT(*) FROM org_ledger l WHERE l.org_id = o.id
                               AND reason = 'check'), 0) AS lifetime_checks,
                  COALESCE((SELECT SUM(amount_paise) FROM payment p WHERE p.org_id = o.id
                               AND p.status = 'paid'), 0) AS paid_paise,
                  (SELECT MAX(created_at) FROM org_ledger l WHERE l.org_id = o.id
                               AND reason = 'check') AS last_check_at
                  FROM organisation o WHERE o.id = %s
                """,
                (_uuid(org_id),),
            )
        if row is None:
            raise not_found("organisation not found")
        return _jsonable(row) or {}

    async def member(self, org_id: str, user_id: str) -> Row | None:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                SELECT m.*, o.status AS org_status FROM org_member m
                  JOIN organisation o ON o.id = m.org_id
                 WHERE m.org_id = %s AND m.user_id = %s
                """,
                (_uuid(org_id), _uuid(user_id)),
            )
        return _jsonable(row)

    async def update_org(self, org_id: str, actor: str, fields: dict[str, Any]) -> Row:
        allowed = {"name", "billing_email", "gst_number", "monthly_spend_limit", "shared_history"}
        changes = {k: v for k, v in fields.items() if k in allowed}
        if changes:
            sets = ", ".join(f"{k} = %s" for k in changes)
            async with self._db.transaction() as conn:
                await conn.execute(
                    f"UPDATE organisation SET {sets} WHERE id = %s",
                    (*changes.values(), _uuid(org_id)),
                )
                await self.audit(
                    conn, org_id=org_id, actor=actor, action="org.updated", detail=changes
                )
        return await self.org(org_id)

    async def close_org(self, org_id: str, actor: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE organisation SET status = 'closed' WHERE id = %s", (_uuid(org_id),)
            )
            await conn.execute(
                "UPDATE api_key SET revoked_at = now() WHERE org_id = %s AND revoked_at IS NULL",
                (_uuid(org_id),),
            )
            await self.audit(conn, org_id=org_id, actor=actor, action="org.closed")

    # ---- members -----------------------------------------------------------------

    async def members(self, org_id: str) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                f"""
                SELECT m.user_id, u.email, u.display_name AS name, m.role, m.monthly_limit,
                       m.status, m.joined_at,
                       COALESCE((SELECT -SUM(delta) FROM org_ledger l
                                  WHERE l.org_id = m.org_id AND l.user_id = m.user_id
                                    AND l.reason = 'check' AND l.created_at >= {_MONTH}), 0)
                           AS month_spend,
                       (SELECT COUNT(*) FROM api_key k WHERE k.org_id = m.org_id
                           AND k.created_by = m.user_id AND k.revoked_at IS NULL) AS keys,
                       COALESCE((SELECT -SUM(delta) FROM org_ledger l
                                  WHERE l.org_id = m.org_id AND l.user_id = m.user_id
                                    AND l.reason = 'check'), 0) AS lifetime_spend,
                       (SELECT MAX(created_at) FROM org_ledger l
                         WHERE l.org_id = m.org_id AND l.user_id = m.user_id
                           AND l.reason = 'check') AS last_active_at
                  FROM org_member m JOIN app_user u ON u.id = m.user_id
                 WHERE m.org_id = %s ORDER BY m.joined_at
                """,
                (_uuid(org_id),),
            )
        return _rows(rows)

    async def _owners(self, conn: Any, org_id: str) -> int:
        row = await self._one(
            conn,
            "SELECT COUNT(*) AS n FROM org_member WHERE org_id = %s AND role = 'owner'"
            " AND status = 'active'",
            (_uuid(org_id),),
        )
        return int(row["n"]) if row else 0

    async def update_member(
        self, org_id: str, user_id: str, actor: str, fields: dict[str, Any]
    ) -> None:
        changes = {k: v for k, v in fields.items() if k in {"role", "monthly_limit", "status"}}
        if "role" in changes and changes["role"] not in ROLES:
            raise bad_request("unknown role")
        if "status" in changes and changes["status"] not in ("active", "suspended"):
            raise bad_request("unknown status")
        if not changes:
            return
        async with self._db.transaction() as conn:
            current = await self._one(
                conn,
                "SELECT role, status FROM org_member WHERE org_id = %s AND user_id = %s FOR UPDATE",
                (_uuid(org_id), _uuid(user_id)),
            )
            if current is None:
                raise not_found("member not found")
            leaving_owner = current["role"] == "owner" and (
                changes.get("role", "owner") != "owner" or changes.get("status") == "suspended"
            )
            if leaving_owner and await self._owners(conn, org_id) <= 1:
                raise bad_request("an organisation needs at least one owner", "last_owner")
            sets = ", ".join(f"{k} = %s" for k in changes)
            await conn.execute(
                f"UPDATE org_member SET {sets} WHERE org_id = %s AND user_id = %s",
                (*changes.values(), _uuid(org_id), _uuid(user_id)),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="member.updated", target=user_id,
                detail=changes,
            )  # fmt: skip

    async def remove_member(self, org_id: str, user_id: str, actor: str) -> None:
        async with self._db.transaction() as conn:
            current = await self._one(
                conn,
                "SELECT role FROM org_member WHERE org_id = %s AND user_id = %s FOR UPDATE",
                (_uuid(org_id), _uuid(user_id)),
            )
            if current is None:
                raise not_found("member not found")
            if current["role"] == "owner" and await self._owners(conn, org_id) <= 1:
                raise bad_request("an organisation needs at least one owner", "last_owner")
            await conn.execute(
                "DELETE FROM org_member WHERE org_id = %s AND user_id = %s",
                (_uuid(org_id), _uuid(user_id)),
            )
            # Their keys stop with them (the plan's default).
            await conn.execute(
                """
                UPDATE api_key SET revoked_at = now()
                 WHERE org_id = %s AND created_by = %s AND revoked_at IS NULL
                """,
                (_uuid(org_id), _uuid(user_id)),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="member.removed", target=user_id
            )

    # ---- invites -----------------------------------------------------------------

    async def create_invite(
        self, org_id: str, actor: str, *, email: str, role: str, monthly_limit: int | None
    ) -> tuple[Row, str]:
        if role not in ROLES:
            raise bad_request("unknown role")
        token = keyfmt.new_token()
        async with self._db.transaction() as conn:
            row = await self._one(
                conn,
                """
                INSERT INTO org_invite (org_id, email, role, monthly_limit, token_hash,
                                        invited_by, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, email, role, monthly_limit, created_at, expires_at
                """,
                (
                    _uuid(org_id), email.strip().lower(), role, monthly_limit,
                    keyfmt.hash_token(token), _uuid(actor), _now() + timedelta(days=INVITE_DAYS),
                ),
            )  # fmt: skip
            await self.audit(
                conn, org_id=org_id, actor=actor, action="invite.created",
                target=email.strip().lower(), detail={"role": role},
            )  # fmt: skip
        return _jsonable(row) or {}, token

    async def invites(self, org_id: str) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT id, email, role, monthly_limit, created_at, expires_at
                  FROM org_invite
                 WHERE org_id = %s AND accepted_at IS NULL AND revoked_at IS NULL
                   AND expires_at > now()
                 ORDER BY created_at DESC
                """,
                (_uuid(org_id),),
            )
        return _rows(rows)

    async def revoke_invite(self, org_id: str, invite_id: str, actor: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE org_invite SET revoked_at = now() WHERE org_id = %s AND id = %s",
                (_uuid(org_id), _uuid(invite_id)),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="invite.revoked", target=invite_id
            )

    async def invite_by_token(self, token: str) -> Row:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                SELECT i.*, o.name AS org_name, i.expires_at <= now() AS expired
                  FROM org_invite i
                  JOIN organisation o ON o.id = i.org_id
                 WHERE i.token_hash = %s
                """,
                (keyfmt.hash_token(token),),
            )
        if row is None or row["revoked_at"] or row["expired"]:
            raise not_found("this invitation has expired or was withdrawn")
        return _jsonable(row) or {}

    async def accept_invite(self, token: str, *, user_id: str, email: str) -> Row:
        invite = await self.invite_by_token(token)
        if invite.get("accepted_at"):
            raise bad_request("this invitation was already used", "invite_used")
        if invite["email"] != email.strip().lower():
            raise forbidden(f"this invitation is for {invite['email']}; sign in with that email")
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO org_member (org_id, user_id, role, monthly_limit)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (org_id, user_id) DO UPDATE
                   SET role = EXCLUDED.role, monthly_limit = EXCLUDED.monthly_limit,
                       status = 'active'
                """,
                (_uuid(invite["org_id"]), _uuid(user_id), invite["role"], invite["monthly_limit"]),
            )
            await conn.execute(
                "UPDATE org_invite SET accepted_at = now() WHERE id = %s", (_uuid(invite["id"]),)
            )
            await self.audit(
                conn, org_id=invite["org_id"], actor=user_id, action="invite.accepted",
                target=email,
            )  # fmt: skip
        return invite

    # ---- API keys ----------------------------------------------------------------

    async def keys(self, org_id: str, *, created_by: str | None = None) -> list[Row]:
        where, params = "k.org_id = %s", [_uuid(org_id)]
        if created_by:
            where += " AND k.created_by = %s"
            params.append(_uuid(created_by))
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                f"""
                SELECT k.id, k.name, k.note, k.prefix, k.monthly_limit, k.ip_allowlist,
                       k.created_at, k.expires_at, k.last_used_at, k.revoked_at, k.replaced_by,
                       k.created_by, u.email AS created_by_email,
                       COALESCE((SELECT -SUM(delta) FROM org_ledger l
                                  WHERE l.api_key_id = k.id AND l.reason = 'check'
                                    AND l.created_at >= {_MONTH}), 0) AS month_spend
                  FROM api_key k LEFT JOIN app_user u ON u.id = k.created_by
                 WHERE {where}
                 ORDER BY k.revoked_at IS NOT NULL, k.created_at DESC
                """,
                tuple(params),
            )
        return _rows(rows)

    async def create_key(
        self,
        org_id: str,
        actor: str,
        *,
        name: str,
        note: str | None = None,
        monthly_limit: int | None = None,
        expires_days: int | None = None,
        ip_allowlist: list[str] | None = None,
        conn: Any = None,
    ) -> tuple[Row, str]:
        key = keyfmt.new_key()
        expires = _now() + timedelta(days=expires_days) if expires_days else None

        async def insert(c: Any) -> Row:
            row = await self._one(
                c,
                """
                INSERT INTO api_key (org_id, created_by, name, note, prefix, key_hash,
                                     monthly_limit, ip_allowlist, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, note, prefix, monthly_limit, ip_allowlist, created_at,
                          expires_at
                """,
                (
                    _uuid(org_id), _uuid(actor), name.strip(), note, keyfmt.shown_part(key),
                    keyfmt.hash_key(key), monthly_limit, list(ip_allowlist or []), expires,
                ),
            )  # fmt: skip
            assert row is not None
            await self.audit(
                c, org_id=org_id, actor=actor, action="key.created",
                target=str(row["id"]), detail={"name": name.strip()},
            )  # fmt: skip
            return row

        if conn is not None:
            row = await insert(conn)
        else:
            async with self._db.transaction() as c:
                row = await insert(c)
        return _jsonable(row) or {}, key

    async def key(self, org_id: str, key_id: str) -> Row:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                "SELECT * FROM api_key WHERE org_id = %s AND id = %s",
                (_uuid(org_id), _uuid(key_id)),
            )
        if row is None:
            raise not_found("key not found")
        return _jsonable(row) or {}

    async def update_key(
        self, org_id: str, key_id: str, actor: str, fields: dict[str, Any]
    ) -> None:
        changes = {
            k: v
            for k, v in fields.items()
            if k in {"name", "note", "monthly_limit", "ip_allowlist"}
        }
        if not changes:
            return
        sets = ", ".join(f"{k} = %s" for k in changes)
        async with self._db.transaction() as conn:
            await conn.execute(
                f"UPDATE api_key SET {sets} WHERE org_id = %s AND id = %s",
                (*changes.values(), _uuid(org_id), _uuid(key_id)),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="key.updated", target=key_id,
                detail={k: v for k, v in changes.items() if k != "ip_allowlist"},
            )  # fmt: skip

    async def revoke_key(self, org_id: str, key_id: str, actor: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE api_key SET revoked_at = now() WHERE org_id = %s AND id = %s"
                " AND revoked_at IS NULL",
                (_uuid(org_id), _uuid(key_id)),
            )
            await self.audit(conn, org_id=org_id, actor=actor, action="key.revoked", target=key_id)

    async def rotate_key(self, org_id: str, key_id: str, actor: str) -> tuple[Row, str]:
        old = await self.key(org_id, key_id)
        if old.get("revoked_at"):
            raise bad_request("a revoked key can't be rotated")
        async with self._db.transaction() as conn:
            row, key = await self.create_key(
                org_id, actor, name=old["name"], note=old.get("note"),
                monthly_limit=old.get("monthly_limit"), ip_allowlist=old.get("ip_allowlist"),
                conn=conn,
            )  # fmt: skip
            # The old key keeps working for the grace period, then stops.
            await conn.execute(
                "UPDATE api_key SET replaced_by = %s, revoked_at = %s WHERE id = %s",
                (_uuid(row["id"]), _now() + ROTATION_GRACE, _uuid(key_id)),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="key.rotated", target=key_id,
                detail={"new_key": row["id"]},
            )  # fmt: skip
        return row, key

    async def authenticate_key(self, key: str, client_ip: str | None) -> tuple[Payer, Row]:
        """The payer behind an API key, or an ApiError saying why there is none."""
        if not keyfmt.looks_valid(key):
            raise invalid_key()
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                SELECT k.id, k.org_id, k.created_by, k.ip_allowlist, k.expires_at, k.revoked_at,
                       k.last_used_at, o.status AS org_status, m.role, m.status AS member_status,
                       (k.revoked_at IS NOT NULL AND k.revoked_at <= now()) AS is_revoked,
                       (k.expires_at IS NOT NULL AND k.expires_at <= now()) AS is_expired,
                       (k.last_used_at IS NULL OR k.last_used_at < now() - interval '1 minute')
                           AS stale_use,
                       u.email, u.display_name, u.disabled
                  FROM api_key k
                  JOIN organisation o ON o.id = k.org_id
                  LEFT JOIN org_member m ON m.org_id = k.org_id AND m.user_id = k.created_by
                  LEFT JOIN app_user u ON u.id = k.created_by
                 WHERE k.key_hash = %s
                """,
                (keyfmt.hash_key(key),),
            )
            if row is None:
                raise invalid_key()
            # Compared in the database, on its clock: the server's may differ.
            if row["is_revoked"] or row["is_expired"]:
                raise invalid_key()
            if row["org_status"] != "active":
                raise not_allowed("this organisation is suspended")
            if row["disabled"] or row["member_status"] != "active":
                raise not_allowed("the member who created this key is suspended or has left")
            if row["role"] not in KEY_ROLES:
                raise not_allowed("the member who created this key may no longer use API keys")
            allow = list(row["ip_allowlist"] or [])
            if allow and (client_ip or "") not in allow:
                raise not_allowed("this key can't be used from this IP address")
            # Written at most once a minute per key, not on every call.
            if row["stale_use"]:
                await conn.execute(
                    "UPDATE api_key SET last_used_at = now() WHERE id = %s", (row["id"],)
                )
        payer = Payer(
            org_id=str(row["org_id"]), user_id=str(row["created_by"]), role=row["role"],
            key_id=str(row["id"]),
        )  # fmt: skip
        return payer, _jsonable(row) or {}

    # ---- the pool: hold, settle, release -----------------------------------------

    async def hold(self, payer: Payer, cost: int) -> Hold:
        org_id = _uuid(payer.org_id)
        user_id = _uuid(payer.user_id)
        key_id = _uuid(payer.key_id) if payer.key_id else None
        async with self._db.transaction() as conn:
            org = await self._one(
                conn,
                """
                SELECT status, monthly_spend_limit, plan, seats, plan_renews_at,
                       plan_cancel_at_end, extra_usage, extra_cap_paise
                  FROM organisation WHERE id = %s FOR UPDATE
                """,
                (org_id,),
            )
            if org is None:
                raise not_found("organisation not found")
            if org["status"] != "active":
                raise not_allowed("this organisation is suspended")
            member = await self._one(
                conn,
                "SELECT monthly_limit, status FROM org_member WHERE org_id = %s AND user_id = %s",
                (org_id, user_id),
            )
            if member is None or member["status"] != "active":
                raise not_allowed("you are not an active member of this organisation")
            sums = await self._one(
                conn,
                f"""
                SELECT
                  COALESCE((SELECT SUM(delta) FROM org_ledger l WHERE l.org_id = %(o)s
                             AND {_CREDITS}), 0) AS balance,
                  COALESCE((SELECT SUM(amount) FROM credit_hold
                             WHERE org_id = %(o)s AND {_OPEN_HOLD}), 0) AS held,
                  COALESCE((SELECT SUM(amount) FROM credit_hold
                             WHERE org_id = %(o)s AND source = 'credits' AND {_OPEN_HOLD}), 0)
                      AS held_credits,
                  COALESCE((SELECT SUM(amount) FROM credit_hold
                             WHERE org_id = %(o)s AND source = 'plan' AND {_OPEN_HOLD}), 0)
                      AS held_plan,
                  COALESCE((SELECT SUM(amount) FROM credit_hold
                             WHERE org_id = %(o)s AND source = 'extra' AND {_OPEN_HOLD}), 0)
                      AS held_extra,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger WHERE org_id = %(o)s
                             AND source = 'plan' AND created_at >= {_PLAN_MONTH}), 0) AS plan_used,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger WHERE org_id = %(o)s
                             AND source = 'extra' AND created_at >= {_PLAN_MONTH}), 0)
                      AS extra_checks,
                  EXISTS (SELECT 1 FROM usage_bill b WHERE b.org_id = %(o)s
                           AND b.status = 'created'
                           AND b.created_at < now() - make_interval(days => %(g)s))
                      AS extra_blocked,
                  COALESCE((SELECT SUM(amount) FROM credit_hold
                             WHERE org_id = %(o)s AND user_id = %(u)s AND {_OPEN_HOLD}), 0)
                      AS held_mine,
                  COALESCE((SELECT SUM(amount) FROM credit_hold
                             WHERE api_key_id = %(k)s AND {_OPEN_HOLD}), 0) AS held_key,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger WHERE org_id = %(o)s
                             AND reason = 'check' AND created_at >= {_MONTH}), 0) AS spent,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger WHERE org_id = %(o)s
                             AND user_id = %(u)s AND reason = 'check'
                             AND created_at >= {_MONTH}), 0) AS spent_mine,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger WHERE api_key_id = %(k)s
                             AND reason = 'check' AND created_at >= {_MONTH}), 0) AS spent_key,
                  (SELECT monthly_limit FROM api_key WHERE id = %(k)s) AS key_limit
                """,
                {"o": org_id, "u": user_id, "k": key_id, "g": plans.UNPAID_GRACE_DAYS},
            )
            assert sums is not None
            month = org_month(
                {
                    **org,
                    "plan_used": int(sums["plan_used"]) + int(sums["held_plan"]),
                    "extra_checks": int(sums["extra_checks"]) + int(sums["held_extra"]),
                    "credits": int(sums["balance"]) - int(sums["held_credits"]),
                    "extra_blocked": sums["extra_blocked"],
                },
                _now(),
            )
            source = plans.source_for(month, cost)
            available = plans.checks_left(month)
            if source is None:
                raise ApiError(
                    402, "insufficient_credits",
                    f"out of credits: this check costs {cost} and the organisation has "
                    f"{max(available, 0)} left",
                )  # fmt: skip
            cap = org["monthly_spend_limit"]
            if cap is not None and int(sums["spent"]) + int(sums["held"]) + cost > cap:
                raise ApiError(
                    402, "org_spend_limit_reached",
                    "the organisation's monthly spending limit has been reached",
                )  # fmt: skip
            limit = member["monthly_limit"]
            if (
                limit is not None
                and int(sums["spent_mine"]) + int(sums["held_mine"]) + cost > limit
            ):
                raise ApiError(
                    402, "member_limit_reached",
                    "your monthly credit limit in this organisation has been reached",
                )  # fmt: skip
            key_limit = sums["key_limit"]
            if (
                key_id is not None
                and key_limit is not None
                and int(sums["spent_key"]) + int(sums["held_key"]) + cost > key_limit
            ):
                raise ApiError(
                    402, "key_limit_reached", "this API key's monthly credit limit has been reached"
                )
            row = await self._one(
                conn,
                """
                INSERT INTO credit_hold (org_id, user_id, api_key_id, amount, expires_at, source)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    org_id, user_id, key_id, cost,
                    _now() + timedelta(minutes=HOLD_MINUTES), source,
                ),
            )  # fmt: skip
            assert row is not None
        remaining = max(available - cost, 0) if source != "extra" else available
        return Hold(id=str(row["id"]), payer=payer, amount=cost, remaining=remaining, source=source)

    async def settle(self, hold: Hold) -> None:
        async with self._db.transaction() as conn:
            row = await self._one(
                conn,
                """
                UPDATE credit_hold SET settled_at = now()
                 WHERE id = %s AND settled_at IS NULL AND released_at IS NULL
                RETURNING org_id, user_id, api_key_id, amount, source
                """,
                (_uuid(hold.id),),
            )
            if row is None:
                return
            await conn.execute(
                """
                INSERT INTO org_ledger (org_id, delta, reason, user_id, api_key_id,
                                        request_key, source)
                VALUES (%s, %s, 'check', %s, %s, %s, %s)
                ON CONFLICT (org_id, request_key) DO NOTHING
                """,
                (
                    row["org_id"],
                    -row["amount"],
                    row["user_id"],
                    row["api_key_id"],
                    f"hold:{hold.id}",
                    row["source"],
                ),
            )

    async def release(self, hold: Hold) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                "UPDATE credit_hold SET released_at = now() WHERE id = %s AND settled_at IS NULL",
                (_uuid(hold.id),),
            )

    async def add_credits(
        self,
        org_id: str,
        amount: int,
        *,
        reason: str,
        actor: str,
        request_key: str,
        note: str | None = None,
        conn: Any = None,
    ) -> bool:
        """Put credits in (or, negative, take them out of) the pool. Once per key."""

        async def write(c: Any) -> bool:
            row = await self._one(
                c,
                """
                INSERT INTO org_ledger (org_id, delta, reason, request_key, note)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (org_id, request_key) DO NOTHING RETURNING id
                """,
                (_uuid(org_id), amount, reason, request_key, note),
            )
            if row is not None:
                await self.audit(
                    c, org_id=org_id, actor=actor, action=f"credits.{reason}",
                    detail={"amount": amount, "note": note},
                )  # fmt: skip
            return row is not None

        if conn is not None:
            return await write(conn)
        async with self._db.transaction() as c:
            return await write(c)

    # ---- usage, audit, shared history ---------------------------------------------

    async def usage(self, org_id: str, *, days: int, user_id: str | None = None) -> Row:
        mine = " AND l.user_id = %(u)s" if user_id else ""
        params = {"o": _uuid(org_id), "d": days, "u": _uuid(user_id) if user_id else None}
        async with self._db.connection() as conn:
            by_day = await self._all(
                conn,
                f"""
                SELECT to_char(date_trunc('day', l.created_at), 'YYYY-MM-DD') AS day,
                       -SUM(l.delta) AS credits, COUNT(*) AS checks
                  FROM org_ledger l
                 WHERE l.org_id = %(o)s AND l.reason = 'check'
                   AND l.created_at >= now() - make_interval(days => %(d)s){mine}
                 GROUP BY 1 ORDER BY 1
                """,
                params,
            )
            by_member = await self._all(
                conn,
                f"""
                SELECT l.user_id, u.email, -SUM(l.delta) AS credits, COUNT(*) AS checks
                  FROM org_ledger l LEFT JOIN app_user u ON u.id = l.user_id
                 WHERE l.org_id = %(o)s AND l.reason = 'check'
                   AND l.created_at >= now() - make_interval(days => %(d)s){mine}
                 GROUP BY 1, 2 ORDER BY 3 DESC
                """,
                params,
            )
            by_key = await self._all(
                conn,
                f"""
                SELECT l.api_key_id AS key_id, k.name, k.prefix, -SUM(l.delta) AS credits,
                       COUNT(*) AS checks
                  FROM org_ledger l JOIN api_key k ON k.id = l.api_key_id
                 WHERE l.org_id = %(o)s AND l.reason = 'check'
                   AND l.created_at >= now() - make_interval(days => %(d)s){mine}
                 GROUP BY 1, 2, 3 ORDER BY 4 DESC
                """,
                params,
            )
            ledger = await self._all(
                conn,
                f"""
                SELECT l.created_at, l.delta, l.reason, l.note, u.email, k.name AS key_name
                  FROM org_ledger l LEFT JOIN app_user u ON u.id = l.user_id
                  LEFT JOIN api_key k ON k.id = l.api_key_id
                 WHERE l.org_id = %(o)s
                   AND l.created_at >= now() - make_interval(days => %(d)s){mine}
                 ORDER BY l.created_at DESC LIMIT 500
                """,
                params,
            )
        return {
            "by_day": _rows(by_day),
            "by_member": _rows(by_member),
            "by_key": _rows(by_key),
            "ledger": _rows(ledger),
        }

    async def audit_log(self, org_id: str, limit: int = 200) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT a.at, a.action, a.target, a.detail, u.email AS actor_email
                  FROM audit_log a LEFT JOIN app_user u ON u.id::text = a.actor
                 WHERE a.tenant_id = %s ORDER BY a.at DESC LIMIT %s
                """,
                (_uuid(org_id), limit),
            )
        return _rows(rows)

    async def record_check(
        self, payer: Payer, *, case_id: str, input_type: str | None, title: str | None,
        verdict: str | None,
    ) -> None:  # fmt: skip
        async with self._db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO org_check (org_id, user_id, api_key_id, case_id, input_type,
                                       title, verdict)
                SELECT %s, %s, %s, %s, %s, %s, %s
                 WHERE EXISTS (SELECT 1 FROM organisation WHERE id = %s AND shared_history)
                """,
                (
                    _uuid(payer.org_id), _uuid(payer.user_id),
                    _uuid(payer.key_id) if payer.key_id else None, _uuid(case_id),
                    input_type, (title or "")[:300] or None, verdict, _uuid(payer.org_id),
                ),
            )  # fmt: skip

    async def history(self, org_id: str, limit: int = 200) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT c.case_id, c.input_type, c.title, c.verdict, c.created_at,
                       u.email, k.name AS key_name
                  FROM org_check c LEFT JOIN app_user u ON u.id = c.user_id
                  LEFT JOIN api_key k ON k.id = c.api_key_id
                 WHERE c.org_id = %s ORDER BY c.created_at DESC LIMIT %s
                """,
                (_uuid(org_id), limit),
            )
        return _rows(rows)

    # ---- idempotency -------------------------------------------------------------

    async def replay(self, scope: str, key: str, fingerprint: str) -> tuple[int, Any] | None:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                SELECT fingerprint, status_code, body FROM idempotent_request
                 WHERE scope = %s AND idem_key = %s AND created_at > now() - interval '24 hours'
                """,
                (scope, key),
            )
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise ApiError(
                422, "idempotency_key_reused",
                "this Idempotency-Key was used with a different request",
            )  # fmt: skip
        return int(row["status_code"]), row["body"]

    async def remember(
        self, scope: str, key: str, fingerprint: str, status_code: int, body: Any
    ) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO idempotent_request (scope, idem_key, fingerprint, status_code, body)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (scope, idem_key) DO NOTHING
                """,
                (scope, key, fingerprint, status_code, json.dumps(body)),
            )

    # ---- domains (verification and JIT membership) --------------------------------

    async def domains(self, org_id: str) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn, "SELECT * FROM org_domain WHERE org_id = %s ORDER BY created_at",
                (_uuid(org_id),),
            )  # fmt: skip
        return _rows(rows)

    async def add_domain(self, org_id: str, domain: str, actor: str) -> Row:
        token = keyfmt.new_token()
        async with self._db.transaction() as conn:
            row = await self._one(
                conn,
                """
                INSERT INTO org_domain (org_id, domain, token) VALUES (%s, %s, %s)
                ON CONFLICT (org_id, domain) DO UPDATE SET domain = EXCLUDED.domain
                RETURNING *
                """,
                (_uuid(org_id), domain, token),
            )
            await self.audit(conn, org_id=org_id, actor=actor, action="domain.added", target=domain)
        return _jsonable(row) or {}

    async def mark_domain(
        self, org_id: str, domain: str, actor: str, fields: dict[str, Any]
    ) -> None:
        changes = {
            k: v for k, v in fields.items() if k in {"verified_at", "auto_join", "default_role"}
        }
        if not changes:
            return
        sets = ", ".join(f"{k} = %s" for k in changes)
        async with self._db.transaction() as conn:
            await conn.execute(
                f"UPDATE org_domain SET {sets} WHERE org_id = %s AND domain = %s",
                (*changes.values(), _uuid(org_id), domain),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="domain.updated", target=domain,
                detail={k: str(v) for k, v in changes.items()},
            )  # fmt: skip

    async def remove_domain(self, org_id: str, domain: str, actor: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "DELETE FROM org_domain WHERE org_id = %s AND domain = %s", (_uuid(org_id), domain)
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="domain.removed", target=domain
            )

    async def join_by_domain(self, user_id: str, email: str) -> None:
        """JIT: an email at a verified, auto-join domain joins that organisation."""
        domain = email.rsplit("@", 1)[-1].lower()
        async with self._db.transaction() as conn:
            rows = await self._all(
                conn,
                """
                INSERT INTO org_member (org_id, user_id, role)
                SELECT d.org_id, %s, d.default_role FROM org_domain d
                  JOIN organisation o ON o.id = d.org_id AND o.status = 'active'
                 WHERE d.domain = %s AND d.verified_at IS NOT NULL AND d.auto_join
                ON CONFLICT (org_id, user_id) DO NOTHING
                RETURNING org_id
                """,
                (_uuid(user_id), domain),
            )
            for r in rows:
                await self.audit(
                    conn, org_id=str(r["org_id"]), actor=user_id, action="member.joined_by_domain",
                    target=email,
                )  # fmt: skip

    # ---- payments ----------------------------------------------------------------

    async def create_payment(
        self, org_id: str | None, actor: str, *, order_id: str, pack: str, credits: int,
        amount_paise: int, test_mode: bool, for_user: str | None = None,
        handoff_id: str | None = None,
    ) -> None:  # fmt: skip
        """An order for an organisation's pool, or (`for_user`) a person's own credits."""
        async with self._db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO payment (org_id, user_id, order_id, pack, credits, amount_paise,
                                     test_mode, created_by, handoff_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    _uuid(org_id) if org_id else None, _uuid(for_user) if for_user else None,
                    order_id, pack, credits, amount_paise, test_mode, _uuid(actor),
                    _uuid(handoff_id) if handoff_id else None,
                ),
            )  # fmt: skip

    async def mark_paid(self, order_id: str, payment_id: str, actor: str) -> Row | None:
        """Credit a paid order - once, whichever of the app or the webhook says so first."""
        async with self._db.transaction() as conn:
            row = await self._one(
                conn, "SELECT * FROM payment WHERE order_id = %s FOR UPDATE", (order_id,)
            )
            if row is None:
                return None
            if row["status"] != "paid":
                await conn.execute(
                    """
                    UPDATE payment SET status = 'paid', payment_id = %s, paid_at = now()
                     WHERE order_id = %s
                    """,
                    (payment_id, order_id),
                )
                if row["org_id"] is not None:
                    await self.add_credits(
                        str(row["org_id"]), int(row["credits"]), reason="purchase",
                        actor=actor, request_key=f"payment:{order_id}",
                        note=f"{row['pack']} pack", conn=conn,
                    )  # fmt: skip
                else:
                    # A person's own credits: their ledger, keyed so it is added once.
                    await conn.execute(
                        """
                        INSERT INTO credit_ledger (user_id, delta, reason, request_key)
                        VALUES (%s, %s, 'purchase', %s)
                        ON CONFLICT (user_id, request_key) DO NOTHING
                        """,
                        (row["user_id"], int(row["credits"]), f"payment:{order_id}"),
                    )
                    await self.audit(
                        conn, org_id=None, actor=actor, action="credits.personal_purchase",
                        target=str(row["user_id"]), detail={"credits": int(row["credits"])},
                    )  # fmt: skip
                if row["handoff_id"] is not None:
                    await conn.execute(
                        "UPDATE payment_handoff SET status = 'paid', finished_at = now()"
                        " WHERE id = %s",
                        (row["handoff_id"],),
                    )
        return _jsonable(row)

    async def mark_failed(self, order_id: str) -> None:
        """A payment Razorpay says failed: the order, and the app waiting on it."""
        async with self._db.transaction() as conn:
            row = await self._one(
                conn,
                """
                UPDATE payment SET status = 'failed'
                 WHERE order_id = %s AND status = 'created'
                RETURNING handoff_id
                """,
                (order_id,),
            )
            if row and row["handoff_id"] is not None:
                await conn.execute(
                    "UPDATE payment_handoff SET status = 'failed', finished_at = now()"
                    " WHERE id = %s AND status IN ('waiting', 'opened')",
                    (row["handoff_id"],),
                )

    async def my_payments(self, user_id: str) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                "SELECT * FROM payment WHERE user_id = %s ORDER BY created_at DESC",
                (_uuid(user_id),),
            )
        return _rows(rows)

    async def my_payment(self, user_id: str, payment_ref: str) -> Row:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                SELECT p.*, u.email AS billing_email, u.display_name AS org_name,
                       NULL AS gst_number
                  FROM payment p JOIN app_user u ON u.id = p.user_id
                 WHERE p.user_id = %s AND p.id = %s
                """,
                (_uuid(user_id), _uuid(payment_ref)),
            )
        if row is None:
            raise not_found("payment not found")
        out = _jsonable(row) or {}
        out["org_name"] = out.get("org_name") or out.get("billing_email")
        return out

    # ---- paying from the phone (handoff) -------------------------------------------

    async def create_handoff(self, user_id: str, org_id: str | None) -> tuple[Row, str]:
        token = keyfmt.new_token()
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                INSERT INTO payment_handoff (user_id, org_id, token_hash, expires_at)
                VALUES (%s, %s, %s, now() + interval '10 minutes')
                RETURNING id, status, expires_at
                """,
                (_uuid(user_id), _uuid(org_id) if org_id else None, keyfmt.hash_token(token)),
            )
        return _jsonable(row) or {}, token

    async def use_handoff(self, token: str) -> Row:
        """The person a handoff token signs in - once, and only while it is fresh."""
        async with self._db.transaction() as conn:
            row = await self._one(
                conn,
                """
                UPDATE payment_handoff h SET used_at = now(), status = 'opened'
                  FROM app_user u
                 WHERE h.token_hash = %s AND u.id = h.user_id AND h.used_at IS NULL
                   AND h.expires_at > now() AND NOT u.disabled
                RETURNING h.id, h.user_id, h.org_id, u.email, u.display_name, u.avatar_url
                """,
                (keyfmt.hash_token(token),),
            )
        if row is None:
            raise ApiError(
                410, "handoff_expired",
                "this payment link has expired or was already used; start again from the app",
            )  # fmt: skip
        return _jsonable(row) or {}

    async def handoff(self, user_id: str, handoff_id: str) -> Row:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                SELECT h.id, h.status, h.org_id, h.created_at, h.expires_at, h.used_at,
                       h.finished_at,
                       (SELECT credits FROM payment p WHERE p.handoff_id = h.id
                          AND p.status = 'paid' ORDER BY paid_at DESC LIMIT 1) AS credits,
                       (h.used_at IS NULL AND h.expires_at <= now()) AS expired
                  FROM payment_handoff h WHERE h.id = %s AND h.user_id = %s
                """,
                (_uuid(handoff_id), _uuid(user_id)),
            )
        if row is None:
            raise not_found("payment not found")
        return _jsonable(row) or {}

    async def finish_handoff(self, user_id: str, handoff_id: str, status: str) -> None:
        if status not in ("cancelled", "failed"):
            raise bad_request("unknown status")
        async with self._db.connection() as conn:
            await conn.execute(
                """
                UPDATE payment_handoff SET status = %s, finished_at = now()
                 WHERE id = %s AND user_id = %s AND status IN ('waiting', 'opened')
                """,
                (status, _uuid(handoff_id), _uuid(user_id)),
            )

    # ---- organisation plans by request --------------------------------------------

    async def create_org_request(self, user_id: str, fields: dict[str, Any]) -> Row:
        async with self._db.transaction() as conn:
            existing = await self._one(
                conn,
                "SELECT id FROM org_request WHERE user_id = %s AND status = 'pending'",
                (_uuid(user_id),),
            )
            if existing is not None:
                raise bad_request(
                    "you already have a request waiting for review", "request_pending"
                )
            row = await self._one(
                conn,
                """
                INSERT INTO org_request (user_id, org_name, billing_email, use_case,
                                         expected_checks, website)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
                """,
                (
                    _uuid(user_id), fields["org_name"], fields.get("billing_email"),
                    fields.get("use_case"), fields.get("expected_checks"), fields.get("website"),
                ),
            )  # fmt: skip
            await self.audit(
                conn, org_id=None, actor=user_id, action="org_request.created",
                detail={"org_name": fields["org_name"]},
            )  # fmt: skip
        return _jsonable(row) or {}

    async def my_org_requests(self, user_id: str) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                "SELECT * FROM org_request WHERE user_id = %s ORDER BY created_at DESC",
                (_uuid(user_id),),
            )
        return _rows(rows)

    async def withdraw_org_request(self, user_id: str, request_id: str) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                """
                UPDATE org_request SET status = 'withdrawn', decided_at = now()
                 WHERE id = %s AND user_id = %s AND status = 'pending'
                """,
                (_uuid(request_id), _uuid(user_id)),
            )

    async def org_requests(self, status: str | None = None) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT r.*, u.email, u.display_name AS name, d.email AS decided_by_email,
                       COALESCE((SELECT SUM(delta) FROM credit_ledger c
                                  WHERE c.user_id = r.user_id
                                    AND COALESCE(c.source, 'credits') = 'credits'), 0)
                           AS personal_balance,
                       (SELECT COUNT(*) FROM credit_ledger c WHERE c.user_id = r.user_id
                          AND c.delta < 0) AS personal_checks
                  FROM org_request r JOIN app_user u ON u.id = r.user_id
                  LEFT JOIN app_user d ON d.id = r.decided_by
                 WHERE %s::text IS NULL OR r.status = %s
                 ORDER BY (r.status = 'pending') DESC, r.created_at DESC
                 LIMIT 300
                """,
                (status, status),
            )
        return _rows(rows)

    async def decide_org_request(
        self, request_id: str, actor: str, *, approve: bool, note: str | None,
        grant_credits: int = 0,
    ) -> Row:  # fmt: skip
        async with self._db.transaction() as conn:
            req = await self._one(
                conn, "SELECT * FROM org_request WHERE id = %s FOR UPDATE", (_uuid(request_id),)
            )
            if req is None:
                raise not_found("request not found")
            if req["status"] != "pending":
                raise bad_request("this request was already decided", "already_decided")
            org_id = None
            if approve:
                org = await self._one(
                    conn,
                    """
                    INSERT INTO organisation (name, billing_email, created_by)
                    VALUES (%s, %s, %s) RETURNING id
                    """,
                    (req["org_name"], req["billing_email"], req["user_id"]),
                )
                assert org is not None
                org_id = org["id"]
                await conn.execute(
                    "INSERT INTO org_member (org_id, user_id, role) VALUES (%s, %s, 'owner')",
                    (org_id, req["user_id"]),
                )
                await self.audit(
                    conn, org_id=str(org_id), actor=actor, action="org.created",
                    detail={"name": req["org_name"], "from_request": str(req["id"])},
                )  # fmt: skip
                if grant_credits > 0:
                    await self.add_credits(
                        str(org_id), grant_credits, reason="grant", actor=actor,
                        request_key=f"request:{req['id']}", note="Starting credits",
                        conn=conn,
                    )  # fmt: skip
            await conn.execute(
                """
                UPDATE org_request SET status = %s, decided_by = %s, decided_at = now(),
                       decision_note = %s, org_id = %s
                 WHERE id = %s
                """,
                (
                    "approved" if approve else "rejected", _uuid(actor), note, org_id,
                    req["id"],
                ),
            )  # fmt: skip
            await self.audit(
                conn, org_id=str(org_id) if org_id else None, actor=actor,
                action="admin.org_request_approved" if approve else "admin.org_request_rejected",
                target=str(req["user_id"]), detail={"org_name": req["org_name"], "note": note},
            )  # fmt: skip
        return {
            "status": "approved" if approve else "rejected",
            "org_id": str(org_id) if org_id else None,
        }

    async def payments(self, org_id: str) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                "SELECT * FROM payment WHERE org_id = %s ORDER BY created_at DESC",
                (_uuid(org_id),),
            )
        return _rows(rows)

    async def payment(self, org_id: str, payment_ref: str) -> Row:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                """
                SELECT p.*, o.name AS org_name, o.billing_email, o.gst_number
                  FROM payment p JOIN organisation o ON o.id = p.org_id
                 WHERE p.org_id = %s AND p.id = %s
                """,
                (_uuid(org_id), _uuid(payment_ref)),
            )
        if row is None:
            raise not_found("payment not found")
        return _jsonable(row) or {}

    # ---- Factify admin -------------------------------------------------------------

    async def admin_stats(self) -> Row:
        async with self._db.connection() as conn:
            totals = await self._one(
                conn,
                """
                SELECT
                  (SELECT COUNT(*) FROM app_user) AS users,
                  (SELECT COUNT(*) FROM app_user WHERE created_at > now() - interval '7 days')
                      AS users_7d,
                  (SELECT COUNT(*) FROM organisation WHERE status <> 'closed') AS orgs,
                  (SELECT COUNT(*) FROM api_key WHERE revoked_at IS NULL) AS active_keys,
                  (SELECT COUNT(*) FROM verification_case
                    WHERE created_at > now() - interval '24 hours') AS checks_24h,
                  (SELECT COUNT(*) FROM verification_case
                    WHERE created_at > now() - interval '30 days') AS checks_30d,
                  COALESCE((SELECT -SUM(delta) FROM credit_ledger WHERE delta < 0
                    AND created_at > now() - interval '30 days'), 0) AS personal_credits_30d,
                  COALESCE((SELECT -SUM(delta) FROM org_ledger WHERE reason = 'check'
                    AND created_at > now() - interval '30 days'), 0) AS org_credits_30d,
                  COALESCE((SELECT SUM(credits) FROM payment WHERE status = 'paid'), 0)
                      AS credits_sold,
                  COALESCE((SELECT SUM(amount_paise) FROM payment WHERE status = 'paid'), 0)
                  -- Plans whose payment went through (0008, 0010), and paid
                  -- extra-usage bills. A renewing subscription counts its first period.
                  + COALESCE((SELECT SUM(amount_paise) FROM subscription
                               WHERE current_start IS NOT NULL), 0)
                  + COALESCE((SELECT SUM(amount_paise) FROM usage_bill WHERE status = 'paid'), 0)
                      AS revenue_paise,
                  (SELECT COUNT(*) FROM subscription WHERE status IN ('active', 'cancelling'))
                      AS paid_plans
                """,
            )
            by_day = await self._all(
                conn,
                """
                SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                       COUNT(*) AS checks,
                       COUNT(*) FILTER (WHERE input_type = 'video') AS videos
                  FROM verification_case WHERE created_at > now() - interval '30 days'
                 GROUP BY 1 ORDER BY 1
                """,
            )
            providers = await self._all(
                conn,
                """
                SELECT provider, SUM(used) AS calls, MAX(cap) AS daily_cap FROM call_budget
                 WHERE day > current_date - 30 GROUP BY 1 ORDER BY 2 DESC
                """,
            )
            survey = await self._all(
                conn,
                """
                SELECT survey_state, survey->>'role' AS role, COUNT(*) AS n
                  FROM app_user GROUP BY 1, 2 ORDER BY 3 DESC
                """,
            )
        return {
            "totals": _jsonable(totals) or {},
            "by_day": _rows(by_day),
            "providers": _rows(providers),
            "survey": _rows(survey),
        }

    async def admin_orgs(self, query: str = "") -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT o.id, o.name, o.status, o.created_at, o.billing_email,
                  COALESCE((SELECT SUM(delta) FROM org_ledger l WHERE l.org_id = o.id
                             AND COALESCE(l.source, 'credits') = 'credits'), 0)
                      AS balance,
                  o.plan, o.seats,
                  (SELECT COUNT(*) FROM org_member m WHERE m.org_id = o.id) AS members,
                  (SELECT COUNT(*) FROM api_key k WHERE k.org_id = o.id
                      AND k.revoked_at IS NULL) AS active_keys
                  FROM organisation o
                 WHERE %s = '' OR o.name ILIKE %s OR o.billing_email ILIKE %s
                 ORDER BY o.created_at DESC LIMIT 200
                """,
                (query, f"%{query}%", f"%{query}%"),
            )
        return _rows(rows)

    async def set_org_status(self, org_id: str, status: str, actor: str, reason: str) -> None:
        if status not in ("active", "suspended"):
            raise bad_request("unknown status")
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE organisation SET status = %s WHERE id = %s", (status, _uuid(org_id))
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action=f"admin.org_{status}",
                detail={"reason": reason},
            )  # fmt: skip

    async def admin_users(self, query: str = "") -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT u.id, u.email, u.display_name AS name, u.created_at, u.last_seen_at,
                       u.is_staff, u.disabled, u.survey_state,
                       COALESCE((SELECT SUM(delta) FROM credit_ledger c WHERE c.user_id = u.id
                                  AND COALESCE(c.source, 'credits') = 'credits'), 0)
                           AS balance,
                       u.plan,
                       (SELECT string_agg(o.name, ', ') FROM org_member m
                          JOIN organisation o ON o.id = m.org_id WHERE m.user_id = u.id) AS orgs
                  FROM app_user u
                 WHERE %s = '' OR u.email ILIKE %s OR u.display_name ILIKE %s
                 ORDER BY u.created_at DESC LIMIT 200
                """,
                (query, f"%{query}%", f"%{query}%"),
            )
        return _rows(rows)

    async def grant_user(self, user_id: str, amount: int, actor: str, reason: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO credit_ledger (user_id, delta, reason, request_key)
                VALUES (%s, %s, 'grant', %s)
                """,
                (_uuid(user_id), amount, f"admin:{datetime.now(UTC).timestamp()}"),
            )
            await self.audit(
                conn, org_id=None, actor=actor, action="admin.user_credits", target=user_id,
                detail={"amount": amount, "reason": reason},
            )  # fmt: skip

    async def set_user_disabled(self, user_id: str, disabled: bool, actor: str) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE app_user SET disabled = %s WHERE id = %s", (disabled, _uuid(user_id))
            )
            if disabled:
                await conn.execute("DELETE FROM auth_session WHERE user_id = %s", (_uuid(user_id),))
            await self.audit(
                conn, org_id=None, actor=actor,
                action="admin.user_disabled" if disabled else "admin.user_enabled", target=user_id,
            )  # fmt: skip

    async def admin_keys(self, prefix: str = "") -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT k.id, k.org_id, o.name AS org_name, k.name, k.prefix, k.created_at,
                       k.last_used_at, k.revoked_at, u.email AS created_by_email
                  FROM api_key k JOIN organisation o ON o.id = k.org_id
                  LEFT JOIN app_user u ON u.id = k.created_by
                 WHERE %s = '' OR k.prefix LIKE %s OR k.name ILIKE %s
                 ORDER BY k.created_at DESC LIMIT 200
                """,
                (prefix, f"{prefix}%", f"%{prefix}%"),
            )
        return _rows(rows)

    async def admin_audit(self, limit: int = 300) -> list[Row]:
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                """
                SELECT a.at, a.action, a.target, a.detail, a.tenant_id AS org_id,
                       u.email AS actor_email
                  FROM audit_log a LEFT JOIN app_user u ON u.id::text = a.actor
                 WHERE a.action LIKE 'admin.%%' OR a.action LIKE 'credits.%%'
                    OR a.action LIKE 'org.%%'
                 ORDER BY a.at DESC LIMIT %s
                """,
                (limit,),
            )
        return _rows(rows)

    # ---- plans and subscriptions (0008) ---------------------------------------------

    async def razorpay_plan_id(self, key: str) -> str | None:
        async with self._db.connection() as conn:
            row = await self._one(conn, "SELECT plan_id FROM razorpay_plan WHERE key = %s", (key,))
        return str(row["plan_id"]) if row else None

    async def save_razorpay_plan(self, key: str, plan_id: str) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                "INSERT INTO razorpay_plan (key, plan_id) VALUES (%s, %s)"
                " ON CONFLICT (key) DO NOTHING",
                (key, plan_id),
            )

    async def create_subscription(
        self, *, user_id: str | None, org_id: str | None, plan: str, interval: str,
        seats: int, amount_paise: int, razorpay_subscription_id: str | None,
        razorpay_plan_id: str | None, test_mode: bool, actor: str,
        handoff_id: str | None = None, kind: str = "subscription", order_id: str | None = None,
    ) -> Row:  # fmt: skip
        """A plan bought, waiting for its first payment: a Razorpay subscription, or
        (`kind` "prepaid") one order paying for a single month or year (0010)."""
        async with self._db.transaction() as conn:
            row = await self._one(
                conn,
                """
                INSERT INTO subscription (user_id, org_id, plan, interval, seats, amount_paise,
                                          razorpay_subscription_id, razorpay_plan_id,
                                          test_mode, created_by, handoff_id, kind, order_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    _uuid(user_id) if user_id else None, _uuid(org_id) if org_id else None,
                    plan, interval, seats, amount_paise, razorpay_subscription_id,
                    razorpay_plan_id, test_mode, _uuid(actor),
                    _uuid(handoff_id) if handoff_id else None, kind, order_id,
                ),
            )  # fmt: skip
            await self.audit(
                conn, org_id=org_id, actor=actor, action="plan.subscribe_started",
                target=user_id, detail={"plan": plan, "interval": interval, "seats": seats},
            )  # fmt: skip
        return _jsonable(row) or {}

    async def subscription(self, razorpay_subscription_id: str) -> Row | None:
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                "SELECT * FROM subscription WHERE razorpay_subscription_id = %s",
                (razorpay_subscription_id,),
            )
        return _jsonable(row)

    async def current_subscription(
        self, *, user_id: str | None = None, org_id: str | None = None
    ) -> Row | None:
        """The owner's subscription that is paying now (or ending at its period's end)."""
        owner, value = ("user_id", user_id) if user_id else ("org_id", org_id)
        async with self._db.connection() as conn:
            row = await self._one(
                conn,
                f"""
                SELECT * FROM subscription
                 WHERE {owner} = %s AND status IN ('active', 'cancelling')
                 ORDER BY created_at DESC LIMIT 1
                """,
                (_uuid(str(value)),),
            )
        return _jsonable(row)

    async def activate_subscription(
        self, razorpay_subscription_id: str, *, current_start: datetime | None,
        current_end: datetime | None, actor: str,
    ) -> Row | None:  # fmt: skip
        """A subscription's payment went through: put its owner on the plan until
        `current_end`. Any other subscription the owner was paying for is marked
        replaced and named in the result (`replaced`) so it can be cancelled at
        Razorpay. One still waiting at checkout is left alone: it may yet be paid."""
        async with self._db.transaction() as conn:
            sub = await self._one(
                conn,
                "SELECT * FROM subscription WHERE razorpay_subscription_id = %s FOR UPDATE",
                (razorpay_subscription_id,),
            )
            if sub is None or sub["status"] in ("cancelled", "replaced", "failed"):
                return _jsonable(sub)
            await conn.execute(
                """
                UPDATE subscription
                   SET status = CASE WHEN status = 'cancelling' THEN 'cancelling' ELSE 'active' END,
                       current_start = COALESCE(%s, current_start),
                       current_end = COALESCE(%s, current_end), updated_at = now()
                 WHERE id = %s
                """,
                (current_start, current_end, sub["id"]),
            )
            renews = current_end or sub["current_end"]
            replaced = await self._put_on_plan(conn, sub, renews, actor)
        out = _jsonable(sub) or {}
        out["replaced"] = replaced
        return out

    async def _put_on_plan(
        self, conn: Any, sub: Row, renews: datetime | None, actor: str
    ) -> list[str]:
        """Inside the caller's transaction: the owner is on `sub`'s plan until `renews`;
        whatever else they were paying for ends (an auto-renewing one is named in the
        result, to be cancelled at Razorpay); the app that sent them is told."""
        owner, value = ("user_id", sub["user_id"]) if sub["user_id"] else ("org_id", sub["org_id"])
        # A plan paid a period at a time never renews by itself; nor does a cancelled one.
        ending = sub["kind"] == "prepaid" or sub["status"] == "cancelling"
        others = await self._all(
            conn,
            f"""
            UPDATE subscription
               SET status = CASE WHEN kind = 'prepaid' THEN 'ended' ELSE 'replaced' END,
                   updated_at = now()
             WHERE {owner} = %s AND id <> %s AND status IN ('active', 'cancelling')
            RETURNING kind, razorpay_subscription_id
            """,
            (value, sub["id"]),
        )
        if sub["user_id"]:
            await conn.execute(
                """
                UPDATE app_user
                   SET plan = %s, plan_interval = %s, plan_renews_at = %s,
                       plan_cancel_at_end = %s
                 WHERE id = %s
                """,
                (sub["plan"], sub["interval"], renews, ending, sub["user_id"]),
            )
        else:
            await conn.execute(
                """
                UPDATE organisation
                   SET plan = 'team', seats = %s, plan_interval = %s, plan_renews_at = %s,
                       plan_cancel_at_end = %s
                 WHERE id = %s
                """,
                (sub["seats"], sub["interval"], renews, ending, sub["org_id"]),
            )
        if sub.get("handoff_id") is not None:
            # The app that sent the person here is waiting: it is paid.
            await conn.execute(
                "UPDATE payment_handoff SET status = 'paid', finished_at = now()"
                " WHERE id = %s AND status IN ('waiting', 'opened')",
                (sub["handoff_id"],),
            )
        if sub["status"] == "created":
            await self.audit(
                conn, org_id=str(sub["org_id"]) if sub["org_id"] else None, actor=actor,
                action="plan.started", target=str(sub["user_id"]) if sub["user_id"] else None,
                detail={"plan": sub["plan"], "interval": sub["interval"], "seats": sub["seats"],
                        "kind": sub["kind"]},
            )  # fmt: skip
        return [
            str(o["razorpay_subscription_id"])
            for o in others
            if o["kind"] == "subscription" and o["razorpay_subscription_id"]
        ]

    async def activate_prepaid(self, order_id: str, payment_id: str, actor: str) -> Row | None:
        """A plan paid by one order (0010): the owner is on it for a month or a year -
        after the period already paid for, when it is the same plan again. Once,
        whichever of the website or the webhook says so first; None for an order
        that is not a plan's."""
        async with self._db.transaction() as conn:
            sub = await self._one(
                conn, "SELECT * FROM subscription WHERE order_id = %s FOR UPDATE", (order_id,)
            )
            if sub is None or sub["status"] != "created":
                out = _jsonable(sub)
                if out is not None:
                    out["replaced"] = []
                return out
            if sub["user_id"]:
                owner = await self._one(
                    conn,
                    "SELECT plan, plan_renews_at, 0 AS seats FROM app_user WHERE id = %s"
                    " FOR UPDATE",
                    (sub["user_id"],),
                )
                same = owner is not None and owner["plan"] == sub["plan"]
            else:
                owner = await self._one(
                    conn,
                    "SELECT plan, plan_renews_at, seats FROM organisation WHERE id = %s FOR UPDATE",
                    (sub["org_id"],),
                )
                same = (
                    owner is not None and owner["plan"] == "team" and owner["seats"] == sub["seats"]
                )
            renews_at = owner["plan_renews_at"] if owner else None
            start = renews_at if same and renews_at is not None and renews_at > _now() else _now()
            period = await self._one(
                conn,
                "SELECT %s::timestamptz + make_interval(months => %s) AS ends",
                (start, 1 if sub["interval"] == "month" else 12),
            )
            assert period is not None
            await conn.execute(
                """
                UPDATE subscription
                   SET status = 'active', current_start = %s, current_end = %s, payment_id = %s,
                       updated_at = now()
                 WHERE id = %s
                """,
                (start, period["ends"], payment_id, sub["id"]),
            )
            replaced = await self._put_on_plan(conn, sub, period["ends"], actor)
        out = _jsonable(sub) or {}
        out["current_end"] = period["ends"].isoformat()
        out["replaced"] = replaced
        return out

    async def subscription_by_order(self, order_id: str) -> Row | None:
        async with self._db.connection() as conn:
            row = await self._one(
                conn, "SELECT * FROM subscription WHERE order_id = %s", (order_id,)
            )
        return _jsonable(row)

    async def end_subscription(self, razorpay_subscription_id: str, status: str) -> Row | None:
        """Razorpay says the subscription is cancelling, cancelled, halted or failed.

        The owner keeps the plan until the period they paid for ends
        (`plans.effective_plan` reads `plan_renews_at`); a cancelling one is shown
        as ending.
        """
        async with self._db.transaction() as conn:
            sub = await self._one(
                conn,
                """
                UPDATE subscription SET status = %s, updated_at = now()
                 WHERE razorpay_subscription_id = %s AND status NOT IN ('replaced', 'cancelled')
                RETURNING *
                """,
                (status, razorpay_subscription_id),
            )
            if sub is None:
                return None
            ending = status == "cancelling"
            table, value = (
                ("app_user", sub["user_id"]) if sub["user_id"] else ("organisation", sub["org_id"])
            )
            await conn.execute(
                f"UPDATE {table} SET plan_cancel_at_end = %s WHERE id = %s",
                (ending or status in ("cancelled", "halted"), value),
            )
            await self.audit(
                conn, org_id=str(sub["org_id"]) if sub["org_id"] else None, actor="razorpay",
                action=f"plan.{status}",
                target=str(sub["user_id"]) if sub["user_id"] else None,
                detail={"plan": sub["plan"]},
            )  # fmt: skip
        return _jsonable(sub)

    async def subscriptions(
        self, *, user_id: str | None = None, org_id: str | None = None
    ) -> list[Row]:
        owner, value = ("user_id", user_id) if user_id else ("org_id", org_id)
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                f"""
                SELECT * FROM subscription WHERE {owner} = %s AND status <> 'created'
                 ORDER BY created_at DESC LIMIT 50
                """,
                (_uuid(str(value)),),
            )
        return _rows(rows)

    async def set_extra_usage(
        self, *, user_id: str | None = None, org_id: str | None = None, enabled: bool,
        cap_paise: int | None, actor: str,
    ) -> None:  # fmt: skip
        table, value = ("app_user", user_id) if user_id else ("organisation", org_id)
        async with self._db.transaction() as conn:
            await conn.execute(
                f"UPDATE {table} SET extra_usage = %s, extra_cap_paise = %s WHERE id = %s",
                (enabled, cap_paise, _uuid(str(value))),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="plan.extra_usage", target=user_id,
                detail={"enabled": enabled, "cap_paise": cap_paise},
            )  # fmt: skip

    async def set_org_plan(self, org_id: str, plan: str, actor: str) -> None:
        """Move an organisation to API (pay per check) or back to credit packs only."""
        async with self._db.transaction() as conn:
            await conn.execute(
                "UPDATE organisation SET plan = %s, extra_usage = %s WHERE id = %s",
                (plan, plan == "api", _uuid(org_id)),
            )
            await self.audit(
                conn, org_id=org_id, actor=actor, action="plan.changed", detail={"plan": plan}
            )

    # ---- extra usage bills (0008) ---------------------------------------------------

    async def extra_usage_to_bill(self, month: date) -> list[Row]:
        """Every person and organisation with extra usage in `month` (India time) and
        no bill for it yet: who, how many checks, and the price a check."""

        def bounds(t: str) -> str:
            return (
                f"{t}.created_at >= (%(m)s::timestamp AT TIME ZONE 'Asia/Kolkata')"
                f" AND {t}.created_at < ((%(m)s::timestamp + interval '1 month')"
                " AT TIME ZONE 'Asia/Kolkata')"
            )

        async with self._db.connection() as conn:
            people = await self._all(
                conn,
                f"""
                SELECT c.user_id, NULL::uuid AS org_id, u.email, -SUM(c.delta) AS checks
                  FROM credit_ledger c JOIN app_user u ON u.id = c.user_id
                 WHERE c.source = 'extra' AND {bounds("c")}
                   AND NOT EXISTS (SELECT 1 FROM usage_bill b
                                    WHERE b.user_id = c.user_id AND b.month = %(m)s)
                 GROUP BY c.user_id, u.email
                """,
                {"m": month},
            )
            orgs = await self._all(
                conn,
                f"""
                SELECT NULL::uuid AS user_id, l.org_id, o.billing_email AS email, o.plan,
                       -SUM(l.delta) AS checks
                  FROM org_ledger l JOIN organisation o ON o.id = l.org_id
                 WHERE l.source = 'extra' AND {bounds("l")}
                   AND NOT EXISTS (SELECT 1 FROM usage_bill b
                                    WHERE b.org_id = l.org_id AND b.month = %(m)s)
                 GROUP BY l.org_id, o.billing_email, o.plan
                """,
                {"m": month},
            )
        out = []
        for r in people + orgs:
            price = plans.API_CHECK_PAISE if r.get("plan") == "api" else plans.EXTRA_CHECK_PAISE
            out.append({**(_jsonable(r) or {}), "price_paise": price})
        return out

    async def create_usage_bill(
        self, *, user_id: str | None, org_id: str | None, month: date, checks: int,
        amount_paise: int, payment_link_id: str, short_url: str | None, test_mode: bool,
    ) -> None:  # fmt: skip
        async with self._db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO usage_bill (user_id, org_id, month, checks, amount_paise,
                                        payment_link_id, short_url, test_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    _uuid(user_id) if user_id else None, _uuid(org_id) if org_id else None,
                    month, checks, amount_paise, payment_link_id, short_url, test_mode,
                ),
            )  # fmt: skip

    async def mark_bill(self, payment_link_id: str, status: str) -> None:
        async with self._db.connection() as conn:
            await conn.execute(
                """
                UPDATE usage_bill
                   SET status = %s, paid_at = CASE WHEN %s = 'paid' THEN now() ELSE paid_at END
                 WHERE payment_link_id = %s AND status = 'created'
                """,
                (status, status, payment_link_id),
            )

    async def usage_bills(
        self, *, user_id: str | None = None, org_id: str | None = None
    ) -> list[Row]:
        owner, value = ("user_id", user_id) if user_id else ("org_id", org_id)
        async with self._db.connection() as conn:
            rows = await self._all(
                conn,
                f"SELECT * FROM usage_bill WHERE {owner} = %s ORDER BY month DESC LIMIT 24",
                (_uuid(str(value)),),
            )
        return _rows(rows)
