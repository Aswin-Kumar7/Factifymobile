-- Factify's own sign-in: an email and password, or Google, and the sessions they open.
--
-- Accounts are compulsory, and sign-in no longer depends on a third-party auth
-- service being configured. A person is still an `app_user` row (0003), so credits
-- and the profile work unchanged; this adds how they prove who they are.
--
-- Passwords are never stored: only a salted scrypt hash. Sessions are never stored
-- either: only the SHA-256 of the token the app holds, so a copy of this table
-- cannot be replayed as anyone's session.

SET LOCAL search_path TO facify, extensions, public;

CREATE TABLE user_login (
    user_id        uuid        PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
    email          text        NOT NULL,
    -- NULL for an account made with Google that has never set a password.
    password_hash  text,
    -- Google's stable id for the person ("sub"), once they have used Google.
    google_sub     text        UNIQUE,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- One account per email address, whatever its case.
CREATE UNIQUE INDEX user_login_email ON user_login (lower(email));

CREATE TABLE auth_session (
    token_hash  text        PRIMARY KEY,
    user_id     uuid        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    method      text        NOT NULL CHECK (method IN ('password', 'google')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);

CREATE INDEX auth_session_by_user ON auth_session (user_id);
