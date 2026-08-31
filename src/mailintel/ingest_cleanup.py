"""Cleanup and thread maintenance for Maildir ingestion."""

from __future__ import annotations

import sqlite3
from contextlib import suppress
from typing import TYPE_CHECKING

from .events import emit
from .threading_ import refresh_thread_stats

if TYPE_CHECKING:
    from .ingest import IngestStats


def remove_missing_files(
    conn: sqlite3.Connection,
    known: dict[tuple[str, str], tuple[str, int]],
    seen: set[tuple[str, str]],
    touched_threads: set[int],
    stats: IngestStats,
) -> None:
    """Remove vanished Maildir mappings and emails with no remaining copies."""
    for key, (_, email_id) in known.items():
        if key in seen:
            continue
        conn.execute("DELETE FROM sync_state WHERE folder = ? AND uniq = ?", key)
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM sync_state WHERE email_id = ?", (email_id,)
        ).fetchone()["n"]
        if remaining == 0:
            _delete_email(conn, email_id, touched_threads, stats)


def _delete_email(
    conn: sqlite3.Connection,
    email_id: int,
    touched_threads: set[int],
    stats: IngestStats,
) -> None:
    row = conn.execute("SELECT thread_id, subject FROM emails WHERE id = ?", (email_id,)).fetchone()
    if row:
        touched_threads.add(row["thread_id"])
        emit(
            conn,
            "email_deleted",
            email_id,
            {"subject": row["subject"]},
            account="default",
        )
    conn.execute("DELETE FROM emails_fts WHERE rowid = ?", (email_id,))
    with suppress(sqlite3.OperationalError):
        conn.execute("DELETE FROM vec_emails WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    stats.deleted += 1


def refresh_touched_threads(conn: sqlite3.Connection, touched_threads: set[int]) -> None:
    """Recompute stats for threads affected by the current ingest pass."""
    surviving = (
        {
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM threads WHERE id IN ({','.join('?' * len(touched_threads))})",
                tuple(touched_threads),
            )
        }
        if touched_threads
        else set()
    )
    refresh_thread_stats(conn, surviving)
