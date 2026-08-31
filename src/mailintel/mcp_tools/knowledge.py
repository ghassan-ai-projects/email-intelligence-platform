"""MCP tools for knowledge queries, statistics, and synchronization."""

from __future__ import annotations

from .. import knowledge, search
from ..mcp_server import _audit_tool, get_config, get_conn, mcp


@mcp.tool()
@_audit_tool
def search_threads(query: str, limit: int = 10) -> list[dict]:
    """Search conversations (threads) by keyword, ranked by matching messages."""
    conn = get_conn()
    try:
        return search.search_threads(conn, query, limit)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def find_action_items(
    status: str = "open",
    owner: str | None = None,
    due_before: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Action items extracted from emails. status: open | done | all."""
    conn = get_conn()
    try:
        return knowledge.find_action_items(conn, status, owner, due_before, limit)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def find_decisions(
    query: str | None = None, date_from: str | None = None, limit: int = 50
) -> list[dict]:
    """Decisions extracted from emails, newest first. Optional keyword filter."""
    conn = get_conn()
    try:
        return knowledge.find_decisions(conn, query, date_from, limit)
    finally:
        conn.close()


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
    conn = get_conn()
    try:
        return knowledge.search_facts(conn, query, category, date_from, limit)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def summarize_sender(addr: str) -> dict:
    """Profile of a sender: volume, dates, topics, open items, recent emails."""
    conn = get_conn()
    try:
        return knowledge.summarize_sender(conn, addr)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def find_waiting_replies(min_age_days: int = 2, limit: int = 25) -> list[dict]:
    """Sent emails still awaiting a reply (we spoke last in the thread)."""
    conn = get_conn()
    try:
        return knowledge.find_waiting_replies(conn, min_age_days, limit)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def daily_summary(date: str | None = None) -> dict:
    """Digest for one day (YYYY-MM-DD, default today): important mail, tasks, facts."""
    conn = get_conn()
    try:
        return knowledge.daily_summary(conn, date)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def list_folders() -> list[dict]:
    """Mail folders with message counts."""
    conn = get_conn()
    try:
        return search.get_stats(conn)["folders"]
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def get_stats() -> dict:
    """Store statistics: totals, enrichment coverage, pipeline queue state."""
    conn = get_conn()
    try:
        return search.get_stats(conn)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def sync_now(enrich: bool = True, limit: int = 100) -> dict:
    """Run mail sync (mbsync) + ingest now; optionally process the enrichment queue."""
    from ..enrich.pipeline import run_pipeline
    from ..ingest import ingest
    from ..sync import run_sync

    cfg = get_config()
    result: dict = {"sync": run_sync(cfg) or "ok"}
    conn = get_conn()
    try:
        result["ingest"] = ingest(conn, cfg).as_dict()
        if enrich:
            result["enrich"] = run_pipeline(conn, cfg, limit=limit).as_dict()
    finally:
        conn.close()
    return result
