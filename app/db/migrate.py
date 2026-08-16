"""Forward-only migration runner (M03).

Numbered SQL files applied in order, each inside its own transaction, each recorded
once. There is no down path: a mistake is corrected by a new migration, never by
rewinding one that has already run somewhere.

Migration failure is a boot failure. A service that starts against a schema it does
not understand will write rows nobody can read back.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from psycopg import AsyncConnection, sql

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

# Facify owns a dedicated schema; see the header of 0001_initial.sql for why. The
# ledger lives there too, so a migrated database carries its own history rather than
# leaving it in a schema the platform manages.
#
# The schema name is composed with psycopg's identifier quoting rather than string
# interpolation. It is a constant today, but a query built by concatenation is a
# habit that outlives the constant that made it safe.
SCHEMA = "facify"
_SCHEMA_ID = sql.Identifier(SCHEMA)

_CREATE_SCHEMA = sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(_SCHEMA_ID)

_CREATE_LEDGER = sql.SQL("""
CREATE TABLE IF NOT EXISTS {}.schema_migration (
    version     TEXT PRIMARY KEY,
    name        TEXT        NOT NULL,
    checksum    TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
""").format(_SCHEMA_ID)

_SELECT_APPLIED = sql.SQL("SELECT version, checksum FROM {}.schema_migration").format(_SCHEMA_ID)

_RECORD_APPLIED = sql.SQL(
    "INSERT INTO {}.schema_migration (version, name, checksum) VALUES (%s, %s, %s)"
).format(_SCHEMA_ID)


class MigrationError(RuntimeError):
    """A migration could not be applied, or history diverged from the files."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def discover(directory: Path | None = None) -> list[Migration]:
    """Load migrations from disk in version order."""
    directory = directory or MIGRATIONS_DIR
    migrations: list[Migration] = []

    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise MigrationError(
                f"migration filename {path.name!r} must look like 0001_description.sql"
            )
        version, name = match.groups()
        migrations.append(Migration(version=version, name=name, sql=path.read_text("utf-8")))

    versions = [m.version for m in migrations]
    if len(set(versions)) != len(versions):
        raise MigrationError(f"duplicate migration versions: {versions}")

    return migrations


async def applied_versions(conn: AsyncConnection[dict[str, object]]) -> dict[str, str]:
    """Version -> checksum for everything already applied."""
    await conn.execute(_CREATE_SCHEMA)
    await conn.execute(_CREATE_LEDGER)
    result = await conn.execute(_SELECT_APPLIED)
    rows = await result.fetchall()
    return {str(row["version"]): str(row["checksum"]) for row in rows}


async def migrate(
    conn: AsyncConnection[dict[str, object]], directory: Path | None = None
) -> list[str]:
    """Apply every pending migration. Returns the versions applied.

    An already-applied migration whose file has since changed is an error, not a
    re-run: the database and the repository have diverged and only a human can say
    which is right.
    """
    migrations = discover(directory)
    already = await applied_versions(conn)

    for migration in migrations:
        recorded = already.get(migration.version)
        if recorded is not None and recorded != migration.checksum:
            raise MigrationError(
                f"migration {migration.version}_{migration.name} was applied with a "
                f"different checksum; forward-only history has diverged from the files"
            )

    pending = [m for m in migrations if m.version not in already]

    for migration in pending:
        async with conn.transaction():
            await conn.execute(migration.sql)
            await conn.execute(
                _RECORD_APPLIED,
                (migration.version, migration.name, migration.checksum),
            )

    return [m.version for m in pending]
