"""Migrations and connection setup: from an empty database, idempotent, atomic, constraints on."""

import json
import re
import sqlite3
from pathlib import Path

import pytest

from citetally import db

TABLES = {
    "schema_migrations", "categories", "vendors", "vendor_aliases", "documents", "pages",
    "extractions", "entries", "entry_lines", "evidence", "checks", "field_edits", "reviews",
    "exports", "export_items", "audit_events", "settings",
}  # fmt: skip
SEED_CODES = {
    "SUPPLIES", "FOOD", "CLEANING", "UTILITIES", "REPAIRS", "INSURANCE", "SOFTWARE",
    "PROFESSIONAL", "VEHICLE", "MARKETING", "OTHER",
}  # fmt: skip


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    return connection


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_migrating_an_empty_database_creates_every_table(conn: sqlite3.Connection) -> None:
    assert table_names(conn) == TABLES


def test_the_first_migration_is_recorded(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT version, name FROM schema_migrations").fetchall()
    assert [(r["version"], r["name"]) for r in rows] == [(1, "init")]


def test_migrating_again_applies_nothing_and_changes_nothing(conn: sqlite3.Connection) -> None:
    before = conn.execute("SELECT version, applied_at FROM schema_migrations").fetchall()
    assert db.migrate(conn) == []
    after = conn.execute("SELECT version, applied_at FROM schema_migrations").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_migrate_returns_the_versions_it_applied() -> None:
    connection = db.connect(":memory:")
    assert db.migrate(connection) == [1]


def test_foreign_keys_are_enforced(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO pages (document_id, page_number, image_path, width_px, height_px, "
            "read_method, word_count, words, text, created_at) "
            "VALUES (999, 1, 'x', 1, 1, 'ocr', 0, '[]', '', 'now')"
        )


def test_check_constraints_reject_unknown_enum_values(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO documents (original_filename, stored_path, file_sha256, mime_type, "
            "size_bytes, status, created_at, updated_at) "
            "VALUES ('a.pdf', 'p', 'h', 'application/pdf', 1, 'paid', 'now', 'now')"
        )


def test_file_databases_use_write_ahead_logging(tmp_path: Path) -> None:
    connection = db.connect(tmp_path / "t.db")
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def write_migrations(folder: Path, files: dict[str, str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, sql in files.items():
        (folder / name).write_text(sql, encoding="utf-8")
    return folder


CREATE_LOG = (
    "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
    "applied_at TEXT NOT NULL);\n"
)


def test_migrations_apply_in_numeric_order(tmp_path: Path) -> None:
    folder = write_migrations(
        tmp_path / "m",
        {
            "0002_second.sql": "CREATE TABLE b (id INTEGER);",
            "0001_first.sql": CREATE_LOG + "CREATE TABLE a (id INTEGER);",
        },
    )
    connection = db.connect(":memory:")
    assert db.migrate(connection, folder) == [1, 2]
    assert {"a", "b"} <= table_names(connection)


def test_a_failing_migration_rolls_back_completely(tmp_path: Path) -> None:
    folder = write_migrations(
        tmp_path / "m",
        {
            "0001_first.sql": CREATE_LOG + "CREATE TABLE a (id INTEGER);",
            "0002_broken.sql": "CREATE TABLE half_done (id INTEGER);\nCREATE TABLE a (id INTEGER);",
        },
    )
    connection = db.connect(":memory:")
    with pytest.raises(db.MigrationError, match="0002"):
        db.migrate(connection, folder)
    assert "half_done" not in table_names(connection)  # nothing from the failed file survives
    versions = [r["version"] for r in connection.execute("SELECT version FROM schema_migrations")]
    assert versions == [1]  # the earlier migration stays applied
    # Fixing the file and running again continues from where it stopped.
    (folder / "0002_broken.sql").write_text("CREATE TABLE b (id INTEGER);", encoding="utf-8")
    assert db.migrate(connection, folder) == [2]


def test_migration_files_must_be_numbered_without_gaps_or_duplicates(tmp_path: Path) -> None:
    connection = db.connect(":memory:")
    gap = write_migrations(
        tmp_path / "gap", {"0001_a.sql": CREATE_LOG, "0003_c.sql": "CREATE TABLE c (id INTEGER);"}
    )
    with pytest.raises(db.MigrationError, match="gap"):
        db.migrate(connection, gap)
    dup = write_migrations(
        tmp_path / "dup", {"0001_a.sql": CREATE_LOG, "0001_b.sql": "CREATE TABLE b (id INTEGER);"}
    )
    with pytest.raises(db.MigrationError, match="duplicate"):
        db.migrate(db.connect(":memory:"), dup)
    bad_name = write_migrations(tmp_path / "bad", {"init.sql": CREATE_LOG})
    with pytest.raises(db.MigrationError, match="name"):
        db.migrate(db.connect(":memory:"), bad_name)


def test_an_applied_migration_that_disappears_is_an_error(tmp_path: Path) -> None:
    folder = write_migrations(
        tmp_path / "m",
        {"0001_first.sql": CREATE_LOG, "0002_second.sql": "CREATE TABLE b (id INTEGER);"},
    )
    connection = db.connect(":memory:")
    db.migrate(connection, folder)
    (folder / "0002_second.sql").unlink()
    with pytest.raises(db.MigrationError, match="missing"):
        db.migrate(connection, folder)


def test_seed_categories_loads_the_chart_once(conn: sqlite3.Connection) -> None:
    assert db.seed_categories(conn) == len(SEED_CODES)
    rows = conn.execute("SELECT code, name, is_active FROM categories").fetchall()
    assert {r["code"] for r in rows} == SEED_CODES
    assert all(r["is_active"] == 1 and r["name"] for r in rows)
    assert db.seed_categories(conn) == 0  # loading again adds nothing


def test_seeding_never_overwrites_a_name_the_user_changed(conn: sqlite3.Connection) -> None:
    db.seed_categories(conn)
    conn.execute("UPDATE categories SET name = 'My supplies' WHERE code = 'SUPPLIES'")
    db.seed_categories(conn)
    name = conn.execute("SELECT name FROM categories WHERE code = 'SUPPLIES'").fetchone()["name"]
    assert name == "My supplies"


def test_seed_file_names_match_the_documented_chart() -> None:
    seed = json.loads(db.SEED_FILE.read_text(encoding="utf-8"))
    assert {c["code"] for c in seed} == SEED_CODES
    assert next(c["name"] for c in seed if c["code"] == "UTILITIES") == "Utilities"


def test_cli_migrates_and_seeds_the_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "data" / "citetally.db"
    monkeypatch.setenv("CITETALLY_DB_PATH", str(target))
    assert db.main(["migrate"]) == 0
    assert target.is_file()
    assert "Applied migration 1" in capsys.readouterr().out
    assert db.main(["migrate"]) == 0
    assert "up to date" in capsys.readouterr().out
    check = db.connect(target)
    assert check.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == len(SEED_CODES)


def test_cli_rejects_unknown_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        db.main(["explode"])


def test_timestamps_are_iso_utc_and_strictly_increasing() -> None:
    stamps = [db.now() for _ in range(200)]
    assert stamps == sorted(stamps) and len(set(stamps)) == 200
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", stamps[0])
