"""Database connection pool (M03).

A single async pool owned by the application lifespan. Repositories take a
connection; nothing in the codebase opens its own.

The pool is opened lazily and explicitly rather than at import, so `create_app()`
stays side-effect free and the pure-core tests never touch a socket.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

Row = dict[str, Any]

# Every connection resolves unqualified names against Factify's own schema first, so
# repositories never carry a schema prefix and can never accidentally read or write a
# platform-managed table in `public`.
# The database schema is still named `facify`, and deliberately.
#
# The product was renamed to Factify everywhere a person can see it. Renaming the
# schema is a different kind of change — an ALTER against a live database holding
# the corpus, the ledger and every issued receipt — so it is not bundled into a
# rename of display text. `migrations/0003_rename_schema.sql` does it in one
# statement whenever that is wanted; until it runs, this name must match what is
# actually there. It briefly did not, and every query failed with
# `relation "corpus_item" does not exist`.
SEARCH_PATH = "facify,extensions,public"


class Database:
    """Owns the connection pool for the process lifetime."""

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self._dsn = dsn
        self._pool = AsyncConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={
                "row_factory": dict_row,
                "options": f"-c search_path={SEARCH_PATH}",
            },
        )

    async def open(self) -> None:
        await self._pool.open(wait=True, timeout=10.0)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection[Row]]:
        """Check out a connection; the surrounding transaction commits on exit.

        The cast reflects the `dict_row` factory configured on the pool, which the
        pool's own type parameters do not carry.
        """
        async with self._pool.connection() as conn:
            yield cast(AsyncConnection[Row], conn)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection[Row]]:
        """Check out a connection inside an explicit transaction.

        Used where several repository writes must land together — a case and its
        content objects, or a verdict and its write-back.
        """
        async with self._pool.connection() as conn, conn.transaction():
            yield cast(AsyncConnection[Row], conn)
