"""MCP tools for events and agent write-back."""

from __future__ import annotations

from .. import actions
from .runtime import _audit_tool, invocation_connection, mcp


@mcp.tool()
@_audit_tool
def get_events_since(cursor: int = 0, types: list[str] | None = None, limit: int = 100) -> dict:
    """Change feed for reactive agents: events with id > cursor, oldest first.

    Persist the returned next_cursor and pass it on the next call to receive
    only the delta. Event types: email_ingested, email_deleted, email_enriched,
    action_item_created, fact_extracted, action_item_completed, draft_created,
    draft_sent, email_sent.
    """
    from ..events import get_events_since as fetch

    with invocation_connection() as conn:
        return fetch(conn, cursor, types, limit)


@mcp.tool()
@_audit_tool
def complete_action_item(action_item_id: int, done: bool = True) -> dict:
    """Mark an action item done (or reopen it with done=false)."""
    with invocation_connection() as conn:
        return actions.complete_action_item(conn, action_item_id, done)


@mcp.tool()
@_audit_tool
def set_importance(email_id: int, importance: int) -> dict:
    """Override an email's importance (1=bulk ... 5=urgent)."""
    with invocation_connection() as conn:
        return actions.set_importance(conn, email_id, importance)


@mcp.tool()
@_audit_tool
def tag_email(email_id: int, tag: str) -> dict:
    """Add a lowercase tag to an email (e.g. 'triaged', 'invoice', 'project-x')."""
    with invocation_connection() as conn:
        return actions.tag_email(conn, email_id, tag)


@mcp.tool()
@_audit_tool
def untag_email(email_id: int, tag: str) -> dict:
    """Remove a tag from an email."""
    with invocation_connection() as conn:
        return actions.untag_email(conn, email_id, tag)


@mcp.tool()
@_audit_tool
def list_tags() -> list[dict]:
    """All tags in use, with email counts."""
    with invocation_connection() as conn:
        return actions.list_tags(conn)


@mcp.tool()
@_audit_tool
def add_email_note(email_id: int, note: str) -> dict:
    """Append a timestamped agent note to an email (shown in get_email)."""
    with invocation_connection() as conn:
        return actions.add_note(conn, email_id, note)
