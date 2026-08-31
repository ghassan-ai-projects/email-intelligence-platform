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
    clean = lambda value: sanitize_value(value) if value is not None else None
    language = sanitize_value(result.language)
    sentiment = sanitize_value(result.sentiment)

    conn.execute(
        "UPDATE emails SET language = ?, summary = ?, importance = ?, sentiment = ?, "
        "enriched_at = ? WHERE id = ?",
        (
            language,
            sanitize_value(result.summary),
            result.importance,
            sentiment,
            now(),
            email_id,
        ),
    )
    existing_actions = conn.execute(
        "SELECT id, description, owner, due_date, status, completed_at "
        "FROM action_items WHERE email_id = ? ORDER BY id",
        (email_id,),
    ).fetchall()
    conn.execute("DELETE FROM facts WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM email_entities WHERE email_id = ?", (email_id,))

    retained_action_ids: list[int] = []
    for item in result.action_items:
        description = sanitize_value(item.description)
        owner = clean(item.owner)
        due_date = clean(item.due_date)
        match = next(
            (
                row
                for row in existing_actions
                if row["id"] not in retained_action_ids
                and row["description"] == description
                and row["owner"] == owner
                and row["due_date"] == due_date
            ),
            None,
        )
        if match:
            retained_action_ids.append(match["id"])
            conn.execute(
                "UPDATE action_items SET description = ?, owner = ?, due_date = ? WHERE id = ?",
                (description, owner, due_date, match["id"]),
            )
            continue
        cur = conn.execute(
            "INSERT INTO action_items (email_id, description, owner, due_date, account) "
            "VALUES (?, ?, ?, ?, ?)",
            (email_id, description, owner, due_date, account),
        )
        if cur.lastrowid is None:
            raise RuntimeError("failed to insert action item")
        retained_action_ids.append(cur.lastrowid)
        emit_event(
            conn,
            "action_item_created",
            email_id,
            {
                "action_item_id": cur.lastrowid,
                "description": description,
                "owner": owner,
                "due_date": due_date,
            },
            account=account,
        )
    if retained_action_ids:
        placeholders = ", ".join("?" for _ in retained_action_ids)
        conn.execute(
            f"DELETE FROM action_items WHERE email_id = ? AND id NOT IN ({placeholders})",
            (email_id, *retained_action_ids),
        )
    else:
        conn.execute("DELETE FROM action_items WHERE email_id = ?", (email_id,))

    for fact in result.facts:
        fact_text = sanitize_value(fact.fact)
        category = sanitize_value(fact.category)
        due_date = clean(fact.due_date)
        cur = conn.execute(
            "INSERT INTO facts (email_id, fact, category, due_date, confidence, account) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email_id, fact_text, category, due_date, fact.confidence, account),
        )
        emit_event(
            conn,
            "fact_extracted",
            email_id,
            {
                "fact_id": cur.lastrowid,
                "fact": fact_text,
                "category": category,
                "due_date": due_date,
            },
            account=account,
        )
    emit_event(
        conn,
        "email_enriched",
        email_id,
        {
            "importance": result.importance,
            "sentiment": sentiment,
            "summary": sanitize_value(result.summary),
            "language": language,
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
            name = sanitize_value(name).strip()
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
