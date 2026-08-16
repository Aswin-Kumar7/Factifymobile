"""Shared fixtures.

Database tests are opt-in: they need a real Postgres with pgvector, which no
substitute provides — `bit(64)` Hamming indexes, `vector` columns and JSONB are not
things SQLite can pretend to do. Without a connection string they skip loudly rather
than silently passing against a fake.

    TEST_DATABASE_URL=postgresql://... uv run pytest -m db

Or set it in .env.test, which this file also reads.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import dotenv_values

from app.db.migrate import migrate
from app.db.pool import Database

# psycopg's async mode cannot run on Windows' default ProactorEventLoop. Production
# is Linux, where this is a no-op; without it no database test can run on a Windows
# development machine.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def _test_database_url() -> str | None:
    """The test connection string, from the environment or from `.env`.

    Deliberately **not** named with the ``FACIFY_`` prefix. That prefix is the
    application's config namespace and `Settings` declares it ``extra="forbid"``, so
    a typo in a real setting fails loudly instead of being ignored — a test-harness
    variable living there would force that guard to be weakened.

    It lives in ``.env.test`` rather than ``.env`` for the same reason: pydantic
    rejects every key in ``.env`` it does not recognise, test-only ones included.

    That file is read as a fallback because pydantic-settings parses dotenv files
    directly and never exports them to ``os.environ``, so a developer who has
    configured the project still has nothing here unless they separately export it.
    Falling back means database tests run for them instead of silently skipping —
    the failure mode worth avoiding, because a skipped database test looks exactly
    like a passing one in a summary line.
    """
    from_env = os.environ.get("TEST_DATABASE_URL")
    if from_env:
        return from_env

    dotenv = Path(__file__).resolve().parents[1] / ".env.test"
    if not dotenv.exists():
        return None

    return dotenv_values(dotenv).get("TEST_DATABASE_URL") or None


TEST_DATABASE_URL = _test_database_url()

requires_database = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="set TEST_DATABASE_URL (environment or .env) to run database tests",
)


@pytest_asyncio.fixture(scope="session")
async def database() -> AsyncIterator[Database]:
    """A migrated database for the test session."""
    assert TEST_DATABASE_URL is not None
    db = Database(TEST_DATABASE_URL, min_size=1, max_size=4)
    await db.open()
    async with db.connection() as conn:
        await migrate(conn)
    yield db
    await db.close()


@pytest_asyncio.fixture
async def conn(database: Database) -> AsyncIterator[object]:
    """A connection whose work is rolled back at the end of the test.

    Every test therefore starts from the same migrated, empty state without
    truncating tables between runs.
    """
    async with database.connection() as connection:
        transaction = connection.transaction(force_rollback=True)
        async with transaction:
            yield connection


# Model tests download weights and are opt-in for the same reason database tests are:
# nothing should silently pull hundreds of megabytes during an ordinary test run.
# `truststore` bridges the OS certificate store, which this network's TLS
# interception requires and a plain CI runner does not.
if os.environ.get("FACIFY_MODEL_TESTS") == "1":  # pragma: no cover - opt-in path
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
