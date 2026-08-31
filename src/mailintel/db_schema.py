"""Versioned SQLite schema scripts used by the database facade."""

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
_GUARDRAIL_TABLES = """
CREATE TABLE IF NOT EXISTS contacts (
    id         INTEGER PRIMARY KEY,
    addr       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL DEFAULT '',
    tier       TEXT NOT NULL DEFAULT 'unknown',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contact_interactions (
    id         INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    email_id   INTEGER REFERENCES emails(id) ON DELETE SET NULL,
    direction  TEXT NOT NULL DEFAULT 'inbound',
    timestamp  TEXT NOT NULL DEFAULT (datetime('now')),
    summary    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_contact_ints_contact ON contact_interactions(contact_id);
"""

_SCHEMA_V4 = f"""
ALTER TABLE emails ADD COLUMN guardrail_score   INTEGER DEFAULT 0;
ALTER TABLE emails ADD COLUMN guardrail_blocked  INTEGER DEFAULT 0;
ALTER TABLE emails ADD COLUMN guardrail_warnings TEXT;
{_GUARDRAIL_TABLES}
"""

# v5: explicit guardrail state so clean, unscanned, and failed scans are
# distinguishable to operators and agent-facing tools.
_SCHEMA_V5 = """
ALTER TABLE emails ADD COLUMN guardrail_status TEXT NOT NULL DEFAULT 'not_scanned';
"""

# v6: durable SMTP send-slot reservations for race-free rate limiting.
_SCHEMA_V6 = """
CREATE TABLE send_rate_slots (
    id         INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'reserved',
    error      TEXT
);
CREATE INDEX idx_send_rate_slots_time ON send_rate_slots(created_at, status);

INSERT INTO send_rate_slots (created_at, status)
SELECT created_at, 'reserved'
FROM audit_log
WHERE tool IN ('send_email', 'send_draft') AND error IS NULL;
"""
