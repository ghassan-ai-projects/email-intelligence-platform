"""Enrichment stage for extracting text from supported email attachments."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

from ..attachment_store import (
    attachment_id_for_occurrence,
    attachment_text,
    extract_pdf_text,
    find_message_path,
    load_attachment,
    open_message,
)
from ..security import sanitize_text

def _is_pdf_attachment(filename: str, mime: str) -> bool:
    return mime == "application/pdf" or filename.lower().endswith(".pdf")


def extract_email_attachments(conn: sqlite3.Connection, email_id: int, maildir_root: Path) -> int:
    """Extract text from an email's PDF attachments into the attachments table."""
    path = find_message_path(conn, email_id, maildir_root)
    if not path:
        return 0
    msg = open_message(path)

    extracted = 0
    occurrences: Counter[str] = Counter()
    for part in msg.iter_attachments():
        filename = part.get_filename() or ""
        occurrence = occurrences[filename]
        occurrences[filename] += 1
        if not _is_pdf_attachment(filename, part.get_content_type()):
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        try:
            text = sanitize_text(extract_pdf_text(payload))
        except Exception:
            continue
        if text:
            attachment_id = attachment_id_for_occurrence(conn, email_id, filename, occurrence)
            if attachment_id is not None:
                cur = conn.execute(
                    "UPDATE attachments SET extracted_text = ? "
                    "WHERE id = ? AND extracted_text IS NULL",
                    (text, attachment_id),
                )
                extracted += cur.rowcount
    return extracted
