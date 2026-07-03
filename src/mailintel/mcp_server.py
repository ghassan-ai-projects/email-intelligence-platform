"""MCP server exposing semantic, knowledge-level email tools over stdio."""

from __future__ import annotations

import sqlite3

from mcp.server.fastmcp import FastMCP

from . import db, knowledge, search
from .config import Config, load_config
from .enrich.embeddings import VoyageEmbedder, embedding_input, knn_email_ids

mcp = FastMCP(
    "mailintel",
    instructions=(
        "Local email intelligence platform. Emails are synced to a local store, "
        "indexed and AI-enriched (summaries, action items, entities, facts, embeddings). "
        "Prefer knowledge tools (find_action_items, search_facts, daily_summary, ...) over "
        "raw search when the question is about tasks, decisions or people. Search tools "
        "return compact results; use get_email for the full body."
    ),
)

_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_conn() -> sqlite3.Connection:
    # One connection per call: cheap with WAL, avoids cross-thread sqlite issues.
    return db.connect(get_config().storage.db_path)


@mcp.tool()
def search_emails(
    query: str | None = None,
    from_addr: str | None = None,
    to_addr: str | None = None,
    folder: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    has_attachments: bool | None = None,
    unread_only: bool = False,
    limit: int = 20,
) -> list[dict]:
    """Full-text + filtered email search.

    query matches subject/body/sender via FTS; dates are YYYY-MM-DD;
    from_addr/to_addr substring-match addresses and names.
    """
    conn = get_conn()
    try:
        return search.search_emails(
            conn, query, from_addr, to_addr, folder, date_from, date_to,
            has_attachments, unread_only, limit,
        )
    finally:
        conn.close()


@mcp.tool()
def semantic_search(query: str, limit: int = 10) -> list[dict]:
    """Find emails semantically similar to a natural-language query (vector search).

    Use for meaning-based questions ('complaints about latency', 'pricing discussions')
    where keyword search would miss synonyms. Requires embeddings to be built.
    """
    cfg = get_config()
    conn = get_conn()
    try:
        embedder = VoyageEmbedder(cfg.embeddings)
        hits = knn_email_ids(conn, embedder.embed_query(query), max(1, min(limit, 50)))
        out = []
        for email_id, distance in hits:
            row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
            if row:
                out.append(search.email_row_brief(row, {"distance": round(distance, 4)}))
        return out
    finally:
        conn.close()


@mcp.tool()
def related_emails(email_id: int, limit: int = 10) -> list[dict]:
    """Find emails most similar to a given email (by embedding distance)."""
    cfg = get_config()
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        if not row:
            return []
        try:
            vec_row = conn.execute(
                "SELECT embedding FROM vec_emails WHERE email_id = ?", (email_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            vec_row = None
        if vec_row:
            import struct

            n = len(vec_row["embedding"]) // 4
            query_vec = list(struct.unpack(f"{n}f", vec_row["embedding"]))
        else:
            embedder = VoyageEmbedder(cfg.embeddings)
            query_vec = embedder.embed_query(embedding_input(row, cfg.embeddings.max_chars))
        hits = knn_email_ids(conn, query_vec, max(1, min(limit, 50)) + 1)
        out = []
        for eid, distance in hits:
            if eid == email_id:
                continue
            r = conn.execute("SELECT * FROM emails WHERE id = ?", (eid,)).fetchone()
            if r:
                out.append(search.email_row_brief(r, {"distance": round(distance, 4)}))
        return out[:limit]
    finally:
        conn.close()


@mcp.tool()
def get_email(email_id: int) -> dict:
    """Full detail for one email: body, recipients, attachments, extracted knowledge."""
    conn = get_conn()
    try:
        return search.get_email(conn, email_id) or {"error": f"email {email_id} not found"}
    finally:
        conn.close()


@mcp.tool()
def get_thread(thread_id: int) -> dict:
    """A whole conversation: participants, chronology, per-message summaries."""
    conn = get_conn()
    try:
        return search.get_thread(conn, thread_id) or {"error": f"thread {thread_id} not found"}
    finally:
        conn.close()


@mcp.tool()
def search_threads(query: str, limit: int = 10) -> list[dict]:
    """Search conversations (threads) by keyword, ranked by matching messages."""
    conn = get_conn()
    try:
        return search.search_threads(conn, query, limit)
    finally:
        conn.close()


@mcp.tool()
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
def find_decisions(query: str | None = None, date_from: str | None = None, limit: int = 50) -> list[dict]:
    """Decisions extracted from emails, newest first. Optional keyword filter."""
    conn = get_conn()
    try:
        return knowledge.find_decisions(conn, query, date_from, limit)
    finally:
        conn.close()


@mcp.tool()
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
def summarize_sender(addr: str) -> dict:
    """Profile of a sender: volume, dates, topics, open items, recent emails."""
    conn = get_conn()
    try:
        return knowledge.summarize_sender(conn, addr)
    finally:
        conn.close()


@mcp.tool()
def find_waiting_replies(min_age_days: int = 2, limit: int = 25) -> list[dict]:
    """Sent emails still awaiting a reply (we spoke last in the thread)."""
    conn = get_conn()
    try:
        return knowledge.find_waiting_replies(conn, min_age_days, limit)
    finally:
        conn.close()


@mcp.tool()
def daily_summary(date: str | None = None) -> dict:
    """Digest for one day (YYYY-MM-DD, default today): important mail, tasks, facts."""
    conn = get_conn()
    try:
        return knowledge.daily_summary(conn, date)
    finally:
        conn.close()


@mcp.tool()
def list_folders() -> list[dict]:
    """Mail folders with message counts."""
    conn = get_conn()
    try:
        return search.get_stats(conn)["folders"]
    finally:
        conn.close()


@mcp.tool()
def get_stats() -> dict:
    """Store statistics: totals, enrichment coverage, pipeline queue state."""
    conn = get_conn()
    try:
        return search.get_stats(conn)
    finally:
        conn.close()


@mcp.tool()
def sync_now(enrich: bool = True, limit: int = 100) -> dict:
    """Run mail sync (mbsync) + ingest now; optionally process the enrichment queue."""
    from .enrich.pipeline import run_pipeline
    from .ingest import ingest
    from .sync import run_sync

    cfg = get_config()
    result: dict = {}
    result["sync"] = run_sync(cfg) or "ok"
    conn = get_conn()
    try:
        result["ingest"] = ingest(conn, cfg).as_dict()
        if enrich:
            result["enrich"] = run_pipeline(conn, cfg, limit=limit).as_dict()
    finally:
        conn.close()
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
