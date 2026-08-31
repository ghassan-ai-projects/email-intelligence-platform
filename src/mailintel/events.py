"""Append-only event log so agents can react to changes instead of polling searches.

Producers emit during ingest, enrichment, write-back and sending. A consumer
(e.g. OpenClaw) stores the last cursor it processed and calls
`get_events_since(cursor)` to fetch only the delta.

Event types:
  email_ingested, email_deleted, email_enriched, action_item_created,
  fact_extracted, action_item_completed, draft_created, draft_sent, email_sent
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

EVENT_TYPES = {
    "email_ingested",
    "email_deleted",
    "email_enriched",
    "action_item_created",
    "fact_extracted",
    "action_item_completed",
    "draft_created",
    "draft_sent",
    "email_sent",
}


def emit(
    conn: sqlite3.Connection,
    event_type: str,
    email_id: int | None = None,
    payload: dict[str, Any] | None = None,
    account: str = "default",
) -> int:
    if event_type not in EVENT_TYPES:
        msg = f"unknown event type: {event_type!r}"
        raise ValueError(msg)
    cur = conn.execute(
        "INSERT INTO events (type, email_id, payload, account, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            event_type,
            email_id,
            json.dumps(payload or {}, ensure_ascii=False, default=str),
            account,
            datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    if cur.lastrowid is None:
        msg = "failed to insert event"
        raise RuntimeError(msg)
    return cur.lastrowid


def prune_events(conn: sqlite3.Connection, before_id: int) -> int:
    """Delete events with id < before_id. Returns the number deleted."""
    cur = conn.execute("DELETE FROM events WHERE id < ?", (before_id,))
    conn.commit()
    return cur.rowcount


def get_events_since(
    conn: sqlite3.Connection,
    cursor: int = 0,
    types: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Events with id > cursor, oldest first. Returns next_cursor to persist.

    `latest_cursor` is always the newest event id in the store, so a consumer
    can fast-forward past types it filtered out.
    """
    cursor = max(0, cursor)
    limit = max(1, min(limit, 500))
    params: list[Any] = [cursor]
    sql = "SELECT * FROM events WHERE id > ?"
    if types:
        sql += f" AND type IN ({','.join('?' * len(types))})"
        params.extend(types)
    sql += " ORDER BY id LIMIT ?"
    params.append(limit)

    started_transaction = not conn.in_transaction
    if started_transaction:
        conn.execute("BEGIN")
    try:
        # Read the watermark first and fetch rows from the same snapshot. A
        # commit between independent snapshots must not advance the cursor
        # past an event that this call could not return.
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
        rows = conn.execute(sql, params).fetchall()
        events = [
            {
                "id": r["id"],
                "type": r["type"],
                "email_id": r["email_id"],
                "payload": json.loads(r["payload"]),
                "account": r["account"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        next_cursor = events[-1]["id"] if events else cursor
        if types and len(events) < limit:
            next_cursor = latest
    finally:
        if started_transaction:
            conn.rollback()
    return {
        "events": events,
        "next_cursor": next_cursor,
        "latest_cursor": latest,
        "has_more": len(events) == limit,
    }
