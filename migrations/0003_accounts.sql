-- Accounts and credits (2026-09-26).
--
-- A person signs in (Supabase Auth: an emailed code, or Google) and has a profile and a
-- credit balance. Limits on checking belong to people, decided on the server; this is
-- where that decision reads from. Until plans exist nothing is refused — usage is
-- recorded, not capped.
--
-- `app_user.id` is the Supabase Auth user id. It is not a foreign key to
-- `auth.users`: that schema belongs to the platform, and this one should migrate on any
-- Postgres.
--
-- The ledger records THAT a check happened and when, never WHAT was checked. There is
-- deliberately no case id and no content here: joining a person to the messages they
-- were suspicious of would build exactly the record the app promises not to keep.
-- `request_key` makes each charge idempotent within a request and links to nothing.

SET LOCAL search_path TO facify, extensions, public;

CREATE TABLE app_user (
    id            uuid        PRIMARY KEY,
    email         text        NOT NULL,
    display_name  text,
    avatar_url    text,
    plan          text        NOT NULL DEFAULT 'free',
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE credit_ledger (
    id           bigserial   PRIMARY KEY,
    user_id      uuid        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    delta        integer     NOT NULL CHECK (delta <> 0),
    reason       text        NOT NULL
                 CHECK (reason IN ('signup_grant', 'grant', 'check', 'deep_check', 'refund')),
    request_key  text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, request_key)
);

CREATE INDEX credit_ledger_by_user ON credit_ledger (user_id, created_at DESC);
