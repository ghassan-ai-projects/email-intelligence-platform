"""Guardrail-specific database utilities: column migration and helper queries."""

from __future__ import annotations

import json
import sqlite3


def migrate_guardrail(conn: sqlite3.Connection) -> None:
    """Validate that the canonical database migration owns guardrail schema."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(emails)").fetchall()}
    required_columns = {
        "guardrail_score",
        "guardrail_blocked",
        "guardrail_warnings",
        "guardrail_status",
    }
    existing_tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    required_tables = {"contacts", "contact_interactions"}
    if not required_columns <= existing or not required_tables <= existing_tables:
        raise RuntimeError(
            "guardrail schema is not migrated; open the database through mailintel.db.connect()"
        )


def store_guardrail_result(
    conn: sqlite3.Connection,
    email_id: int,
    risk_score: int,
    blocked: bool,
    warnings: list[str],
) -> None:
    """Write the guardrail scan result into the emails row."""
    conn.execute(
        "UPDATE emails SET guardrail_score = ?, guardrail_blocked = ?, guardrail_warnings = ?, "
        "guardrail_status = ? "
        "WHERE id = ?",
        (risk_score, int(blocked), json.dumps(warnings), "blocked" if blocked else "clean", email_id),
    )


def store_guardrail_failure(conn: sqlite3.Connection, email_id: int, reason: str) -> None:
    """Persist an explicit fail-closed state when scanning cannot complete."""
    conn.execute(
        "UPDATE emails SET guardrail_score = 0, guardrail_blocked = 1, "
        "guardrail_warnings = ?, guardrail_status = 'unknown' WHERE id = ?",
        (json.dumps([f"guardrail scan failed: {reason[:120]}"]), email_id),
    )
