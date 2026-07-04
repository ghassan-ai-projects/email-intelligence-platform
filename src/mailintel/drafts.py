"""Draft-first sending: agents prepare mail, sending is a separate deliberate step.

Drafts live in the store with no side effects; `send_draft` goes through every
sender.py guardrail (smtp.enabled, recipient allowlist) at send time — so a
draft created for a disallowed recipient still cannot be sent.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from .config import Config
from .events import emit
from .security import sanitize_text
from .sender import SendError, send_email


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "draft_id": row["id"],
        "to": json.loads(row["to_addrs"]),
        "cc": json.loads(row["cc_addrs"]),
        "subject": row["subject"],
        "body": row["body"],
        "in_reply_to_email_id": row["in_reply_to_email_id"],
        "attachment_ids": json.loads(row["attachment_ids"]),
        "status": row["status"],
        "account": row["account"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "sent_at": row["sent_at"],
    }


def create_draft(
    conn: sqlite3.Connection,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    in_reply_to_email_id: int | None = None,
    attachment_ids: list[int] | None = None,
    account: str = "default",
) -> dict:
    if not to:
        return {"error": "at least one recipient required"}
    now = _now()
    cur = conn.execute(
        "INSERT INTO drafts (to_addrs, cc_addrs, subject, body, in_reply_to_email_id, "
        "attachment_ids, account, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            json.dumps(to),
            json.dumps(cc or []),
            sanitize_text(subject),
            sanitize_text(body),
            in_reply_to_email_id,
            json.dumps(attachment_ids or []),
            account,
            now,
            now,
        ),
    )
    draft_id = cur.lastrowid
    assert draft_id is not None
    emit(
        conn,
        "draft_created",
        in_reply_to_email_id,
        {
            "draft_id": draft_id,
            "to": to,
            "subject": subject,
        },
        account=account,
    )
    conn.commit()
    return get_draft(conn, draft_id)


def get_draft(conn: sqlite3.Connection, draft_id: int) -> dict:
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        return {"error": f"draft {draft_id} not found"}
    return _row_to_dict(row)


def list_drafts(conn: sqlite3.Connection, status: str = "draft") -> list[dict]:
    if status == "all":
        rows = conn.execute("SELECT * FROM drafts ORDER BY updated_at DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM drafts WHERE status = ? ORDER BY updated_at DESC", (status,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_draft(
    conn: sqlite3.Connection,
    draft_id: int,
    to: list[str] | None = None,
    subject: str | None = None,
    body: str | None = None,
    cc: list[str] | None = None,
    attachment_ids: list[int] | None = None,
) -> dict:
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        return {"error": f"draft {draft_id} not found"}
    if row["status"] == "sent":
        return {"error": f"draft {draft_id} was already sent"}
    updates: dict = {}
    if to is not None:
        updates["to_addrs"] = json.dumps(to)
    if cc is not None:
        updates["cc_addrs"] = json.dumps(cc)
    if subject is not None:
        updates["subject"] = sanitize_text(subject)
    if body is not None:
        updates["body"] = sanitize_text(body)
    if attachment_ids is not None:
        updates["attachment_ids"] = json.dumps(attachment_ids)
    if updates:
        updates["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE drafts SET {sets} WHERE id = ?", (*updates.values(), draft_id))
        conn.commit()
    return get_draft(conn, draft_id)


def delete_draft(conn: sqlite3.Connection, draft_id: int) -> dict:
    cur = conn.execute("DELETE FROM drafts WHERE id = ? AND status != 'sent'", (draft_id,))
    conn.commit()
    if cur.rowcount == 0:
        return {"error": f"draft {draft_id} not found (or already sent)"}
    return {"draft_id": draft_id, "status": "deleted"}


def send_draft(conn: sqlite3.Connection, cfg: Config, draft_id: int) -> dict:
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        return {"error": f"draft {draft_id} not found"}
    if row["status"] == "sent":
        return {"error": f"draft {draft_id} was already sent at {row['sent_at']}"}
    draft = _row_to_dict(row)
    try:
        result = send_email(
            conn,
            cfg,
            to=draft["to"],
            subject=draft["subject"],
            body=draft["body"],
            cc=draft["cc"] or None,
            attachment_ids=draft["attachment_ids"] or None,
            in_reply_to_email_id=draft["in_reply_to_email_id"],
        )
    except SendError as exc:
        return {"error": str(exc), "draft_id": draft_id}
    now = _now()
    conn.execute(
        "UPDATE drafts SET status = 'sent', sent_at = ?, updated_at = ? WHERE id = ?",
        (now, now, draft_id),
    )
    emit(
        conn,
        "draft_sent",
        draft["in_reply_to_email_id"],
        {
            "draft_id": draft_id,
            "to": draft["to"],
            "subject": draft["subject"],
        },
        account=draft["account"],
    )
    conn.commit()
    result["draft_id"] = draft_id
    return result
