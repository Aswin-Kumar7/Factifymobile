-- Monthly plans (2026-10-01): a person is on Free, Plus or Pro; an organisation on
-- Team (per member), API (pay per check) or, as before, credit packs only.
--
-- Each plan gives a number of checks a calendar month (India time). A check is paid
-- from, in order: the plan's checks this month, then any credits the account already
-- has (bought packs, sign-up grants), then - only on a paid plan and only if the
-- owner turned it on - extra usage, billed at the end of the month up to a cap the
-- owner sets.
--
-- Every check is still one ledger row with its negative delta, so usage, limits and
-- statistics read the ledgers exactly as before. The new `source` column says what
-- paid for it; the credit balance counts only rows paid from credits (NULL is a row
-- from before plans: credits).
--
-- subscription: a Razorpay subscription for a person or an organisation.
-- razorpay_plan: Razorpay's plan id for each (plan, interval), made on first use.
-- usage_bill: a month's extra usage, sent as a Razorpay payment link.

SET LOCAL search_path TO facify, extensions, public;

ALTER TABLE app_user
    ADD COLUMN plan_interval      text CHECK (plan_interval IN ('month', 'year')),
    ADD COLUMN plan_renews_at     timestamptz,
    ADD COLUMN plan_cancel_at_end boolean NOT NULL DEFAULT false,
    ADD COLUMN extra_usage        boolean NOT NULL DEFAULT false,
    ADD COLUMN extra_cap_paise    integer CHECK (extra_cap_paise >= 0);

ALTER TABLE app_user ADD CONSTRAINT app_user_plan_check
    CHECK (plan IN ('free', 'plus', 'pro'));

ALTER TABLE organisation
    ADD COLUMN plan               text NOT NULL DEFAULT 'credits'
                                  CHECK (plan IN ('credits', 'team', 'api')),
    ADD COLUMN seats              integer NOT NULL DEFAULT 0 CHECK (seats >= 0),
    ADD COLUMN plan_interval      text CHECK (plan_interval IN ('month', 'year')),
    ADD COLUMN plan_renews_at     timestamptz,
    ADD COLUMN plan_cancel_at_end boolean NOT NULL DEFAULT false,
    ADD COLUMN extra_usage        boolean NOT NULL DEFAULT false,
    ADD COLUMN extra_cap_paise    integer CHECK (extra_cap_paise >= 0);

ALTER TABLE credit_ledger
    ADD COLUMN source text CHECK (source IN ('plan', 'credits', 'extra'));
ALTER TABLE org_ledger
    ADD COLUMN source text CHECK (source IN ('plan', 'credits', 'extra'));
ALTER TABLE credit_hold
    ADD COLUMN source text NOT NULL DEFAULT 'credits'
               CHECK (source IN ('plan', 'credits', 'extra'));

CREATE INDEX credit_ledger_month ON credit_ledger (user_id, created_at)
    WHERE source IN ('plan', 'extra');
CREATE INDEX org_ledger_month ON org_ledger (org_id, created_at)
    WHERE source IN ('plan', 'extra');

CREATE TABLE subscription (
    id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                   uuid        REFERENCES app_user(id) ON DELETE CASCADE,
    org_id                    uuid        REFERENCES organisation(id) ON DELETE CASCADE,
    plan                      text        NOT NULL CHECK (plan IN ('plus', 'pro', 'team')),
    interval                  text        NOT NULL CHECK (interval IN ('month', 'year')),
    seats                     integer     NOT NULL DEFAULT 1 CHECK (seats >= 1),
    amount_paise              integer     NOT NULL CHECK (amount_paise > 0),
    razorpay_subscription_id  text        UNIQUE,
    razorpay_plan_id          text,
    status                    text        NOT NULL DEFAULT 'created'
                              CHECK (status IN ('created', 'active', 'cancelling', 'cancelled',
                                                'halted', 'failed', 'replaced')),
    current_start             timestamptz,
    current_end               timestamptz,
    test_mode                 boolean     NOT NULL DEFAULT true,
    created_by                uuid        REFERENCES app_user(id) ON DELETE SET NULL,
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT subscription_has_owner CHECK ((user_id IS NULL) <> (org_id IS NULL))
);

CREATE INDEX subscription_by_user ON subscription (user_id, created_at DESC);
CREATE INDEX subscription_by_org ON subscription (org_id, created_at DESC);

CREATE TABLE razorpay_plan (
    key         text        PRIMARY KEY,
    plan_id     text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE usage_bill (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid        REFERENCES app_user(id) ON DELETE CASCADE,
    org_id           uuid        REFERENCES organisation(id) ON DELETE CASCADE,
    month            date        NOT NULL,
    checks           integer     NOT NULL CHECK (checks > 0),
    amount_paise     integer     NOT NULL CHECK (amount_paise > 0),
    payment_link_id  text        UNIQUE,
    short_url        text,
    status           text        NOT NULL DEFAULT 'created'
                     CHECK (status IN ('created', 'paid', 'cancelled', 'failed')),
    test_mode        boolean     NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    paid_at          timestamptz,
    CONSTRAINT usage_bill_has_owner CHECK ((user_id IS NULL) <> (org_id IS NULL))
);

CREATE UNIQUE INDEX usage_bill_user_month ON usage_bill (user_id, month) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX usage_bill_org_month ON usage_bill (org_id, month) WHERE org_id IS NOT NULL;
