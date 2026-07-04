"""Attachment access and text extraction (PDF for now; OCR is future work)."""

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
    """Locate the current Maildir file for an email (flag renames move files)."""
    row = conn.execute("SELECT maildir_path FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not row:
        return None
    path = maildir_root / row["maildir_path"]
    if path.exists():
        return path
    state = conn.execute(
        "SELECT folder, filename FROM sync_state WHERE email_id = ? LIMIT 1", (email_id,)
    ).fetchone()
    if not state:
        return None
    candidates = list(maildir_root.rglob(state["filename"]))
    return candidates[0] if candidates else None


def _open_message(path: Path):
    with path.open("rb") as f:
        return email_lib.message_from_binary_file(f, policy=email.policy.default)


def load_attachment(
    conn: sqlite3.Connection, maildir_root: Path, attachment_id: int
) -> tuple[str, str, bytes] | None:
    """Return (filename, mime, raw bytes) for a stored attachment."""
    att = conn.execute(
        "SELECT email_id, filename, mime FROM attachments WHERE id = ?", (attachment_id,)
    ).fetchone()
    if not att:
        return None
    path = find_message_path(conn, att["email_id"], maildir_root)
    if not path:
        return None
    msg = _open_message(path)
    for part in msg.iter_attachments():
        if (part.get_filename() or "") == att["filename"]:
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


def extract_email_attachments(conn: sqlite3.Connection, email_id: int, maildir_root: Path) -> int:
    """Extract text from an email's PDF attachments into the attachments table."""
    path = find_message_path(conn, email_id, maildir_root)
    if not path:
        return 0
    msg = _open_message(path)

    extracted = 0
    for part in msg.iter_attachments():
        if part.get_content_type() != "application/pdf" and not (
            (part.get_filename() or "").lower().endswith(".pdf")
        ):
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        try:
            text = extract_pdf_text(payload)
        except Exception:
            continue
        if text:
            conn.execute(
                "UPDATE attachments SET extracted_text = ? "
                "WHERE email_id = ? AND filename = ? AND extracted_text IS NULL",
                (text, email_id, part.get_filename() or ""),
            )
            extracted += 1
    return extracted
