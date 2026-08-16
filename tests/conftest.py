"""Shared fixtures.

Database tests are opt-in: they need a real Postgres with pgvector, which no
substitute provides — `bit(64)` Hamming indexes, `vector` columns and JSONB are not
things SQLite can pretend to do. Without a connection string they skip loudly rather
than silently passing against a fake.

    FACIFY_TEST_DATABASE_URL=postgresql://... uv run pytest -m db
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.db.migrate import migrate
from app.db.pool import Database

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
