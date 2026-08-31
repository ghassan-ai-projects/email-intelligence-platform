"""Behavioral coverage for SMTP validation and attachment guardrails."""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from mailintel import drafts
from mailintel.ingest import ingest
from mailintel.sender import (
    SendError,
    SendOutcomeUnknown,
    _resolve_local_file,
    _validated_recipients,
    send_email,
)


def test_recipient_validation_handles_display_names_and_bad_values() -> None:
    assert _validated_recipients(['"Doe, Jane" <jane@example.com>'], []) == [
        "jane@example.com"
    ]
    with pytest.raises(SendError, match="Invalid recipient"):
        _validated_recipients(["not-an-address", "@example.com", "alice@"], [])
    with pytest.raises(SendError, match="No valid recipient"):
        _validated_recipients(["   "], [])
    with pytest.raises(SendError, match="allowed_recipients"):
        _validated_recipients(["jane@outside.example"], ["*@inside.example"])
    with pytest.raises(SendError, match="Invalid recipient"):
        _validated_recipients(["jane@example.com trailing"], [])


def test_resolve_local_file_requires_existing_whitelisted_path(tmp_path) -> None:
    missing = tmp_path / "missing.txt"
    with pytest.raises(SendError, match="not found"):
        _resolve_local_file(str(missing), [tmp_path])
    file_path = tmp_path / "report.txt"
    file_path.write_text("report")
    assert _resolve_local_file(str(file_path), [tmp_path]) == file_path.resolve()


def test_send_email_validates_host_credentials_and_cc(conn, cfg, monkeypatch) -> None:
    cfg.smtp.enabled = True
    with pytest.raises(SendError, match="smtp.host"):
        send_email(conn, cfg, ["a@example.com"], "subject", "body")

    cfg.smtp.host = "smtp.example.com"
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    with pytest.raises(SendError, match="credentials"):
        send_email(conn, cfg, ["a@example.com"], "subject", "body")

    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    with pytest.raises(SendError, match="Invalid recipient"):
        send_email(conn, cfg, ["a@example.com"], "subject", "body", cc=["bad"])


def test_send_email_supports_starttls_reply_headers_and_local_attachment(
    conn, cfg, monkeypatch, tmp_path
) -> None:
    ingest(conn, cfg)
    reply_id = conn.execute(
        "SELECT id FROM emails WHERE message_id = '<m1@example.com>'"
    ).fetchone()["id"]
    attachment = tmp_path / "report.txt"
    attachment.write_text("safe report")
    cfg.smtp.enabled = True
    cfg.smtp.host = "smtp.example.com"
    cfg.smtp.attachment_dirs = [tmp_path]
    cfg.smtp.allowed_recipients = ["*@example.com"]
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    sent: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["connection"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message: EmailMessage):
            sent["message"] = message

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    result = send_email(
        conn,
        cfg,
        ['"Doe, Jane" <jane@example.com>'],
        "Report",
        "See attached.",
        cc=["cc@example.com"],
        attachment_paths=[str(attachment)],
        in_reply_to_email_id=reply_id,
    )
    assert result["status"] == "sent"
    assert sent["starttls"] is True
    assert sent["login"] == ("me@example.com", "pw")
    message = sent["message"]
    assert isinstance(message, EmailMessage)
    assert message["In-Reply-To"] == "<m1@example.com>"
    assert message["References"] == "<m1@example.com>"
    assert [part.get_filename() for part in message.iter_attachments()] == ["report.txt"]


def test_send_email_rejects_missing_stored_attachment(conn, cfg, monkeypatch) -> None:
    cfg.smtp.enabled = True
    cfg.smtp.host = "smtp.example.com"
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    with pytest.raises(SendError, match="Stored attachment 999 not found"):
        send_email(conn, cfg, ["a@example.com"], "subject", "body", attachment_ids=[999])


class _RefusingSMTP:
    def __init__(self, _host, _port, timeout=None):
        _ = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self):
        pass

    def login(self, _username, _password):
        pass

    def send_message(self, _message):
        return self.refused


def test_all_smtp_refusals_do_not_emit_sent_event_or_consume_slot(conn, cfg, monkeypatch):
    cfg.smtp.enabled = True
    cfg.smtp.host = "smtp.example.com"
    cfg.smtp.max_sends_per_hour = 5
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    _RefusingSMTP.refused = {"a@example.com": (550, b"rejected")}
    monkeypatch.setattr("smtplib.SMTP", _RefusingSMTP)

    with pytest.raises(SendError, match="refused all"):
        send_email(conn, cfg, ["a@example.com"], "subject", "body")

    assert conn.execute("SELECT COUNT(*) FROM events WHERE type = 'email_sent'").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM send_rate_slots").fetchone()[0] == "failed"


def test_partial_smtp_refusal_marks_draft_unknown_without_retry(conn, cfg, monkeypatch):
    cfg.smtp.enabled = True
    cfg.smtp.host = "smtp.example.com"
    cfg.smtp.max_sends_per_hour = 5
    monkeypatch.setenv("EMAIL_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    _RefusingSMTP.refused = {"b@example.com": (550, b"rejected")}
    monkeypatch.setattr("smtplib.SMTP", _RefusingSMTP)
    draft = drafts.create_draft(conn, ["a@example.com", "b@example.com"], "subject", "body")

    result = drafts.send_draft(conn, cfg, draft["draft_id"])

    assert "unknown" in result["error"]
    assert conn.execute("SELECT status FROM drafts").fetchone()[0] == "unknown"
    assert conn.execute("SELECT COUNT(*) FROM events WHERE type = 'email_sent'").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM send_rate_slots").fetchone()[0] == "reserved"
