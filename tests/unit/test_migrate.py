"""M03 — migration discovery and the forward-only guarantee.

These need no database: they exercise the file contract and the divergence check,
which is where the runner can go wrong silently.
"""

from pathlib import Path

import pytest

from app.db.migrate import MIGRATIONS_DIR, MigrationError, discover

pytestmark = pytest.mark.unit


class TestDiscovery:
    def test_finds_the_initial_migration(self) -> None:
        migrations = discover()

        assert [m.version for m in migrations][:1] == ["0001"]
        assert migrations[0].name == "initial"

    def test_migrations_are_returned_in_version_order(self, tmp_path: Path) -> None:
        (tmp_path / "0003_third.sql").write_text("SELECT 3;", encoding="utf-8")
        (tmp_path / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
        (tmp_path / "0002_second.sql").write_text("SELECT 2;", encoding="utf-8")

        assert [m.version for m in discover(tmp_path)] == ["0001", "0002", "0003"]

    def test_badly_named_file_is_rejected(self, tmp_path: Path) -> None:
        """A file that does not declare its version cannot be ordered."""
        (tmp_path / "add_some_table.sql").write_text("SELECT 1;", encoding="utf-8")

        with pytest.raises(MigrationError, match="must look like"):
            discover(tmp_path)

    def test_duplicate_versions_are_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "0001_one.sql").write_text("SELECT 1;", encoding="utf-8")
        (tmp_path / "0001_two.sql").write_text("SELECT 2;", encoding="utf-8")

        with pytest.raises(MigrationError, match="duplicate migration versions"):
            discover(tmp_path)


class TestChecksums:
    def test_checksum_changes_when_the_file_changes(self, tmp_path: Path) -> None:
        """This is what makes an edited, already-applied migration detectable."""
        path = tmp_path / "0001_initial.sql"

        path.write_text("SELECT 1;", encoding="utf-8")
        before = discover(tmp_path)[0].checksum

        path.write_text("SELECT 2;", encoding="utf-8")
        after = discover(tmp_path)[0].checksum

        assert before != after


class TestInitialSchema:
    """The structural commitments that must not be deferred to a later migration."""

    def _sql(self) -> str:
        return (MIGRATIONS_DIR / "0001_initial.sql").read_text(encoding="utf-8")

    def test_write_back_tables_exist_from_the_first_migration(self) -> None:
        """If these arrive later, the compounding loop is a promise, not a property."""
        sql = self._sql()

        for table in ("media_fingerprint", "claim_occurrence", "origin_cluster"):
            assert f"CREATE TABLE {table}" in sql

    def test_observation_is_separate_from_evidence(self) -> None:
        sql = self._sql()

        assert "CREATE TABLE observation" in sql
        assert "trust_state" in sql

    def test_advisory_is_a_separate_table_from_evidence(self) -> None:
        """Tier E has its own table because it is a different type (invariant 1)."""
        sql = self._sql()

        assert "CREATE TABLE advisory" in sql
        assert "CREATE TABLE evidence" in sql

    def test_evidence_requires_citation_snapshot_excerpt_and_anchor(self) -> None:
        """Invariant 4, enforced by the schema rather than by convention."""
        sql = self._sql()
        evidence_block = sql.split("CREATE TABLE evidence")[1].split("CREATE INDEX")[0]

        for column in ("citation_url", "snapshot_id", "source_excerpt", "source_anchor"):
            assert f"{column}" in evidence_block
            line = next(ln for ln in evidence_block.splitlines() if ln.strip().startswith(column))
            assert "NOT NULL" in line, f"{column} must be NOT NULL"

    def test_feed_run_is_unique_per_window(self) -> None:
        """The idempotency lock: a duplicated trigger is a provable no-op."""
        assert "UNIQUE (feed_id, window_start)" in self._sql()

    def test_call_budget_cannot_exceed_its_cap(self) -> None:
        assert "budget_never_exceeds_cap" in self._sql()

    def test_tenant_and_provider_version_columns_are_present(self) -> None:
        """Present but unused, so later evolution needs no migration surgery."""
        sql = self._sql()

        assert "tenant_id" in sql
        assert "provider_version" in sql
