"""MCP tools for keyword and semantic email search."""

from __future__ import annotations

import sqlite3
import struct

from .. import search
from ..enrich.embeddings import embedding_input, knn_email_ids, make_embedder
from ..mcp_server import _audit_tool, get_config, get_conn, mcp


@mcp.tool()
@_audit_tool
def search_emails(
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
    """Full-text + filtered email search.

    query matches subject/body/sender via FTS; dates are YYYY-MM-DD;
    from_addr/to_addr substring-match addresses and names; tag filters
    to emails tagged via tag_email.
    """
    conn = get_conn()
    try:
        return search.search_emails(
            conn,
            query,
            from_addr,
            to_addr,
            folder,
            date_from,
            date_to,
            has_attachments,
            unread_only,
            tag,
            limit,
        )
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def semantic_search(query: str, limit: int = 10) -> list[dict]:
    """Find emails semantically similar to a natural-language query (vector search).

    Use for meaning-based questions ('complaints about latency', 'pricing discussions')
    where keyword search would miss synonyms. Requires embeddings to be built.
    """
    cfg = get_config()
    conn = get_conn()
    try:
        embedder = make_embedder(cfg.embeddings)
        hits = knn_email_ids(conn, embedder.embed_query(query), max(1, min(limit, 50)))
        results = []
        for email_id, distance in hits:
            row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
            if row:
                results.append(search.email_row_brief(row, {"distance": round(distance, 4)}))
        return results
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def related_emails(email_id: int, limit: int = 10) -> list[dict]:
    """Find emails most similar to a given email (by embedding distance)."""
    cfg = get_config()
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        if not row:
            return []
        query_vec = _load_stored_embedding(conn, email_id)
        if query_vec is None:
            embedder = make_embedder(cfg.embeddings)
            query_vec = embedder.embed_query(embedding_input(row, cfg.embeddings.max_chars))
        hits = knn_email_ids(conn, query_vec, max(1, min(limit, 50)) + 1)
        results = []
        for result_id, distance in hits:
            if result_id == email_id:
                continue
            result_row = conn.execute("SELECT * FROM emails WHERE id = ?", (result_id,)).fetchone()
            if result_row:
                results.append(search.email_row_brief(result_row, {"distance": round(distance, 4)}))
        return results[:limit]
    finally:
        conn.close()


def _load_stored_embedding(conn: sqlite3.Connection, email_id: int) -> list[float] | None:
    try:
        vector_row = conn.execute(
            "SELECT embedding FROM vec_emails WHERE email_id = ?", (email_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not vector_row:
        return None
    dimensions = len(vector_row["embedding"]) // 4
    return list(struct.unpack(f"{dimensions}f", vector_row["embedding"]))
