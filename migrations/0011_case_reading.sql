-- What was read from each input (2026-10-02, contract 1.8).
--
-- A result now says what Factify read from the input, part by part, and what it
-- could not read (`input_read`). A background check's full answer is held in memory
-- for 15 minutes; after that `/v1/cases/{id}` reads the case back from the ledger,
-- which holds the claims, their evidence and their verdicts, and none of this. The
-- same case opened from History after 15 minutes then lost the panel that says what
-- was read, the picture and video checks, the website card and the list of what was
-- skipped. A withheld answer lost the reason it was withheld.
--
-- One row per case, written once the answer is final, holding those parts of the
-- answer exactly as they were shown (the API's own JSON). The ledger's rows still
-- decide what they hold; this only fills in what they cannot.
--
-- Privacy: the payload holds the text read from the input in full - a post's text,
-- the words in its pictures, what is said in a video - so a stored answer can show
-- what it was made from. Like every other row of a case it joins to no person (see
-- 0003), and it goes when its case goes.

SET LOCAL search_path TO facify, extensions, public;

CREATE TABLE case_reading (
    case_id     uuid        PRIMARY KEY REFERENCES verification_case(id) ON DELETE CASCADE,
    payload     jsonb       NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at  timestamptz NOT NULL DEFAULT now()
);
