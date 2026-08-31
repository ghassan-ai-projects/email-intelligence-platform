"""Persist the knowledge projections produced by LLM enrichment."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from ..events import emit
from ..models import EnrichmentResult
from ..security import sanitize_text


def persist_enrichment(
    conn: sqlite3.Connection,
    email_id: int,
    result: EnrichmentResult,
    now: Callable[[], str],
    emit_event: Callable[..., int] = emit,
    sanitize_value: Callable[[str], str] = sanitize_text,
) -> None:
    """Replace one email's knowledge projections and emit their events."""
    account_row = conn.execute("SELECT account FROM emails WHERE id = ?", (email_id,)).fetchone()
    account = account_row["account"] if account_row else "default"

    conn.execute(
        "UPDATE emails SET language = ?, summary = ?, importance = ?, sentiment = ?, "
        "enriched_at = ? WHERE id = ?",
        (
            result.language,
            sanitize_value(result.summary),
            result.importance,
            result.sentiment,
            now(),
            email_id,
        ),
    )
    # Re-enrichment replaces previous knowledge rows for the email.
    conn.execute("DELETE FROM action_items WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM facts WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM email_entities WHERE email_id = ?", (email_id,))

    for item in result.action_items:
        description = sanitize_value(item.description)
        cur = conn.execute(
            "INSERT INTO action_items (email_id, description, owner, due_date, account) "
            "VALUES (?, ?, ?, ?, ?)",
            (email_id, description, item.owner, item.due_date, account),
        )
        emit_event(
            conn,
            "action_item_created",
            email_id,
            {
                "action_item_id": cur.lastrowid,
                "description": description,
                "owner": item.owner,
                "due_date": item.due_date,
            },
            account=account,
        )
    for fact in result.facts:
        fact_text = sanitize_value(fact.fact)
        cur = conn.execute(
            "INSERT INTO facts (email_id, fact, category, due_date, confidence, account) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email_id, fact_text, fact.category, fact.due_date, fact.confidence, account),
        )
        emit_event(
            conn,
            "fact_extracted",
            email_id,
            {
                "fact_id": cur.lastrowid,
                "fact": fact_text,
                "category": fact.category,
                "due_date": fact.due_date,
            },
            account=account,
        )
    emit_event(
        conn,
        "email_enriched",
        email_id,
        {
            "importance": result.importance,
            "sentiment": result.sentiment,
            "summary": sanitize_value(result.summary),
            "language": result.language,
        },
        account=account,
    )
    entity_lists = [
        ("person", result.entities.people),
        ("company", result.entities.companies),
        ("project", result.entities.projects),
        ("topic", result.entities.topics),
    ]
    for entity_type, names in entity_lists:
        for name in names:
            name = name.strip()
            if not name:
                continue
            normalized_name = name.lower()
            conn.execute(
                "INSERT OR IGNORE INTO entities (type, name, name_norm) VALUES (?, ?, ?)",
                (entity_type, name, normalized_name),
            )
            entity_id = conn.execute(
                "SELECT id FROM entities WHERE type = ? AND name_norm = ?",
                (entity_type, normalized_name),
            ).fetchone()["id"]
            conn.execute(
                "INSERT OR IGNORE INTO email_entities (email_id, entity_id) VALUES (?, ?)",
                (email_id, entity_id),
            )
