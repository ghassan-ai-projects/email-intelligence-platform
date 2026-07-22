"""Full-text and filtered search over the email store."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

_TOKEN = re.compile(r'"[^"]*"|\S+')


def fts_query(user_query: str) -> str:
    """Sanitize free text into an FTS5 query: quoted terms ANDed, phrases preserved."""
    parts = []
    for tok in _TOKEN.findall(user_query):
        tok = tok.strip('"').replace('"', "")
        if tok:
            parts.append(f'"{tok}"')
    return " ".join(parts)


def email_row_brief(row: sqlite3.Row, extra: dict | None = None) -> dict:
    d = {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "date": row["date_utc"],
        "folder": row["folder"],
        "from": f"{row['from_name']} <{row['from_addr']}>".strip(),
        "subject": row["subject"],
        "snippet": row["snippet"],
        "has_attachments": bool(row["has_attachments"]),
        "is_sent": bool(row["is_sent"]),
    }
    keys = row.keys()
    if "summary" in keys and row["summary"]:
        d["summary"] = row["summary"]
    if "importance" in keys and row["importance"] is not None:
        d["importance"] = row["importance"]
    # Guardrail scan info (present after v4 migration).
    if "guardrail_score" in keys and row["guardrail_score"]:
        d["guardrail_score"] = row["guardrail_score"]
        d["guardrail_blocked"] = bool(row["guardrail_blocked"])
        if "guardrail_warnings" in keys and row["guardrail_warnings"]:
            import json

            d["guardrail_warnings"] = json.loads(row["guardrail_warnings"])
    if extra:
        d.update(extra)
    return d


def search_emails(
    conn: sqlite3.Connection,
    query: str | None = None,
    from_addr: str | None = None,
    to_addr: str | None = None,
    folder: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    has_attachments: bool | None = None,
    unread_only: bool = False,
    tag: str | None = None,
    limit: int = 20,
) -> list[dict]:
    where: list[str] = []
    params: list[Any] = []

    if query:
        where.append("e.id IN (SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?)")
        params.append(fts_query(query))
    if from_addr:
        where.append("(e.from_addr LIKE ? OR e.from_name LIKE ?)")
        params.extend([f"%{from_addr}%", f"%{from_addr}%"])
    if to_addr:
        where.append("e.id IN (SELECT email_id FROM recipients WHERE addr LIKE ? OR name LIKE ?)")
        params.extend([f"%{to_addr}%", f"%{to_addr}%"])
    if folder:
        where.append("e.folder = ?")
        params.append(folder)
    if date_from:
        where.append("e.date_utc >= ?")
        params.append(date_from)
    if date_to:
        where.append("e.date_utc <= ?")
        params.append(date_to + (" 23:59:59" if len(date_to) == 10 else ""))
    if has_attachments is not None:
        where.append("e.has_attachments = ?")
        params.append(int(has_attachments))
    if unread_only:
        where.append("e.is_read = 0")
    if tag:
        where.append("e.id IN (SELECT email_id FROM email_tags WHERE tag = ?)")
        params.append(tag.lower().strip())

    sql = "SELECT e.* FROM emails e"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.date_utc DESC LIMIT ?"
    params.append(max(1, min(limit, 100)))

    return [email_row_brief(r) for r in conn.execute(sql, params)]


def get_email(conn: sqlite3.Connection, email_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not row:
        return None
    d = email_row_brief(row)
    d["body"] = row["body_text"]
    d["message_id"] = row["message_id"]
    d["language"] = row["language"]
    d["sentiment"] = row["sentiment"]
    d["recipients"] = [
        {"kind": r["kind"], "addr": r["addr"], "name": r["name"]}
        for r in conn.execute("SELECT * FROM recipients WHERE email_id = ?", (email_id,))
    ]
    d["attachments"] = [
        {
            "id": r["id"],
            "filename": r["filename"],
            "mime": r["mime"],
            "size": r["size"],
            "has_extracted_text": bool(r["extracted_text"]),
        }
        for r in conn.execute("SELECT * FROM attachments WHERE email_id = ?", (email_id,))
    ]
    d["action_items"] = [
        dict(r)
        for r in conn.execute(
            "SELECT id, description, owner, due_date, status FROM action_items WHERE email_id = ?",
            (email_id,),
        )
    ]
    d["facts"] = [
        dict(r)
        for r in conn.execute(
            "SELECT id, fact, category, due_date FROM facts WHERE email_id = ?", (email_id,)
        )
    ]
    d["entities"] = [
        {"type": r["type"], "name": r["name"]}
        for r in conn.execute(
            "SELECT en.type, en.name FROM email_entities ee "
            "JOIN entities en ON en.id = ee.entity_id WHERE ee.email_id = ?",
            (email_id,),
        )
    ]
    d["tags"] = [
        r["tag"]
        for r in conn.execute(
            "SELECT tag FROM email_tags WHERE email_id = ? ORDER BY tag", (email_id,)
        )
    ]
    d["agent_notes"] = row["agent_notes"]
    d["account"] = row["account"]
    return d


def get_thread(conn: sqlite3.Connection, thread_id: int) -> dict | None:
    t = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
    if not t:
        return None
    emails = [
        email_row_brief(r)
        for r in conn.execute(
            "SELECT * FROM emails WHERE thread_id = ? ORDER BY date_utc", (thread_id,)
        )
    ]
    participants = sorted(
        {
            r["addr"]
            for r in conn.execute(
                "SELECT DISTINCT addr FROM recipients WHERE email_id IN "
                "(SELECT id FROM emails WHERE thread_id = ?) "
                "UNION SELECT DISTINCT from_addr AS addr FROM emails WHERE thread_id = ?",
                (thread_id, thread_id),
            )
            if r["addr"]
        }
    )
    return {
        "thread_id": thread_id,
        "subject": emails[0]["subject"] if emails else "",
        "first_date": t["first_date"],
        "last_date": t["last_date"],
        "message_count": t["message_count"],
        "participants": participants,
        "emails": emails,
    }


def search_threads(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT e.thread_id, COUNT(*) AS hits FROM emails e "
        "WHERE e.id IN (SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?) "
        "GROUP BY e.thread_id ORDER BY hits DESC, MAX(e.date_utc) DESC LIMIT ?",
        (fts_query(query), max(1, min(limit, 50))),
    ).fetchall()
    out = []
    for r in rows:
        t = get_thread(conn, r["thread_id"])
        if t:
            t["matching_messages"] = r["hits"]
            # Keep thread listings compact: drop per-email bodies/snippets detail.
            t["emails"] = [
                {k: e[k] for k in ("id", "date", "from", "subject", "is_sent")} for e in t["emails"]
            ]
            out.append(t)
    return out


def get_stats(conn: sqlite3.Connection) -> dict:
    def one(sql: str, params: tuple = ()) -> Any:
        return conn.execute(sql, params).fetchone()[0]

    folders = [
        {"folder": r["folder"], "count": r["n"]}
        for r in conn.execute(
            "SELECT folder, COUNT(*) AS n FROM emails GROUP BY folder ORDER BY n DESC"
        )
    ]
    jobs = {
        f"{r['stage']}:{r['status']}": r["n"]
        for r in conn.execute(
            "SELECT stage, status, COUNT(*) AS n FROM pipeline_jobs GROUP BY stage, status"
        )
    }
    return {
        "emails": one("SELECT COUNT(*) FROM emails"),
        "threads": one("SELECT COUNT(*) FROM threads"),
        "enriched": one("SELECT COUNT(*) FROM emails WHERE enriched_at IS NOT NULL"),
        "action_items_open": one("SELECT COUNT(*) FROM action_items WHERE status = 'open'"),
        "facts": one("SELECT COUNT(*) FROM facts"),
        "entities": one("SELECT COUNT(*) FROM entities"),
        "date_range": {
            "first": one("SELECT MIN(date_utc) FROM emails"),
            "last": one("SELECT MAX(date_utc) FROM emails"),
        },
        "folders": folders,
        "pipeline_jobs": jobs,
    }
