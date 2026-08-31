"""SQLite projections created during Maildir ingestion."""

from __future__ import annotations

import sqlite3

from .config import Config
from .ingest_parser import _WS, ParsedEmail
from .threading_ import assign_thread

SNIPPET_LEN = 300


def insert_email(
    conn: sqlite3.Connection,
    parsed: ParsedEmail,
    folder: str,
    rel_path: str,
    is_sent: bool,
    is_read: bool,
    cfg: Config,
    account: str = "default",
) -> int:
    """Insert one parsed message and all of its relational projections."""
    thread_id = assign_thread(
        conn, parsed.message_id, parsed.subject, parsed.date_utc, parsed.refs, account
    )
    snippet = _WS.sub(" ", parsed.body_text)[:SNIPPET_LEN].strip()
    cursor = conn.execute(
        "INSERT INTO emails (message_id, thread_id, folder, maildir_path, subject, from_addr, "
        "from_name, date_utc, body_text, snippet, size, has_attachments, "
        "is_sent, is_read, account) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            parsed.message_id,
            thread_id,
            folder,
            rel_path,
            parsed.subject,
            parsed.from_addr,
            parsed.from_name,
            parsed.date_utc,
            parsed.body_text,
            snippet,
            parsed.size,
            int(bool(parsed.attachments)),
            int(is_sent),
            int(is_read),
            account,
        ),
    )
    email_id = cursor.lastrowid
    assert email_id is not None
    _insert_references(conn, email_id, parsed.refs)
    _insert_recipients(conn, email_id, parsed.recipients, account)
    _insert_attachments(conn, email_id, parsed.attachments, account)
    upsert_fts(conn, email_id, parsed)
    enqueue_jobs(conn, email_id, parsed, cfg)
    return email_id


def _insert_references(conn: sqlite3.Connection, email_id: int, refs: list[str]) -> None:
    for ref in refs:
        conn.execute(
            "INSERT INTO email_refs (email_id, ref_message_id) VALUES (?, ?)", (email_id, ref)
        )


def _insert_recipients(
    conn: sqlite3.Connection,
    email_id: int,
    recipients: list[tuple[str, str, str]],
    account: str,
) -> None:
    for kind, address, name in recipients:
        conn.execute(
            "INSERT INTO recipients (email_id, kind, addr, name, account) VALUES (?, ?, ?, ?, ?)",
            (email_id, kind, address, name, account),
        )


def _insert_attachments(
    conn: sqlite3.Connection,
    email_id: int,
    attachments: list[tuple[str, str, int]],
    account: str,
) -> None:
    for filename, mime, size in attachments:
        conn.execute(
            "INSERT INTO attachments (email_id, filename, mime, size, account) "
            "VALUES (?, ?, ?, ?, ?)",
            (email_id, filename, mime, size, account),
        )


def upsert_fts(conn: sqlite3.Connection, email_id: int, parsed: ParsedEmail) -> None:
    """Replace the FTS projection for an email."""
    conn.execute("DELETE FROM emails_fts WHERE rowid = ?", (email_id,))
    conn.execute(
        "INSERT INTO emails_fts (rowid, subject, body_text, from_text) VALUES (?, ?, ?, ?)",
        (email_id, parsed.subject, parsed.body_text, f"{parsed.from_name} {parsed.from_addr}"),
    )


def enqueue_jobs(conn: sqlite3.Connection, email_id: int, parsed: ParsedEmail, cfg: Config) -> None:
    """Queue configured enrichment stages, skipping attachments without PDFs."""
    stages = list(cfg.enrich.stages)
    if "attachments" in stages and not any(
        mime == "application/pdf" or filename.lower().endswith(".pdf")
        for filename, mime, _ in parsed.attachments
    ):
        stages.remove("attachments")
    for stage in stages:
        conn.execute(
            "INSERT OR IGNORE INTO pipeline_jobs (email_id, stage, status) "
            "VALUES (?, ?, 'pending')",
            (email_id, stage),
        )
