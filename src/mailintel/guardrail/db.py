"""Guardrail-specific database utilities: column migration and helper queries."""

from __future__ import annotations

import json
import sqlite3


def migrate_guardrail(conn: sqlite3.Connection) -> None:
    """Ensure the guardrail columns exist on the emails table.

    This is a no-op if the v4 schema migration in db.py has already run.
    It can be called independently as a safety net.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(emails)").fetchall()}
    cols = {
        "guardrail_score": "INTEGER DEFAULT 0",
        "guardrail_blocked": "INTEGER DEFAULT 0",
        "guardrail_warnings": "TEXT",
    }
    for col_name, col_type in cols.items():
        if col_name not in existing:
            conn.execute(f"ALTER TABLE emails ADD COLUMN {col_name} {col_type}")

    # Contacts table (idempotent).
    existing_tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "contacts" not in existing_tables:
        conn.executescript("""
            CREATE TABLE contacts (
                id         INTEGER PRIMARY KEY,
                addr       TEXT NOT NULL UNIQUE,
                name       TEXT NOT NULL DEFAULT '',
                tier       TEXT NOT NULL DEFAULT 'unknown',
                notes      TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE contact_interactions (
                id         INTEGER PRIMARY KEY,
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                email_id   INTEGER REFERENCES emails(id) ON DELETE SET NULL,
                direction  TEXT NOT NULL DEFAULT 'inbound',
                timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
                summary    TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX idx_contact_ints_contact
                ON contact_interactions(contact_id);
        """)

    conn.commit()


def store_guardrail_result(
    conn: sqlite3.Connection,
    email_id: int,
    risk_score: int,
    blocked: bool,
    warnings: list[str],
) -> None:
    """Write the guardrail scan result into the emails row."""
    conn.execute(
        "UPDATE emails SET guardrail_score = ?, guardrail_blocked = ?, guardrail_warnings = ? "
        "WHERE id = ?",
        (risk_score, int(blocked), json.dumps(warnings), email_id),
    )
    conn.commit()
