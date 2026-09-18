-- Result receipts (M42).
--
-- A receipt attests that a verdict was produced from a specific set of evidence. Its
-- value is entirely in being checkable *later*: the signature proves this service
-- issued it, and the evidence digest proves the evidence has not changed since. A
-- receipt that passes the first check and fails the second is the tampering case the
-- whole mechanism exists to surface, and it cannot be surfaced by a receipt that was
-- never written down.
--
-- Stored rather than recomputed on read. Re-signing whatever evidence happens to be
-- there now would produce a receipt that always verifies, which is a receipt that
-- attests to nothing.
--
-- One row per case. `id` is content-addressed by the issuer from the case and the
-- evidence digest, so re-issuing an unchanged case is idempotent and re-issuing a
-- changed one is a different receipt rather than a silent overwrite.

SET LOCAL search_path TO facify, extensions, public;

CREATE TABLE receipt (
    id                text        PRIMARY KEY,
    case_id           uuid        NOT NULL REFERENCES verification_case(id) ON DELETE CASCADE,
    evidence_digest   text        NOT NULL,
    signature         text        NOT NULL,
    issued_at         timestamptz NOT NULL,
    rule_version      text        NOT NULL,
    action            text        NOT NULL,
    evidence_count    integer     NOT NULL CHECK (evidence_count >= 0),
    receipt_version   text        NOT NULL
);

-- Receipts are looked up by case at least as often as by id: a client that kept a
-- case id and lost the receipt still has to be able to ask what was attested.
CREATE INDEX receipt_case_idx ON receipt (case_id, issued_at DESC);
