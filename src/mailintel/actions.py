"""Write-back operations: agents mutate state instead of re-discovering it.

Complements the read-side knowledge tools — an agent that resolved a task,
triaged an email or learned something can record that here.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .events import emit
from .security import sanitize_text


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def complete_action_item(conn: sqlite3.Connection, action_item_id: int, done: bool = True) -> dict:
    row = conn.execute(
        "SELECT * FROM action_items WHERE id = ?", (action_item_id,)
    ).fetchone()
    if not row:
        return {"error": f"action item {action_item_id} not found"}
    status = "done" if done else "open"
    conn.execute(
        "UPDATE action_items SET status = ?, completed_at = ? WHERE id = ?",
        (status, _now() if done else None, action_item_id),
    )
    if done:
        emit(conn, "action_item_completed", row["email_id"], {
            "action_item_id": action_item_id,
            "description": row["description"],
        }, account=row["account"])
    conn.commit()
    return {"action_item_id": action_item_id, "status": status}


def set_importance(conn: sqlite3.Connection, email_id: int, importance: int) -> dict:
    importance = min(5, max(1, importance))
    cur = conn.execute(
        "UPDATE emails SET importance = ? WHERE id = ?", (importance, email_id)
    )
    if cur.rowcount == 0:
        return {"error": f"email {email_id} not found"}
    row = conn.execute("SELECT account FROM emails WHERE id = ?", (email_id,)).fetchone()
    conn.commit()
    return {"email_id": email_id, "importance": importance, "account": row["account"]}


def tag_email(conn: sqlite3.Connection, email_id: int, tag: str) -> dict:
    tag = sanitize_text(tag).strip().lower()
    if not tag:
        return {"error": "empty tag"}
    row = conn.execute("SELECT account FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not row:
        return {"error": f"email {email_id} not found"}
    conn.execute(
        "INSERT OR IGNORE INTO email_tags (email_id, tag) VALUES (?, ?)", (email_id, tag)
    )
    conn.commit()
    return {"email_id": email_id, "tags": get_tags(conn, email_id), "account": row["account"]}


def untag_email(conn: sqlite3.Connection, email_id: int, tag: str) -> dict:
    conn.execute(
        "DELETE FROM email_tags WHERE email_id = ? AND tag = ?",
        (email_id, sanitize_text(tag).strip().lower()),
    )
    conn.commit()
    return {"email_id": email_id, "tags": get_tags(conn, email_id)}


def get_tags(conn: sqlite3.Connection, email_id: int) -> list[str]:
    return [
        r["tag"]
        for r in conn.execute(
            "SELECT tag FROM email_tags WHERE email_id = ? ORDER BY tag", (email_id,)
        )
    ]


def list_tags(conn: sqlite3.Connection) -> list[dict]:
    return [
        {"tag": r["tag"], "count": r["n"]}
        for r in conn.execute(
            "SELECT tag, COUNT(*) AS n FROM email_tags GROUP BY tag ORDER BY n DESC"
        )
    ]


def add_note(conn: sqlite3.Connection, email_id: int, note: str) -> dict:
    """Append a timestamped agent note to an email (notes accumulate)."""
    note = sanitize_text(note).strip()
    if not note:
        return {"error": "empty note"}
    row = conn.execute(
        "SELECT agent_notes, account FROM emails WHERE id = ?", (email_id,)
    ).fetchone()
    if not row:
        return {"error": f"email {email_id} not found"}
    entry = f"[{_now()}] {note}"
    combined = f'{row["agent_notes"]}\n{entry}' if row["agent_notes"] else entry
    conn.execute("UPDATE emails SET agent_notes = ? WHERE id = ?", (combined, email_id))
    conn.commit()
    return {"email_id": email_id, "agent_notes": combined, "account": row["account"]}
