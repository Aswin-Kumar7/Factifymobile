-- A plan bought from the phone (2026-10-01): the app opens the website through a
-- payment handoff (0007) to choose a plan; the subscription remembers that handoff,
-- so when its first payment goes through the app waiting on it is told "paid".

SET LOCAL search_path TO facify, extensions, public;

ALTER TABLE subscription
    ADD COLUMN handoff_id uuid REFERENCES payment_handoff(id) ON DELETE SET NULL;
