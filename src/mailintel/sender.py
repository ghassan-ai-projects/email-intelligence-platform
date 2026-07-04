"""Outgoing mail via SMTP — opt-in, with guardrails.

Because sending can be triggered by an agent (and agents read untrusted email
content), this module enforces:
- `smtp.enabled` must be explicitly true in the config (default: off);
- every recipient must match `smtp.allowed_recipients` when the list is set;
- local-file attachments are restricted to `smtp.attachment_dirs`;
- stored email attachments can always be forwarded by id (already in the store).
"""

from __future__ import annotations

import smtplib
import sqlite3
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path

from .config import Config
from .enrich.attachments import load_attachment
from .events import emit
from .security import recipient_allowed


class SendError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def check_send_rate(conn: sqlite3.Connection, cfg: Config) -> None:
    """Block if send_email/send_draft calls in the last hour exceed the cap."""
    cap = cfg.smtp.max_sends_per_hour
    if cap <= 0:
        return
    since = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    count = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE tool IN ('send_email', 'send_draft') "
        "AND created_at > ?",
        (since,),
    ).fetchone()[0]
    if count >= cap:
        raise SendError(
            f"Rate limit exceeded: {cap} send(s) per hour. "
            "Wait or raise smtp.max_sends_per_hour."
        )


def _validated_recipients(raw: list[str], allowed: list[str]) -> list[str]:
    addrs = [a for _, a in getaddresses(raw) if a]
    if not addrs:
        raise SendError("No valid recipient addresses given")
    for addr in addrs:
        if not recipient_allowed(addr, allowed):
            raise SendError(
                f"Recipient '{addr}' is not covered by smtp.allowed_recipients — "
                f"refusing to send (guardrail against injected exfiltration)"
            )
    return addrs


def _resolve_local_file(path_str: str, allowed_dirs: list[Path]) -> Path:
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise SendError(f"Attachment file not found: {path}")
    if not any(path.is_relative_to(d.resolve()) for d in allowed_dirs):
        raise SendError(
            f"File '{path}' is outside smtp.attachment_dirs — refusing to attach "
            f"(guardrail: only whitelisted directories may be sent)"
        )
    return path


def send_email(
    conn: sqlite3.Connection,
    cfg: Config,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    attachment_ids: list[int] | None = None,
    attachment_paths: list[str] | None = None,
    in_reply_to_email_id: int | None = None,
) -> dict:
    smtp = cfg.smtp
    if not smtp.enabled:
        raise SendError(
            "Sending is disabled. Set [smtp] enabled = true in the config "
            "(plus host/credentials) to allow it."
        )
    if not smtp.host:
        raise SendError("smtp.host is not configured")
    check_send_rate(conn, cfg)
    username, password = smtp.username, smtp.password
    if not username or not password:
        raise SendError(
            f"SMTP credentials missing: set {smtp.username_env} and "
            f"{smtp.password_env} (e.g. in ~/.mailintel/.env)"
        )

    to_addrs = _validated_recipients(to, smtp.allowed_recipients)
    cc_addrs = _validated_recipients(cc, smtp.allowed_recipients) if cc else []

    msg = EmailMessage()
    msg["From"] = smtp.from_addr or username
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["Subject"] = subject
    msg.set_content(body)

    if in_reply_to_email_id is not None:
        row = conn.execute(
            "SELECT message_id, subject FROM emails WHERE id = ?", (in_reply_to_email_id,)
        ).fetchone()
        if row:
            msg["In-Reply-To"] = row["message_id"]
            msg["References"] = row["message_id"]

    attached: list[str] = []
    for att_id in attachment_ids or []:
        loaded = load_attachment(conn, cfg.maildir.path, att_id)
        if not loaded:
            raise SendError(f"Stored attachment {att_id} not found")
        filename, mime, data = loaded
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(
            data, maintype=maintype, subtype=subtype or "octet-stream",
            filename=filename or f"attachment-{att_id}",
        )
        attached.append(filename or str(att_id))

    if attachment_paths:
        if not smtp.attachment_dirs:
            raise SendError(
                "Local-file attachments are disabled: configure smtp.attachment_dirs"
            )
        for path_str in attachment_paths:
            path = _resolve_local_file(path_str, smtp.attachment_dirs)
            import mimetypes

            mime, _ = mimetypes.guess_type(path.name)
            maintype, _, subtype = (mime or "application/octet-stream").partition("/")
            msg.add_attachment(
                path.read_bytes(), maintype=maintype, subtype=subtype or "octet-stream",
                filename=path.name,
            )
            attached.append(path.name)

    with smtplib.SMTP(smtp.host, smtp.port, timeout=60) as server:
        if smtp.starttls:
            server.starttls()
        server.login(username, password)
        server.send_message(msg)

    # Use the account of the email being replied to, if any, otherwise default.
    account = "default"
    if in_reply_to_email_id is not None:
        row = conn.execute("SELECT account FROM emails WHERE id = ?", (in_reply_to_email_id,)).fetchone()
        if row:
            account = row["account"]
    emit(conn, "email_sent", in_reply_to_email_id, {
        "to": to_addrs, "cc": cc_addrs, "subject": subject, "attachments": attached,
    }, account=account)
    conn.commit()
    return {
        "status": "sent",
        "from": msg["From"],
        "to": to_addrs,
        "cc": cc_addrs,
        "subject": subject,
        "attachments": attached,
    }
