"""Conversation threading via References/In-Reply-To with a subject fallback.

Handles out-of-order arrival: if a new message links two existing threads
(e.g. the parent arrived after its children), the threads are merged.
"""

from __future__ import annotations

import re
import sqlite3

_REPLY_PREFIX = re.compile(r"^\s*((re|fwd?|aw|sv|antw)\s*(\[\d+\])?\s*:\s*)+", re.IGNORECASE)
_WS = re.compile(r"\s+")

# A reply without headers only joins a thread whose last activity is recent.
SUBJECT_FALLBACK_WINDOW_DAYS = 60


def normalize_subject(subject: str) -> str:
    return _WS.sub(" ", _REPLY_PREFIX.sub("", subject or "")).strip().lower()


def is_reply_subject(subject: str) -> bool:
    return bool(_REPLY_PREFIX.match(subject or ""))


def assign_thread(
    conn: sqlite3.Connection,
    message_id: str,
    subject: str,
    date_utc: str,
    refs: list[str],
    account: str = "default",
) -> int:
    """Pick (or create) the thread for a message about to be inserted.

    Returns the thread id. May merge existing threads if the message bridges them.
    """
    subject_norm = normalize_subject(subject)
    thread_ids: set[int] = set()

    if refs:
        placeholders = ",".join("?" * len(refs))
        rows = conn.execute(
            f"SELECT DISTINCT thread_id FROM emails "
            f"WHERE message_id IN ({placeholders}) AND thread_id IS NOT NULL",
            refs,
        ).fetchall()
        thread_ids.update(r["thread_id"] for r in rows)

    # Children that arrived before this message reference it.
    rows = conn.execute(
        "SELECT DISTINCT e.thread_id FROM email_refs r "
        "JOIN emails e ON e.id = r.email_id "
        "WHERE r.ref_message_id = ? AND e.thread_id IS NOT NULL",
        (message_id,),
    ).fetchall()
    thread_ids.update(r["thread_id"] for r in rows)

    if not thread_ids and subject_norm and is_reply_subject(subject):
        row = conn.execute(
            "SELECT id FROM threads WHERE subject_norm = ? "
            "AND last_date >= datetime(?, ?) "
            "ORDER BY last_date DESC LIMIT 1",
            (subject_norm, date_utc, f"-{SUBJECT_FALLBACK_WINDOW_DAYS} days"),
        ).fetchone()
        if row:
            thread_ids.add(row["id"])

    if not thread_ids:
        cur = conn.execute(
            "INSERT INTO threads (subject_norm, first_date, last_date, message_count, account) "
            "VALUES (?, ?, ?, 0, ?)",
            (subject_norm, date_utc, date_utc, account),
        )
        return cur.lastrowid

    keep = min(thread_ids)
    stale = thread_ids - {keep}
    if stale:
        placeholders = ",".join("?" * len(stale))
        conn.execute(
            f"UPDATE emails SET thread_id = ? WHERE thread_id IN ({placeholders})",
            (keep, *stale),
        )
        conn.execute(f"DELETE FROM threads WHERE id IN ({placeholders})", tuple(stale))
    return keep


def refresh_thread_stats(conn: sqlite3.Connection, thread_ids: set[int]) -> None:
    for tid in thread_ids:
        row = conn.execute(
            "SELECT MIN(date_utc) AS first_date, MAX(date_utc) AS last_date, "
            "COUNT(*) AS n FROM emails WHERE thread_id = ?",
            (tid,),
        ).fetchone()
        if row["n"] == 0:
            conn.execute("DELETE FROM threads WHERE id = ?", (tid,))
        else:
            conn.execute(
                "UPDATE threads SET first_date = ?, last_date = ?, message_count = ? "
                "WHERE id = ?",
                (row["first_date"], row["last_date"], row["n"], tid),
            )
