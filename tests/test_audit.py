"""Audit log, send rate caps, and multi-account schema placeholders."""

from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage

import pytest

from mailintel import drafts, mcp_server, sender
from mailintel.enrich.pipeline import run_pipeline
from mailintel.ingest import ingest
from mailintel.mcp_tools import runtime
from tests.fakes import FakeEmbedder, FakeProvider


def _recent_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _setup(conn, cfg):
    ingest(conn, cfg)
    run_pipeline(conn, cfg, provider=FakeProvider(), embedder=FakeEmbedder())


@pytest.fixture
def served(conn, cfg, monkeypatch):
    _setup(conn, cfg)
    monkeypatch.setattr(runtime, "_config", cfg)
    return cfg


# --- audit log ---------------------------------------------------------------


def test_mcp_tool_call_logged(served, conn):
    mcp_server.get_stats()
    row = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row["tool"] == "get_stats"
    assert row["caller"]  # hostname:pid
    assert row["args"] == "{}"
    assert row["error"] is None


def test_mcp_tool_args_logged(served, conn):
    mcp_server.search_emails(query="kubernetes", limit=5)
    row = conn.execute("SELECT * FROM audit_log WHERE tool = 'search_emails'").fetchone()
    args = row["args"]
    assert '"query"' in args
    assert '"kubernetes"' in args
    assert '"limit"' in args


def test_audit_logs_error_returns(served, conn):
    result = mcp_server.get_email(999_999)
    assert result["error"]
    row = conn.execute("SELECT * FROM audit_log WHERE tool = 'get_email'").fetchone()
    assert row["error"] == result["error"]
    assert row["result_summary"] is None


def test_audit_args_truncated(served, conn):
    long_body = "x" * 5000
    mcp_server.create_draft(["a@b.com"], "subject", long_body)
    row = conn.execute("SELECT * FROM audit_log WHERE tool = 'create_draft'").fetchone()
    assert len(row["args"]) < 3000
    assert "redacted" in row["args"]
    assert long_body not in row["args"]


def test_audit_redacts_scan_content(served, conn):
    mcp_server.scan_email_mcp(
        "sender-secret@example.com", "subject-secret", "body-secret-unique-marker"
    )
    row = conn.execute(
        "SELECT args FROM audit_log WHERE tool = 'scan_email_mcp' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert "body-secret-unique-marker" not in row["args"]
    assert "subject-secret" not in row["args"]
    assert "sender-secret@example.com" not in row["args"]
    assert row["args"].count("redacted") == 3


def test_audit_result_summary_contains_only_event_metadata(served, conn):
    mcp_server.create_draft(["a@b.com"], "private-result-marker", "private body")
    mcp_server.get_events_since()
    row = conn.execute(
        "SELECT result_summary FROM audit_log WHERE tool = 'get_events_since' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert "private-result-marker" not in (row["result_summary"] or "")
    assert "private body" not in (row["result_summary"] or "")
    assert '"events_count"' in row["result_summary"]


def test_invalid_mcp_arguments_are_audited(served, conn):
    with pytest.raises(TypeError):
        mcp_server.get_email()
    row = conn.execute(
        "SELECT error FROM audit_log WHERE tool = 'get_email' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert "required argument" in row["error"]


def test_audit_intent_survives_result_finalize_failure(served, conn, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("audit finalize unavailable")

    monkeypatch.setattr(runtime, "_finish_audit", fail)
    with pytest.raises(RuntimeError, match="audit finalize unavailable"):
        mcp_server.create_draft(["private@example.com"], "subject", "body")

    audit = conn.execute(
        "SELECT error FROM audit_log WHERE tool = 'create_draft' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert audit["error"] == "in_progress"
    assert conn.execute("SELECT status FROM drafts").fetchone()[0] == "draft"


# --- rate caps ---------------------------------------------------------------


def test_send_email_rate_cap_blocks(conn, cfg):
    cfg.smtp.enabled = True
    cfg.smtp.host = "mail.example.com"
    cfg.smtp.max_sends_per_hour = 2

    # Seed two durable reservations.
    for _ in range(2):
        conn.execute(
            "INSERT INTO send_rate_slots (created_at, status) VALUES (?, 'reserved')",
            (_recent_timestamp(),),
        )
    conn.commit()

    with pytest.raises(sender.SendError, match="Rate limit exceeded"):
        sender.send_email(conn, cfg, ["a@b.com"], "s", "b")


def test_send_draft_rate_cap_blocks(conn, cfg, monkeypatch):
    cfg.smtp.enabled = True
    cfg.smtp.host = "mail.example.com"
    cfg.smtp.max_sends_per_hour = 1
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")

    d = drafts.create_draft(conn, ["a@b.com"], "s", "b")
    conn.execute(
        "INSERT INTO send_rate_slots (created_at, status) VALUES (?, 'reserved')",
        (_recent_timestamp(),),
    )
    conn.commit()

    result = drafts.send_draft(conn, cfg, d["draft_id"])
    assert "Rate limit exceeded" in result["error"]


def test_rate_cap_zero_is_unlimited(conn, cfg, monkeypatch):
    cfg.smtp.enabled = True
    cfg.smtp.host = "mail.example.com"
    cfg.smtp.max_sends_per_hour = 0

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, user, pw):
            pass

        def send_message(self, msg: EmailMessage):
            sent.append(msg)

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")

    # Seed many prior sends; cap is disabled so this should still go through.
    for _ in range(20):
        conn.execute(
            "INSERT INTO send_rate_slots (created_at, status) VALUES (?, 'reserved')",
            (_recent_timestamp(),),
        )
    conn.commit()

    sender.send_email(conn, cfg, ["a@example.com"], "s", "b")
    assert len(sent) == 1


# --- account column ----------------------------------------------------------


def test_ingested_email_has_default_account(conn, cfg):
    _setup(conn, cfg)
    rows = conn.execute("SELECT account FROM emails").fetchall()
    assert all(r["account"] == "default" for r in rows)


def test_events_and_drafts_carry_account(conn, cfg):
    _setup(conn, cfg)
    event = conn.execute("SELECT account FROM events LIMIT 1").fetchone()
    assert event["account"] == "default"

    d = drafts.create_draft(conn, ["a@b.com"], "s", "b")
    assert d["account"] == "default"


def test_audit_log_has_account_column(conn, cfg, monkeypatch):
    _setup(conn, cfg)
    monkeypatch.setattr(runtime, "_config", cfg)
    mcp_server.get_stats()
    row = conn.execute("SELECT account FROM audit_log LIMIT 1").fetchone()
    assert row["account"] == "default"
