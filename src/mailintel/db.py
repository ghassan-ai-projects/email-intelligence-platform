"""SQLite storage: connection setup, sqlite-vec loading, and schema migrations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

import sqlite_vec

from .db_schema import _SCHEMA, _SCHEMA_V2, _SCHEMA_V3, _SCHEMA_V4, _SCHEMA_V5, _SCHEMA_V6

SCHEMA_VERSION = 6


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    _migrate(conn)
    return conn


@contextmanager
def connection(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """Open and close a database connection for one application operation."""
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def import_contacts_json(conn: sqlite3.Connection, path: Path | str | None = None) -> int:
    """Import contacts from a JSON file into the contacts table.

    Defaults to ~/.mailintel/contacts.json. Returns the number of contacts
    inserted or updated. Malformed files or entries are skipped.
    """
    from .guardrail.contacts import ContactsDB

    default_path = Path.home() / ".mailintel" / "contacts.json"
    return ContactsDB(conn).import_json(path or default_path)


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    if version < 1:
        conn.executescript(_SCHEMA)
    if version < 2:
        conn.executescript(_SCHEMA_V2)
    if version < 3:
        conn.executescript(_SCHEMA_V3)
    if version < 4:
        conn.executescript(_SCHEMA_V4)
    if version < 5:
        conn.executescript(_SCHEMA_V5)
    if version < 6:
        conn.executescript(_SCHEMA_V6)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
