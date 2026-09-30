-- Organisations (2026-09-30, docs/website-dashboard-plan.md): a paying owner, members
-- who check from one shared credit pool within their own limits, API keys for the
-- check endpoints, Razorpay payments, and staff (Factify's own admins).
--
-- The pool is its own ledger (`org_ledger`), separate from each person's free credits
-- (`credit_ledger`, 0003). Like that ledger it records that a check happened, who ran
-- it and through which key - never what was checked. The one exception is
-- `org_check`, a shared history an owner may switch on (`shared_history`), stated in
-- the privacy policy.
--
-- Credits are held before a check (`credit_hold`) and settled after, inside a
-- transaction that locks the organisation row: fifty parallel API calls against a
-- pool of ten run exactly ten.

SET LOCAL search_path TO facify, extensions, public;

ALTER TABLE app_user
    ADD COLUMN is_staff boolean NOT NULL DEFAULT false,
    ADD COLUMN disabled boolean NOT NULL DEFAULT false;

CREATE TABLE organisation (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 text        NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    billing_email        text,
    gst_number           text,
    status               text        NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'suspended', 'closed')),
    -- Credits per calendar month for the whole organisation; NULL is no cap.
    monthly_spend_limit  integer     CHECK (monthly_spend_limit >= 0),
    -- Opt-in: keep a shared history of the organisation's checks on the server.
    shared_history       boolean     NOT NULL DEFAULT false,
    created_by           uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE org_member (
    org_id         uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    user_id        uuid        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    role           text        NOT NULL CHECK (role IN ('owner', 'developer', 'member')),
    -- Credits per calendar month; NULL is no limit beyond the pool.
    monthly_limit  integer     CHECK (monthly_limit >= 0),
    status         text        NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'suspended')),
    joined_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);

CREATE INDEX org_member_by_user ON org_member (user_id);

CREATE TABLE org_invite (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    email          text        NOT NULL,
    role           text        NOT NULL CHECK (role IN ('owner', 'developer', 'member')),
    monthly_limit  integer     CHECK (monthly_limit >= 0),
    -- Only the SHA-256 of the link's token.
    token_hash     text        NOT NULL UNIQUE,
    invited_by     uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz NOT NULL,
    accepted_at    timestamptz,
    revoked_at     timestamptz
);

CREATE INDEX org_invite_by_org ON org_invite (org_id);

CREATE TABLE api_key (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    created_by     uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    name           text        NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
    note           text,
    -- The first characters, shown so a key can be recognised; never the whole key.
    prefix         text        NOT NULL,
    -- SHA-256 of the whole key. The key itself is shown once and never stored.
    key_hash       text        NOT NULL UNIQUE,
    monthly_limit  integer     CHECK (monthly_limit >= 0),
    ip_allowlist   text[]      NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz,
    last_used_at   timestamptz,
    revoked_at     timestamptz,
    -- Rotation: the key that replaced this one, which keeps working meanwhile.
    replaced_by    uuid        REFERENCES api_key(id) ON DELETE SET NULL
);

CREATE INDEX api_key_by_org ON api_key (org_id);
CREATE INDEX api_key_by_prefix ON api_key (prefix);

CREATE TABLE org_ledger (
    id           bigserial   PRIMARY KEY,
    org_id       uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    delta        integer     NOT NULL CHECK (delta <> 0),
    reason       text        NOT NULL
                 CHECK (reason IN ('purchase', 'grant', 'check', 'refund', 'adjustment')),
    user_id      uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    api_key_id   uuid        REFERENCES api_key(id) ON DELETE SET NULL,
    request_key  text        NOT NULL,
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, request_key)
);

CREATE INDEX org_ledger_by_org ON org_ledger (org_id, created_at DESC);

CREATE TABLE credit_hold (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    user_id      uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    api_key_id   uuid        REFERENCES api_key(id) ON DELETE SET NULL,
    amount       integer     NOT NULL CHECK (amount > 0),
    created_at   timestamptz NOT NULL DEFAULT now(),
    -- A hold nobody settled (a crashed check) stops counting after this.
    expires_at   timestamptz NOT NULL,
    settled_at   timestamptz,
    released_at  timestamptz
);

CREATE INDEX credit_hold_open ON credit_hold (org_id) WHERE settled_at IS NULL AND released_at IS NULL;

CREATE TABLE payment (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    provider             text        NOT NULL DEFAULT 'razorpay',
    order_id             text        NOT NULL UNIQUE,
    payment_id           text        UNIQUE,
    pack                 text        NOT NULL,
    credits              integer     NOT NULL CHECK (credits > 0),
    amount_paise         integer     NOT NULL CHECK (amount_paise > 0),
    currency             text        NOT NULL DEFAULT 'INR',
    status               text        NOT NULL DEFAULT 'created'
                         CHECK (status IN ('created', 'paid', 'failed')),
    test_mode            boolean     NOT NULL DEFAULT true,
    created_by           uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    paid_at              timestamptz
);

CREATE INDEX payment_by_org ON payment (org_id, created_at DESC);

-- Domains an organisation has proved it owns (a DNS TXT record). With auto_join,
-- anyone signing in with an email at the domain joins as a member (JIT).
CREATE TABLE org_domain (
    org_id        uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    domain        text        NOT NULL,
    token         text        NOT NULL,
    verified_at   timestamptz,
    auto_join     boolean     NOT NULL DEFAULT false,
    default_role  text        NOT NULL DEFAULT 'member'
                  CHECK (default_role IN ('developer', 'member')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, domain)
);

CREATE UNIQUE INDEX org_domain_verified ON org_domain (domain) WHERE verified_at IS NOT NULL;

-- A POST retried with the same Idempotency-Key gets the first answer, uncharged.
CREATE TABLE idempotent_request (
    scope        text        NOT NULL,
    idem_key     text        NOT NULL,
    fingerprint  text        NOT NULL,
    status_code  integer     NOT NULL,
    body         jsonb       NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, idem_key)
);

-- Opt-in shared history (organisation.shared_history): which checks were run.
CREATE TABLE org_check (
    id           bigserial   PRIMARY KEY,
    org_id       uuid        NOT NULL REFERENCES organisation(id) ON DELETE CASCADE,
    user_id      uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    api_key_id   uuid        REFERENCES api_key(id) ON DELETE SET NULL,
    case_id      uuid        NOT NULL,
    input_type   text,
    title        text,
    verdict      text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX org_check_by_org ON org_check (org_id, created_at DESC);
