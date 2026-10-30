"""SQLite connection, numbered SQL migrations and seed data. See docs/BACKEND_SCHEMA.md section 6.

  python -m citetally.db migrate     apply pending migrations and load the seed categories

Connections run in autocommit mode with foreign keys on and WAL for file databases. Code that
needs several writes to succeed or fail together uses `transaction(conn)`.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from citetally.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
SEED_FILE = REPO_ROOT / "db" / "seed" / "categories.json"
_MIGRATION_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationError(Exception):
    """A migration file is malformed, missing, or failed to apply."""


_last_tick = datetime.min.replace(tzinfo=UTC)


def now() -> str:
    """The current time as an ISO 8601 UTC string, to the millisecond.

    Strictly increasing within a process, so rows written one after the other always sort in the
    order they were written (the review queue and the "edits since the last review" rule need it).
    """
    global _last_tick
    tick = datetime.now(UTC)
    tick = tick.replace(microsecond=tick.microsecond // 1000 * 1000)
    if tick <= _last_tick:
        tick = _last_tick + timedelta(milliseconds=1)
    _last_tick = tick
    return tick.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if str(path) != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """All the writes inside succeed together or none of them do."""
    nested = connection.in_transaction
    savepoint = "citetally_nested"
    connection.execute(f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.execute(f"ROLLBACK TO {savepoint}" if nested else "ROLLBACK")
        if nested:
            connection.execute(f"RELEASE {savepoint}")
        raise
    connection.execute(f"RELEASE {savepoint}" if nested else "COMMIT")


def _statements(sql: str) -> Iterator[str]:
    """Split a script into complete statements, ignoring chunks that are only comments."""
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if any(
                not part.strip().startswith("--") for part in statement.splitlines() if part.strip()
            ):
                yield statement
    if buffer.strip() and any(
        not part.strip().startswith("--") for part in buffer.splitlines() if part.strip()
    ):
        yield buffer.strip()


def _discover(folder: Path) -> dict[int, tuple[str, Path]]:
    found: dict[int, tuple[str, Path]] = {}
    for path in sorted(folder.glob("*.sql")):
        match = _MIGRATION_NAME.match(path.name)
        if match is None:
            raise MigrationError(f"Migration file name must look like 0001_name.sql: {path.name}")
        version = int(match.group(1))
        if version in found:
            raise MigrationError(f"Two migration files share version {version} (duplicate).")
        found[version] = (match.group(2), path)
    for expected, actual in enumerate(sorted(found), start=1):
        if actual != expected:
            raise MigrationError(f"Migration numbers have a gap: version {expected} is missing.")
    return found


def _applied(connection: sqlite3.Connection) -> set[int]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if exists is None:
        return set()
    return {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}


def migrate(connection: sqlite3.Connection, folder: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply pending migrations in order, each in its own transaction. Returns the versions."""
    available = _discover(folder)
    applied = _applied(connection)
    missing = applied - set(available)
    if missing:
        raise MigrationError(f"Applied migration(s) {sorted(missing)} are missing from {folder}.")
    done: list[int] = []
    for version in sorted(set(available) - applied):
        name, path = available[version]
        try:
            with transaction(connection):
                for statement in _statements(path.read_text(encoding="utf-8")):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, now()),
                )
        except sqlite3.Error as error:
            raise MigrationError(f"Migration {version:04d}_{name} failed: {error}") from error
        done.append(version)
    return done


def seed_categories(connection: sqlite3.Connection, path: Path = SEED_FILE) -> int:
    """Add the seed categories that are missing. Never changes one that already exists."""
    categories = json.loads(path.read_text(encoding="utf-8"))
    before = connection.total_changes
    with transaction(connection):
        for category in categories:
            connection.execute(
                "INSERT OR IGNORE INTO categories (code, name, created_at) VALUES (?, ?, ?)",
                (category["code"], category["name"], now()),
            )
    return connection.total_changes - before


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m citetally.db")
    parser.add_argument("command", choices=["migrate"], help="apply migrations and seed data")
    parser.parse_args(argv)

    path = Settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(path)
    applied = migrate(connection)
    seeded = seed_categories(connection)
    names = {
        row["version"]: row["name"] for row in connection.execute("SELECT * FROM schema_migrations")
    }
    for version in applied:
        print(f"Applied migration {version} ({names[version]})")
    if not applied:
        print(f"Database is up to date ({len(names)} migrations)")
    if seeded:
        print(f"Added {seeded} seed categories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
