"""Shared access to Maildir attachments and bounded text extraction."""

from __future__ import annotations

import email as email_lib
import email.policy
import io
import sqlite3
from pathlib import Path

MAX_PDF_PAGES = 20
MAX_TEXT_CHARS = 20_000

TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_EXACT = {"application/json", "application/xml", "application/csv"}


def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    chunks: list[str] = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks).strip()[:MAX_TEXT_CHARS]


def find_message_path(conn: sqlite3.Connection, email_id: int, maildir_root: Path) -> Path | None:
    """Locate the current Maildir file for an email, including renamed copies."""
    row = conn.execute("SELECT maildir_path FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not row:
        return None
    path = maildir_root / row["maildir_path"]
    if path.exists():
        return path
    states = conn.execute(
        "SELECT folder, filename FROM sync_state WHERE email_id = ? ORDER BY rowid", (email_id,)
    ).fetchall()
    if not states:
        return None
    from .ingest_maildir import iter_maildirs

    folders = dict(iter_maildirs(maildir_root))
    for state in states:
        folder = folders.get(state["folder"])
        if folder is None:
            continue
        for subdirectory in ("cur", "new"):
            candidate = folder / subdirectory / state["filename"]
            if candidate.is_file():
                return candidate
    return None


def open_message(path: Path):
    with path.open("rb") as message_file:
        return email_lib.message_from_binary_file(message_file, policy=email.policy.default)


def attachment_occurrence(
    conn: sqlite3.Connection, email_id: int, filename: str, attachment_id: int
) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM attachments "
        "WHERE email_id = ? AND filename = ? AND id <= ?",
        (email_id, filename, attachment_id),
    ).fetchone()
    return row[0] - 1


def attachment_id_for_occurrence(
    conn: sqlite3.Connection, email_id: int, filename: str, occurrence: int
) -> int | None:
    row = conn.execute(
        "SELECT id FROM attachments WHERE email_id = ? AND filename = ? "
        "ORDER BY id LIMIT 1 OFFSET ?",
        (email_id, filename, occurrence),
    ).fetchone()
    return row["id"] if row else None


def load_attachment(
    conn: sqlite3.Connection, maildir_root: Path, attachment_id: int
) -> tuple[str, str, bytes] | None:
    """Return (filename, mime, raw bytes) for a stored attachment."""
    att = conn.execute(
        "SELECT id, email_id, filename, mime FROM attachments WHERE id = ?", (attachment_id,)
    ).fetchone()
    if not att:
        return None
    path = find_message_path(conn, att["email_id"], maildir_root)
    if not path:
        return None
    msg = open_message(path)
    occurrence = attachment_occurrence(conn, att["email_id"], att["filename"], att["id"])
    matching_parts = [
        part
        for part in msg.iter_attachments()
        if (part.get_filename() or "") == att["filename"]
    ]
    if 0 <= occurrence < len(matching_parts):
        part = matching_parts[occurrence]
        payload = part.get_payload(decode=True) or b""
        return att["filename"], att["mime"], payload
    return None


def attachment_text(filename: str, mime: str, data: bytes) -> str | None:
    """Best-effort text extraction for a single attachment; None if binary."""
    if mime == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            return extract_pdf_text(data)
        except Exception:
            return None
    if mime.startswith(TEXT_MIME_PREFIXES) or mime in TEXT_MIME_EXACT:
        return data.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
    return None
