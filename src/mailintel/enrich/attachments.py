"""Attachment text extraction (PDF for now; OCR is future work)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MAX_PDF_PAGES = 20
MAX_TEXT_CHARS = 20_000


def extract_pdf_text(data: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    chunks: list[str] = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks).strip()[:MAX_TEXT_CHARS]


def extract_email_attachments(
    conn: sqlite3.Connection, email_id: int, maildir_root: Path
) -> int:
    """Re-open the message file and extract text from its PDF attachments."""
    import email as email_lib
    import email.policy

    row = conn.execute(
        "SELECT maildir_path FROM emails WHERE id = ?", (email_id,)
    ).fetchone()
    if not row:
        return 0
    path = maildir_root / row["maildir_path"]
    if not path.exists():
        # Flag renames move Maildir files; find the current name via sync_state.
        state = conn.execute(
            "SELECT folder, filename FROM sync_state WHERE email_id = ? LIMIT 1", (email_id,)
        ).fetchone()
        if not state:
            return 0
        candidates = list(maildir_root.rglob(state["filename"]))
        if not candidates:
            return 0
        path = candidates[0]

    with open(path, "rb") as f:
        msg = email_lib.message_from_binary_file(f, policy=email.policy.default)

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
