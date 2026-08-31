"""MCP tools for knowledge queries, statistics, and synchronization."""

from __future__ import annotations

from .. import knowledge, search
from .runtime import _audit_tool, get_config, invocation_connection, mcp


@mcp.tool()
@_audit_tool
def search_threads(query: str, limit: int = 10) -> list[dict]:
    """Search conversations (threads) by keyword, ranked by matching messages."""
    with invocation_connection() as conn:
        return search.search_threads(conn, query, limit)


@mcp.tool()
@_audit_tool
def find_action_items(
    status: str = "open",
    owner: str | None = None,
    due_before: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Action items extracted from emails. status: open | done | all."""
    with invocation_connection() as conn:
        return knowledge.find_action_items(conn, status, owner, due_before, limit)


@mcp.tool()
@_audit_tool
def find_decisions(
    query: str | None = None, date_from: str | None = None, limit: int = 50
) -> list[dict]:
    """Decisions extracted from emails, newest first. Optional keyword filter."""
    with invocation_connection() as conn:
        return knowledge.find_decisions(conn, query, date_from, limit)


@mcp.tool()
@_audit_tool
def search_facts(
    query: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Structured facts extracted from emails.

    category: deadline | decision | change | commitment | info.
    """
    with invocation_connection() as conn:
        return knowledge.search_facts(conn, query, category, date_from, limit)


@mcp.tool()
@_audit_tool
def summarize_sender(addr: str) -> dict:
    """Profile of a sender: volume, dates, topics, open items, recent emails."""
    with invocation_connection() as conn:
        return knowledge.summarize_sender(conn, addr)


@mcp.tool()
@_audit_tool
def find_waiting_replies(min_age_days: int = 2, limit: int = 25) -> list[dict]:
    """Sent emails still awaiting a reply (we spoke last in the thread)."""
    with invocation_connection() as conn:
        return knowledge.find_waiting_replies(conn, min_age_days, limit)


@mcp.tool()
@_audit_tool
def daily_summary(date: str | None = None) -> dict:
    """Digest for one day (YYYY-MM-DD, default today): important mail, tasks, facts."""
    with invocation_connection() as conn:
        return knowledge.daily_summary(conn, date)


@mcp.tool()
@_audit_tool
def list_folders() -> list[dict]:
    """Mail folders with message counts."""
    with invocation_connection() as conn:
        return search.get_stats(conn)["folders"]


@mcp.tool()
@_audit_tool
def get_stats() -> dict:
    """Store statistics: totals, enrichment coverage, pipeline queue state."""
    with invocation_connection() as conn:
        return search.get_stats(conn)


@mcp.tool()
@_audit_tool
def sync_now(enrich: bool = True, limit: int = 100) -> dict:
    """Run mail sync (mbsync) + ingest now; optionally process the enrichment queue."""
    from ..sync_cycle import run_sync_cycle

    cfg = get_config()
    with invocation_connection() as conn:
        return run_sync_cycle(cfg, enrich=enrich, limit=limit, conn=conn).as_dict()
