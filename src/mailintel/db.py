"""SQLite storage: connection setup, sqlite-vec loading, and schema migrations."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import sqlite_vec

from .db_schema import _SCHEMA, _SCHEMA_V2, _SCHEMA_V3, _SCHEMA_V4

SCHEMA_VERSION = 4


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


def import_contacts_json(conn: sqlite3.Connection, path: Path | str | None = None) -> int:
    """Import contacts from a JSON file into the contacts table.

    Defaults to ~/.mailintel/contacts.json. Returns the number of contacts
    inserted or updated. Malformed files or entries are skipped.
    """
    if path is None:
        path = Path.home() / ".mailintel" / "contacts.json"
    path = Path(path)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(data, dict):
        return 0
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for entry in data.get("contacts", []):
        if not isinstance(entry, dict):
            continue
        addr = str(entry.get("addr", "")).lower().strip()
        if not addr:
            continue
        existing = conn.execute("SELECT id FROM contacts WHERE addr = ?", (addr,)).fetchone()
        if existing:
            updates: list[str] = []
            params: list[str] = []
            for field in ("tier", "name", "notes"):
                val = entry.get(field)
                if val:
                    updates.append(f"{field} = ?")
                    params.append(str(val))
            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(str(existing["id"]))
                conn.execute(f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?", params)
        else:
            conn.execute(
                "INSERT OR IGNORE INTO contacts (addr, name, tier, notes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    addr,
                    str(entry.get("name", "")),
                    str(entry.get("tier", "unknown")),
                    str(entry.get("notes", "")),
                    now,
                    now,
                ),
            )
        count += 1
    conn.commit()
    return count


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
