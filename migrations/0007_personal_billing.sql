-- Buying credits as a person, organisation plans by request, and paying from the
-- phone in the browser (2026-10-01).
--
-- A payment is now for a person (user_id) or an organisation (org_id). A person's
-- purchase lands in their own ledger (credit_ledger, reason 'purchase').
--
-- payment_handoff: the app's way into the browser to pay, like Spotify's. The app
-- asks for one; the browser opens /pay with its token, which signs the person in
-- once (the token is single-use, lives 10 minutes, and only its SHA-256 is kept);
-- the app polls the handoff's status until the payment it led to is paid, failed or
-- cancelled. Every purchase gets a new handoff.
--
-- org_request: a person asks for an organisation plan; Factify's admin approves
-- (creating the organisation with them as owner) or rejects it.

SET LOCAL search_path TO facify, extensions, public;

ALTER TABLE credit_ledger DROP CONSTRAINT credit_ledger_reason_check;
ALTER TABLE credit_ledger ADD CONSTRAINT credit_ledger_reason_check
    CHECK (reason IN ('signup_grant', 'grant', 'check', 'deep_check', 'refund', 'purchase'));

ALTER TABLE auth_session DROP CONSTRAINT auth_session_method_check;
ALTER TABLE auth_session ADD CONSTRAINT auth_session_method_check
    CHECK (method IN ('password', 'google', 'handoff'));

CREATE TABLE payment_handoff (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    token_hash  text        NOT NULL UNIQUE,
    -- Which account the app wants to pay for: NULL is the person's own credits.
    org_id      uuid        REFERENCES organisation(id) ON DELETE CASCADE,
    status      text        NOT NULL DEFAULT 'waiting'
                CHECK (status IN ('waiting', 'opened', 'paid', 'failed', 'cancelled')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz,
    finished_at timestamptz
);

CREATE INDEX payment_handoff_by_user ON payment_handoff (user_id, created_at DESC);

ALTER TABLE payment ALTER COLUMN org_id DROP NOT NULL;
ALTER TABLE payment
    ADD COLUMN user_id    uuid REFERENCES app_user(id) ON DELETE CASCADE,
    ADD COLUMN handoff_id uuid REFERENCES payment_handoff(id) ON DELETE SET NULL,
    ADD CONSTRAINT payment_has_owner CHECK (org_id IS NOT NULL OR user_id IS NOT NULL);

CREATE INDEX payment_by_user ON payment (user_id, created_at DESC);

CREATE TABLE org_request (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    org_name         text        NOT NULL CHECK (length(org_name) BETWEEN 1 AND 80),
    billing_email    text,
    use_case         text,
    expected_checks  integer     CHECK (expected_checks >= 0),
    website          text,
    status           text        NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn')),
    decided_by       uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    decided_at       timestamptz,
    decision_note    text,
    org_id           uuid        REFERENCES organisation(id) ON DELETE SET NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX org_request_by_status ON org_request (status, created_at DESC);
-- One open request per person at a time.
CREATE UNIQUE INDEX org_request_one_pending ON org_request (user_id) WHERE status = 'pending';
