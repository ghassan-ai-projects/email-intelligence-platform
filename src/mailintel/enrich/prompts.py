"""Prompt construction for the single structured enrichment call per email."""

from __future__ import annotations

import sqlite3

from ..config import LLMConfig

ENRICH_SYSTEM = """\
You are an email analysis engine inside a local email intelligence platform.
Given one email, return ONLY a JSON object with exactly these fields:

{
  "language": "ISO 639-1 code of the email body language, e.g. 'en', 'ar'",
  "summary": "1-3 sentence factual summary of what the email says or asks",
  "importance": 1-5 (1=bulk/marketing, 2=FYI, 3=normal, 4=needs attention, 5=urgent/critical),
  "sentiment": "positive" | "neutral" | "negative",
  "action_items": [
    {"description": "...", "owner": "person responsible or null", "due_date": "YYYY-MM-DD or null"}
  ],
  "entities": {
    "people": ["full names of people mentioned (not email addresses)"],
    "companies": ["organizations mentioned"],
    "projects": ["projects, products or initiatives mentioned"],
    "topics": ["2-5 short topical tags, lowercase"]
  },
  "facts": [
    {"fact": "one self-contained factual statement worth remembering",
     "category": "deadline" | "decision" | "change" | "commitment" | "info",
     "due_date": "YYYY-MM-DD or null",
     "confidence": 0.0-1.0}
  ]
}

Rules:
- Extract only what the email states; never invent details.
- Facts must be understandable without reading the email (include who/what/when).
- Automated notifications and marketing usually have no action items and few facts.
- Empty lists are fine. Output raw JSON only, no markdown fences, no commentary.
"""


def build_enrich_prompt(conn: sqlite3.Connection, email_row: sqlite3.Row, cfg: LLMConfig) -> str:
    recipients = conn.execute(
        "SELECT kind, addr, name FROM recipients WHERE email_id = ?", (email_row["id"],)
    ).fetchall()
    to_line = ", ".join(
        f'{r["name"]} <{r["addr"]}>'.strip() for r in recipients if r["kind"] == "to"
    )

    body = email_row["body_text"][: cfg.max_body_chars]

    parts = [
        f'From: {email_row["from_name"]} <{email_row["from_addr"]}>'.strip(),
        f"To: {to_line}",
        f'Date: {email_row["date_utc"]} UTC',
        f'Subject: {email_row["subject"]}',
        f'Folder: {email_row["folder"]}',
        "",
        body if body else "(empty body)",
    ]

    att_rows = conn.execute(
        "SELECT filename, mime, extracted_text FROM attachments WHERE email_id = ?",
        (email_row["id"],),
    ).fetchall()
    for att in att_rows:
        parts.append(f'\n--- Attachment: {att["filename"]} ({att["mime"]}) ---')
        if att["extracted_text"]:
            parts.append(att["extracted_text"][: cfg.max_attachment_chars])

    return "\n".join(parts)
