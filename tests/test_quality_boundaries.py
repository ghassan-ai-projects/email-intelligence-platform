"""Behavioral regression tests for the round-two quality findings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
import sqlite3

import pytest

from mailintel import actions, drafts, ingest as ingest_mod
from mailintel.config import EnrichConfig, GuardrailConfig
from mailintel.enrich.attachments import load_attachment
from mailintel.enrich.pipeline import run_embed_stage, run_pipeline, store_enrichment
from mailintel.events import emit, get_events_since
from mailintel.guardrail.contacts import ContactsDB
from mailintel.ingest import ingest
from mailintel.models import ActionItem, EnrichmentResult, Entities
from mailintel.search import search_emails
from tests.conftest import write_message


def test_invalid_new_contact_tier_is_rejected(conn):
    with pytest.raises(ValueError, match="invalid tier"):
        ContactsDB(conn).register_contact("new@example.com", tier="invalid")
    assert conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0


def test_empty_trusted_domains_preserve_exfiltration_override():
    cfg = GuardrailConfig(
        trusted_domains=[],
        exfiltration_guard={"enabled": False},
    )
    assert cfg.scanner_config()["exfiltration_guard"] == {"enabled": False, "trusted_domains": []}


def test_blank_full_text_query_is_empty(conn):
    assert search_emails(conn, query="   \"\"") == []


def test_repeated_completion_is_idempotent(conn, cfg):
    ingest(conn, cfg)
    email_id = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO action_items (email_id, description, account) VALUES (?, ?, ?)",
        (email_id, "Do the thing", "default"),
    )
    conn.commit()

    actions.complete_action_item(conn, cur.lastrowid)
    first_count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE type = 'action_item_completed'"
    ).fetchone()[0]
    actions.complete_action_item(conn, cur.lastrowid)
    second_count = conn.execute(
        "SELECT COUNT(*) FROM events WHERE type = 'action_item_completed'"
    ).fetchone()[0]
    assert first_count == 1
    assert second_count == first_count


def test_filtered_event_cursor_advances_past_unmatched_events(conn):
    emit(conn, "email_ingested", 1, {})
    emit(conn, "email_enriched", 1, {})
    result = get_events_since(conn, types=["draft_created"])
    assert result["events"] == []
    assert result["next_cursor"] == result["latest_cursor"] == 2


def test_reenrichment_preserves_completed_action_item(conn, cfg):
    ingest(conn, cfg)
    email_id = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    result = EnrichmentResult(
        action_items=[ActionItem(description="Follow up", owner="Alice", due_date="2025-06-10")],
        entities=Entities(),
    )
    store_enrichment(conn, email_id, result)
    action_id = conn.execute("SELECT id FROM action_items WHERE email_id = ?", (email_id,)).fetchone()[
        "id"
    ]
    actions.complete_action_item(conn, action_id)
    store_enrichment(conn, email_id, result)
    row = conn.execute(
        "SELECT id, status, completed_at FROM action_items WHERE email_id = ?", (email_id,)
    ).fetchone()
    assert dict(row) == {"id": action_id, "status": "done", "completed_at": row["completed_at"]}


def test_running_enrichment_job_blocks_embedding(conn, cfg):
    ingest(conn, cfg)
    target = conn.execute(
        "SELECT email_id FROM pipeline_jobs WHERE stage = 'enrich' LIMIT 1"
    ).fetchone()["email_id"]
    conn.execute(
        "UPDATE pipeline_jobs SET status = 'done' WHERE stage = 'enrich' AND email_id != ?",
        (target,),
    )
    conn.execute(
        "UPDATE pipeline_jobs SET status = 'running' WHERE stage = 'enrich' AND email_id = ?",
        (target,),
    )
    conn.commit()
    done, failed = run_embed_stage(conn, cfg, limit=100, embedder=_TwoDimEmbedder())
    assert done == 4
    assert failed == 0
    status = conn.execute(
        "SELECT status FROM pipeline_jobs WHERE stage = 'embed' AND email_id = ?", (target,)
    ).fetchone()["status"]
    assert status == "pending"


class _TwoDimEmbedder:
    dimensions = 8

    def embed_documents(self, texts):
        return [[0.0] * self.dimensions for _ in texts]

    def embed_query(self, text):
        return [0.0] * self.dimensions


def test_draft_transport_failure_becomes_unknown(conn, cfg, monkeypatch):
    draft = drafts.create_draft(conn, ["a@example.com"], "subject", "body")

    def fail(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(drafts, "send_email", fail)
    result = drafts.send_draft(conn, cfg, draft["draft_id"])
    assert "unknown" in result["error"]
    assert conn.execute("SELECT status FROM drafts").fetchone()["status"] == "unknown"


def test_stale_sending_draft_is_reconciled_without_retry(conn, cfg):
    draft = drafts.create_draft(conn, ["a@example.com"], "subject", "body")
    stale = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE drafts SET status = 'sending', updated_at = ? WHERE id = ?",
        (stale, draft["draft_id"]),
    )
    conn.commit()
    result = drafts.send_draft(conn, cfg, draft["draft_id"])
    assert "unknown" in result["error"]
    assert conn.execute("SELECT status FROM drafts").fetchone()["status"] == "unknown"


def test_duplicate_attachment_names_are_identity_safe(conn, cfg, maildir):
    message = EmailMessage()
    message["Message-ID"] = "<duplicates@example.com>"
    message["Subject"] = "Duplicate attachments"
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Me <me@example.com>"
    message["Date"] = "Thu, 05 Jun 2025 10:00:00 +0000"
    message.set_content("body")
    message.add_attachment(b"first", maintype="text", subtype="plain", filename="same.txt")
    message.add_attachment(b"second", maintype="text", subtype="plain", filename="same.txt")
    write_message(maildir, "9000.duplicates.host:2,", message.as_bytes())
    ingest(conn, cfg)
    rows = conn.execute(
        "SELECT id FROM attachments WHERE email_id = "
        "(SELECT id FROM emails WHERE message_id = '<duplicates@example.com>') ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert load_attachment(conn, cfg.maildir.path, rows[0]["id"])[2] == b"first"
    assert load_attachment(conn, cfg.maildir.path, rows[1]["id"])[2] == b"second"


def test_duplicate_copy_in_sent_folder_updates_sent_projection(conn, cfg, maildir):
    ingest(conn, cfg)
    source = maildir / "cur" / "1000.k8s.host:2,S"
    write_message(maildir / ".Sent", "9001.copy.host:2,S", source.read_bytes())
    ingest(conn, cfg)
    row = conn.execute(
        "SELECT folder, is_sent FROM emails WHERE message_id = '<m1@example.com>'"
    ).fetchone()
    assert row["folder"] == "INBOX"
    assert row["is_sent"] == 1
    (maildir / ".Sent" / "cur" / "9001.copy.host:2,S").unlink()
    ingest(conn, cfg)
    row = conn.execute(
        "SELECT folder, is_sent FROM emails WHERE message_id = '<m1@example.com>'"
    ).fetchone()
    assert row["folder"] == "INBOX"
    assert row["is_sent"] == 0


def test_malformed_message_is_counted_without_hiding_valid_mail(conn, cfg, monkeypatch, maildir):
    write_message(maildir, "9002.bad.host:2,", b"bad")
    original = ingest_mod.parse_message

    def parse(path):
        if path.name.startswith("9002"):
            raise ValueError("malformed")
        return original(path)

    monkeypatch.setattr(ingest_mod, "parse_message", parse)
    stats = ingest(conn, cfg)
    assert stats.parse_errors == 1
    assert conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0] == 5


def test_config_rejects_unknown_enrichment_stage():
    with pytest.raises(ValueError, match="unknown enrichment stage"):
        EnrichConfig(stages=["enrich", "typo"])


def test_pipeline_requires_clean_caller_transaction(conn, cfg):
    conn.execute("INSERT INTO contacts (addr) VALUES (?)", ("sentinel@example.com",))
    with pytest.raises(RuntimeError, match="clean connection"):
        run_pipeline(conn, cfg, provider=object(), embedder=object())
    assert conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE addr = 'sentinel@example.com'"
    ).fetchone()[0] == 1
    conn.rollback()


def test_ingest_propagates_guardrail_persistence_failures(conn, cfg, monkeypatch):
    def fail(*_args):
        raise sqlite3.OperationalError("db write failed")

    monkeypatch.setattr(ingest_mod, "store_guardrail_result", fail)
    with pytest.raises(sqlite3.OperationalError, match="db write failed"):
        ingest(conn, cfg)
