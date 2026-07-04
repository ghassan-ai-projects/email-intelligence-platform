"""Knowledge-level queries over enriched data (facts, action items, senders, digests)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from .search import email_row_brief


def _email_context(conn: sqlite3.Connection, email_id: int) -> dict:
    r = conn.execute(
        "SELECT id, thread_id, date_utc, subject, from_addr, from_name FROM emails WHERE id = ?",
        (email_id,),
    ).fetchone()
    if not r:
        return {"email_id": email_id}
    return {
        "email_id": r["id"],
        "thread_id": r["thread_id"],
        "date": r["date_utc"],
        "subject": r["subject"],
        "from": f"{r['from_name']} <{r['from_addr']}>".strip(),
    }


def find_action_items(
    conn: sqlite3.Connection,
    status: str = "open",
    owner: str | None = None,
    due_before: str | None = None,
    limit: int = 50,
) -> list[dict]:
    where = ["1=1"] if status == "all" else ["a.status = ?"]
    params: list = [] if status == "all" else [status]
    if owner:
        where.append("a.owner LIKE ?")
        params.append(f"%{owner}%")
    if due_before:
        where.append("a.due_date IS NOT NULL AND a.due_date <= ?")
        params.append(due_before)
    params.append(max(1, min(limit, 200)))
    rows = conn.execute(
        f"SELECT a.* FROM action_items a JOIN emails e ON e.id = a.email_id "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY a.due_date IS NULL, a.due_date, e.date_utc DESC LIMIT ?",
        params,
    ).fetchall()
    return [
        {
            "id": r["id"],
            "description": r["description"],
            "owner": r["owner"],
            "due_date": r["due_date"],
            "status": r["status"],
            "source": _email_context(conn, r["email_id"]),
        }
        for r in rows
    ]


def search_facts(
    conn: sqlite3.Connection,
    query: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    limit: int = 50,
) -> list[dict]:
    where: list[str] = []
    params: list = []
    if query:
        where.append("f.fact LIKE ?")
        params.append(f"%{query}%")
    if category:
        where.append("f.category = ?")
        params.append(category)
    if date_from:
        where.append("e.date_utc >= ?")
        params.append(date_from)
    sql = "SELECT f.*, e.date_utc FROM facts f JOIN emails e ON e.id = f.email_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.date_utc DESC LIMIT ?"
    params.append(max(1, min(limit, 200)))
    return [
        {
            "fact": r["fact"],
            "category": r["category"],
            "due_date": r["due_date"],
            "confidence": r["confidence"],
            "source": _email_context(conn, r["email_id"]),
        }
        for r in conn.execute(sql, params)
    ]


def find_decisions(
    conn: sqlite3.Connection,
    query: str | None = None,
    date_from: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return search_facts(conn, query=query, category="decision", date_from=date_from, limit=limit)


def summarize_sender(conn: sqlite3.Connection, addr: str, recent: int = 10) -> dict:
    like = f"%{addr}%"
    agg = conn.execute(
        "SELECT COUNT(*) AS total, MIN(date_utc) AS first_date, MAX(date_utc) AS last_date, "
        "SUM(has_attachments) AS with_attachments, SUM(1 - is_read) AS unread "
        "FROM emails WHERE from_addr LIKE ? AND is_sent = 0",
        (like,),
    ).fetchone()
    top_topics = [
        {"topic": r["name"], "count": r["n"]}
        for r in conn.execute(
            "SELECT en.name, COUNT(*) AS n FROM email_entities ee "
            "JOIN entities en ON en.id = ee.entity_id "
            "JOIN emails e ON e.id = ee.email_id "
            "WHERE e.from_addr LIKE ? AND en.type = 'topic' "
            "GROUP BY en.id ORDER BY n DESC LIMIT 10",
            (like,),
        )
    ]
    recent_rows = conn.execute(
        "SELECT * FROM emails WHERE from_addr LIKE ? AND is_sent = 0 "
        "ORDER BY date_utc DESC LIMIT ?",
        (like, recent),
    ).fetchall()
    open_items = conn.execute(
        "SELECT COUNT(*) AS n FROM action_items a JOIN emails e ON e.id = a.email_id "
        "WHERE e.from_addr LIKE ? AND a.status = 'open'",
        (like,),
    ).fetchone()["n"]
    return {
        "sender": addr,
        "total_received": agg["total"],
        "first_date": agg["first_date"],
        "last_date": agg["last_date"],
        "unread": agg["unread"] or 0,
        "with_attachments": agg["with_attachments"] or 0,
        "open_action_items": open_items,
        "top_topics": top_topics,
        "recent_emails": [email_row_brief(r) for r in recent_rows],
    }


def find_waiting_replies(
    conn: sqlite3.Connection, min_age_days: int = 2, limit: int = 25
) -> list[dict]:
    """Threads where our sent message is the latest and nobody replied since."""
    cutoff = (datetime.now(UTC) - timedelta(days=min_age_days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT e.* FROM emails e "
        "JOIN threads t ON t.id = e.thread_id "
        "WHERE e.is_sent = 1 AND e.date_utc = t.last_date AND t.last_date <= ? "
        "AND t.message_count >= 1 "
        "ORDER BY t.last_date DESC LIMIT ?",
        (cutoff, max(1, min(limit, 100))),
    ).fetchall()
    out = []
    for r in rows:
        recipients = [
            f"{rr['name']} <{rr['addr']}>".strip()
            for rr in conn.execute(
                "SELECT addr, name FROM recipients WHERE email_id = ? AND kind = 'to'",
                (r["id"],),
            )
        ]
        d = email_row_brief(r, {"waiting_since": r["date_utc"], "recipients": recipients})
        out.append(d)
    return out


def daily_summary(conn: sqlite3.Connection, date: str | None = None) -> dict:
    date = date or datetime.now(UTC).strftime("%Y-%m-%d")
    start, end = f"{date} 00:00:00", f"{date} 23:59:59"
    rows = conn.execute(
        "SELECT * FROM emails WHERE date_utc BETWEEN ? AND ? AND is_sent = 0 "
        "ORDER BY importance DESC NULLS LAST, date_utc DESC",
        (start, end),
    ).fetchall()
    important = [email_row_brief(r) for r in rows if (r["importance"] or 0) >= 4]
    new_items = [
        {
            "description": r["description"],
            "owner": r["owner"],
            "due_date": r["due_date"],
            "source": _email_context(conn, r["email_id"]),
        }
        for r in conn.execute(
            "SELECT a.* FROM action_items a JOIN emails e ON e.id = a.email_id "
            "WHERE e.date_utc BETWEEN ? AND ? AND a.status = 'open'",
            (start, end),
        )
    ]
    new_facts = [
        {"fact": r["fact"], "category": r["category"], "due_date": r["due_date"]}
        for r in conn.execute(
            "SELECT f.* FROM facts f JOIN emails e ON e.id = f.email_id "
            "WHERE e.date_utc BETWEEN ? AND ? AND f.category != 'info'",
            (start, end),
        )
    ]
    return {
        "date": date,
        "received": len(rows),
        "unread": sum(1 for r in rows if not r["is_read"]),
        "important": important,
        "new_action_items": new_items,
        "key_facts": new_facts,
        "all_emails": [email_row_brief(r) for r in rows[:50]],
    }
