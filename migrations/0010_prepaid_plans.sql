-- Plans paid a period at a time (2026-10-01). Where Razorpay's subscriptions are not
-- available on the account, a plan is bought as one payment for a month or a year
-- (a Razorpay order, like a credit pack) and renewed by paying again; buying the
-- same plan again adds the new period after the one already paid for. Auto-renewing
-- subscriptions stay as they were (kind 'subscription').

SET LOCAL search_path TO facify, extensions, public;

ALTER TABLE subscription
    ADD COLUMN kind       text NOT NULL DEFAULT 'subscription'
                          CHECK (kind IN ('subscription', 'prepaid')),
    ADD COLUMN order_id   text UNIQUE,
    ADD COLUMN payment_id text;

ALTER TABLE subscription DROP CONSTRAINT subscription_status_check;
ALTER TABLE subscription ADD CONSTRAINT subscription_status_check
    CHECK (status IN ('created', 'active', 'cancelling', 'cancelled', 'halted', 'failed',
                      'replaced', 'ended'));
