"""Shared fixtures.

Database tests are opt-in: they need a real Postgres with pgvector, which no
substitute provides — `bit(64)` Hamming indexes, `vector` columns and JSONB are not
things SQLite can pretend to do. Without a connection string they skip loudly rather
than silently passing against a fake.

    FACIFY_TEST_DATABASE_URL=postgresql://... uv run pytest -m db
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.db.migrate import migrate
from app.db.pool import Database

# psycopg's async mode cannot run on Windows' default ProactorEventLoop. Production
# is Linux, where this is a no-op; without it no database test can run on a Windows
# development machine.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_DATABASE_URL = os.environ.get("FACIFY_TEST_DATABASE_URL")

requires_database = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="set FACIFY_TEST_DATABASE_URL to run database tests",
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
