-- Rename the database schema to match the product name.
--
-- The product is Factify. The schema is still `facify`, because renaming display
-- text and renaming a schema are different kinds of change: this one runs against
-- a live database holding the corpus, the ledger, every stored verdict and every
-- issued receipt, so it is kept as a deliberate step rather than folded into a
-- rename of strings.
--
-- It is a single statement, it is atomic, and it is reversible by swapping the two
-- names. No data moves and no table is rewritten — Postgres renames the namespace
-- and every object inside it comes along.
--
-- **Run it and the code change together.** `app/db/pool.py` sets `search_path` to
-- the schema name, and unqualified queries resolve through it; with one renamed and
-- not the other, every query fails with `relation "corpus_item" does not exist`.
-- After running this, change SEARCH_PATH in `app/db/pool.py` to
-- `factify,extensions,public`, SCHEMA in `app/db/migrate.py` to "factify", and the
-- six `FROM facify.<table>` references in `app/sources/corpus.py` and
-- `app/orchestration/media.py`.
--
--     psql "$FACTIFY_DATABASE_URL" -f migrations/manual/rename_schema.sql
--
-- It lives in `manual/` on purpose. The runner applies every numbered file in
-- `migrations/` in order, so a numbered copy here would rename the live schema the
-- next time anyone migrated — without the four code changes that must land with it.
--
-- Receipts are unaffected: they are signed over evidence values, not over the
-- schema those values are stored in.

BEGIN;

ALTER SCHEMA facify RENAME TO factify;

COMMIT;

-- To undo:
--
--     ALTER SCHEMA factify RENAME TO facify;
