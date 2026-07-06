"""SQLite storage: connection setup, sqlite-vec loading, and schema migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

SCHEMA_VERSION = 4

_SCHEMA = """
CREATE TABLE emails (
    id              INTEGER PRIMARY KEY,
    message_id      TEXT NOT NULL UNIQUE,
    thread_id       INTEGER REFERENCES threads(id),
    folder          TEXT NOT NULL,
    maildir_path    TEXT NOT NULL,
    subject         TEXT NOT NULL DEFAULT '',
    from_addr       TEXT NOT NULL DEFAULT '',
    from_name       TEXT NOT NULL DEFAULT '',
    date_utc        TEXT NOT NULL,
    body_text       TEXT NOT NULL DEFAULT '',
    snippet         TEXT NOT NULL DEFAULT '',
    size            INTEGER NOT NULL DEFAULT 0,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    is_sent         INTEGER NOT NULL DEFAULT 0,
    is_read         INTEGER NOT NULL DEFAULT 0,
    language        TEXT,
    importance      INTEGER,
    sentiment       TEXT,
    summary         TEXT,
    enriched_at     TEXT
);
CREATE INDEX idx_emails_date   ON emails(date_utc);
CREATE INDEX idx_emails_from   ON emails(from_addr);
CREATE INDEX idx_emails_thread ON emails(thread_id);
CREATE INDEX idx_emails_folder ON emails(folder);

CREATE TABLE threads (
    id            INTEGER PRIMARY KEY,
    subject_norm  TEXT NOT NULL DEFAULT '',
    first_date    TEXT,
    last_date     TEXT,
    message_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_threads_subject ON threads(subject_norm);

CREATE TABLE email_refs (
    email_id       INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    ref_message_id TEXT NOT NULL
);
CREATE INDEX idx_refs_msgid ON email_refs(ref_message_id);
CREATE INDEX idx_refs_email ON email_refs(email_id);

CREATE TABLE recipients (
    email_id INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    kind     TEXT NOT NULL,
    addr     TEXT NOT NULL,
    name     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_recipients_addr  ON recipients(addr);
CREATE INDEX idx_recipients_email ON recipients(email_id);

CREATE TABLE attachments (
    id             INTEGER PRIMARY KEY,
    email_id       INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    filename       TEXT NOT NULL DEFAULT '',
    mime           TEXT NOT NULL DEFAULT '',
    size           INTEGER NOT NULL DEFAULT 0,
    extracted_text TEXT
);
CREATE INDEX idx_attachments_email ON attachments(email_id);

CREATE TABLE entities (
    id        INTEGER PRIMARY KEY,
    type      TEXT NOT NULL,
    name      TEXT NOT NULL,
    name_norm TEXT NOT NULL,
    UNIQUE(type, name_norm)
);

CREATE TABLE email_entities (
    email_id  INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE(email_id, entity_id)
);
CREATE INDEX idx_email_entities_entity ON email_entities(entity_id);

CREATE TABLE facts (
    id         INTEGER PRIMARY KEY,
    email_id   INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    fact       TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'info',
    due_date   TEXT,
    confidence REAL
);
CREATE INDEX idx_facts_category ON facts(category);

CREATE TABLE action_items (
    id          INTEGER PRIMARY KEY,
    email_id    INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    owner       TEXT,
    due_date    TEXT,
    status      TEXT NOT NULL DEFAULT 'open'
);
CREATE INDEX idx_action_items_status ON action_items(status);

CREATE TABLE pipeline_jobs (
    id         INTEGER PRIMARY KEY,
    email_id   INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    stage      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    updated_at TEXT,
    UNIQUE(email_id, stage)
);
CREATE INDEX idx_jobs_status ON pipeline_jobs(status, stage);

-- Tracks which Maildir files have been ingested. A message that exists in
-- several folders (e.g. Gmail labels) maps multiple rows to one email.
CREATE TABLE sync_state (
    folder   TEXT NOT NULL,
    uniq     TEXT NOT NULL,
    filename TEXT NOT NULL,
    email_id INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    PRIMARY KEY (folder, uniq)
);
CREATE INDEX idx_sync_state_email ON sync_state(email_id);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- Standalone FTS index; rowid == emails.id, maintained by ingest code.
CREATE VIRTUAL TABLE emails_fts USING fts5(subject, body_text, from_text);
"""


# v2: agent-loop support — append-only event log (cursor-consumed by agents),
# email tags + notes (write-back), and drafts (draft-first sending).
_SCHEMA_V2 = """
CREATE TABLE events (
    id         INTEGER PRIMARY KEY,
    type       TEXT NOT NULL,
    email_id   INTEGER,
    payload    TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_events_type ON events(type, id);

CREATE TABLE email_tags (
    email_id INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    UNIQUE(email_id, tag)
);
CREATE INDEX idx_email_tags_tag ON email_tags(tag);

CREATE TABLE drafts (
    id                    INTEGER PRIMARY KEY,
    to_addrs              TEXT NOT NULL,
    cc_addrs              TEXT NOT NULL DEFAULT '[]',
    subject               TEXT NOT NULL DEFAULT '',
    body                  TEXT NOT NULL DEFAULT '',
    in_reply_to_email_id  INTEGER,
    attachment_ids        TEXT NOT NULL DEFAULT '[]',
    status                TEXT NOT NULL DEFAULT 'draft',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    sent_at               TEXT
);

ALTER TABLE emails ADD COLUMN agent_notes TEXT;
ALTER TABLE action_items ADD COLUMN completed_at TEXT;
"""


# v3: audit log for every MCP tool call, per-hour send rate caps, and account
# column placeholder for future multi-account support.
_SCHEMA_V3 = """
CREATE TABLE audit_log (
    id             INTEGER PRIMARY KEY,
    tool           TEXT NOT NULL,
    args           TEXT NOT NULL DEFAULT '{}',
    caller         TEXT NOT NULL DEFAULT '',
    account        TEXT NOT NULL DEFAULT 'default',
    result_summary TEXT,
    error          TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_audit_log_tool_time    ON audit_log(tool, created_at);
CREATE INDEX idx_audit_log_account_time ON audit_log(account, created_at);

ALTER TABLE emails      ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE threads     ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE recipients  ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE attachments ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE facts       ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE action_items ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE drafts      ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE events      ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
ALTER TABLE sync_state  ADD COLUMN account TEXT NOT NULL DEFAULT 'default';
"""


# v4: guardrail columns on emails table + contacts table.
_SCHEMA_V4 = """
ALTER TABLE emails ADD COLUMN guardrail_score   INTEGER DEFAULT 0;
ALTER TABLE emails ADD COLUMN guardrail_blocked  INTEGER DEFAULT 0;
ALTER TABLE emails ADD COLUMN guardrail_warnings TEXT;

CREATE TABLE contacts (
    id         INTEGER PRIMARY KEY,
    addr       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL DEFAULT '',
    tier       TEXT NOT NULL DEFAULT 'unknown',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE contact_interactions (
    id         INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    email_id   INTEGER REFERENCES emails(id) ON DELETE SET NULL,
    direction  TEXT NOT NULL DEFAULT 'inbound',
    timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
    summary    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_contact_ints_contact ON contact_interactions(contact_id);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    _migrate(conn)
    # Import known contacts from JSON into the contacts table.
    _import_contacts_json(conn)
    return conn


def _import_contacts_json(conn: sqlite3.Connection) -> None:
    """Import contacts from ~/.mailintel/contacts.json into the SQLite contacts table."""
    import json
    from pathlib import Path
    from datetime import UTC, datetime

    path = Path.home() / ".mailintel" / "contacts.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    for entry in data.get("contacts", []):
        addr = entry.get("addr", "").lower().strip()
        if not addr:
            continue
        existing = conn.execute(
            "SELECT id FROM contacts WHERE addr = ?", (addr,)
        ).fetchone()
        if existing:
            # Update tier/name/notes if provided.
            updates = []
            params = []
            for field in ("tier", "name", "notes"):
                val = entry.get(field)
                if val:
                    updates.append(f"{field} = ?")
                    params.append(val)
            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(existing["id"])
                conn.execute(
                    f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?", params
                )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO contacts (addr, name, tier, notes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    addr,
                    entry.get("name", ""),
                    entry.get("tier", "unknown"),
                    entry.get("notes", ""),
                    now,
                    now,
                ),
            )
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    if version < 1:
        conn.executescript(_SCHEMA)
    if version < 2:
        conn.executescript(_SCHEMA_V2)
    if version < 3:
        conn.executescript(_SCHEMA_V3)
    if version < 4:
        conn.executescript(_SCHEMA_V4)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
