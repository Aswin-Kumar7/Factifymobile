-- Why people use Factify (2026-09-30): four short questions asked once, after a new
-- account is made - who they are, where they meet things to check, what they want to
-- check, and how they heard of us. Every question can be skipped, and so can the
-- whole survey.
--
-- `survey_state` is what the app reads to decide whether to ask:
--   due        a new account that has not been asked yet
--   answered   answered (some questions may be blank)
--   skipped    the person chose not to answer
--   not_asked  the account existed before the survey; it is never asked
--
-- The answers are about the person, never about what they checked: nothing here
-- joins to a case, for the reason given in 0003.

SET LOCAL search_path TO facify, extensions, public;

-- Existing accounts take 'not_asked' from the first default; new ones are 'due'.
ALTER TABLE app_user
    ADD COLUMN survey_state text NOT NULL DEFAULT 'not_asked'
        CHECK (survey_state IN ('due', 'answered', 'skipped', 'not_asked')),
    ADD COLUMN survey       jsonb,
    ADD COLUMN survey_at    timestamptz;

ALTER TABLE app_user ALTER COLUMN survey_state SET DEFAULT 'due';
