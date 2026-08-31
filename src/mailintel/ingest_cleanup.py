"""Cleanup and thread maintenance for Maildir ingestion."""

from __future__ import annotations

import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from .events import emit
from .ingest_maildir import iter_maildirs, segment_matches, split_flags
from .threading_ import refresh_thread_stats

if TYPE_CHECKING:
    from .ingest import IngestStats


def remove_missing_files(
    conn: sqlite3.Connection,
    known: dict[tuple[str, str], tuple[str, int]],
    seen: set[tuple[str, str]],
    touched_threads: set[int],
    stats: IngestStats,
    root: Path,
    sent_folders: list[str],
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
        else:
            _refresh_email_projection(conn, email_id, root, sent_folders)


def _refresh_email_projection(
    conn: sqlite3.Connection, email_id: int, root: Path, sent_folders: list[str]
) -> None:
    """Recompute aggregate flags and canonical path after a copy disappears."""
    folders = dict(iter_maildirs(root))
    copies: list[tuple[str, Path, bool, bool]] = []
    for folder, filename in conn.execute(
        "SELECT folder, filename FROM sync_state WHERE email_id = ? ORDER BY rowid", (email_id,)
    ):
        folder_path = folders.get(folder)
        if folder_path is None:
            continue
        for subdirectory in ("cur", "new"):
            candidate = folder_path / subdirectory / filename
            if candidate.is_file():
                _, is_read = split_flags(filename)
                copies.append((folder, candidate, segment_matches(folder, sent_folders), is_read))
                break
    if not copies:
        return
    folder, path, _is_sent, _is_read = copies[0]
    conn.execute(
        "UPDATE emails SET folder = ?, maildir_path = ?, is_sent = ?, is_read = ? WHERE id = ?",
        (
            folder,
            str(path.relative_to(root)),
            int(any(copy[2] for copy in copies)),
            int(all(copy[3] for copy in copies)),
            email_id,
        ),
    )


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
