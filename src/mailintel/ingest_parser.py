"""RFC822 message parsing for Maildir ingestion."""

from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import html2text

from .security import sanitize_text

_WS = re.compile(r"\s+")
_MSGID = re.compile(r"<[^<>]+>")


@dataclass
class ParsedEmail:
    message_id: str
    subject: str
    from_addr: str
    from_name: str
    date_utc: str
    body_text: str
    refs: list[str]
    recipients: list[tuple[str, str, str]]
    attachments: list[tuple[str, str, int]]
    size: int


def _html_to_text(html: str) -> str:
    converter = html2text.HTML2Text()
    converter.ignore_links = True
    converter.ignore_images = True
    converter.body_width = 0
    return converter.handle(html)


def _clean_text(text: str) -> str:
    """Collapse blank-line noise in text derived from HTML."""
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    blank_lines = 0
    for line in lines:
        blank_lines = blank_lines + 1 if not line else 0
        if blank_lines <= 1:
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def _extract_body(msg: EmailMessage) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        part = None
    if part is None:
        return ""
    try:
        content = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        if not isinstance(payload, bytes):
            payload = b""
        content = payload.decode("utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        content = _html_to_text(content)
    return _clean_text(content)


def _parse_refs(msg: EmailMessage) -> list[str]:
    raw = (msg.get("References") or "") + " " + (msg.get("In-Reply-To") or "")
    references: list[str] = []
    for message_id in _MSGID.findall(raw):
        if message_id not in references:
            references.append(message_id)
    return references


def _parse_date(msg: EmailMessage, path: Path) -> str:
    try:
        raw_date = msg.get("Date")
        if not isinstance(raw_date, str):
            raise ValueError("missing Date header")
        parsed = email.utils.parsedate_to_datetime(raw_date)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
    except Exception:
        parsed = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _addresses(msg: EmailMessage, header: str) -> list[tuple[str, str]]:
    addresses = []
    for name, address in email.utils.getaddresses([msg.get(header, "")]):
        if address:
            addresses.append((address.lower(), name))
    return addresses


def parse_message(path: Path) -> ParsedEmail:
    """Parse and sanitize one RFC822 message from a Maildir path."""
    with path.open("rb") as message_file:
        msg: EmailMessage = email.message_from_binary_file(
            message_file, policy=email.policy.default
        )

    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:
        with path.open("rb") as message_file:
            digest = hashlib.sha256(message_file.read()).hexdigest()[:32]
            message_id = f"<mailintel-{digest}>"

    from_pairs = _addresses(msg, "From")
    from_addr, from_name = from_pairs[0] if from_pairs else ("", "")
    recipients = [
        (kind, address, name)
        for kind in ("to", "cc", "bcc")
        for address, name in _addresses(msg, kind)
    ]

    attachments = []
    try:
        for part in msg.iter_attachments():
            payload = part.get_payload(decode=True) or b""
            attachments.append((part.get_filename() or "", part.get_content_type(), len(payload)))
    except Exception:
        pass

    return ParsedEmail(
        message_id=message_id,
        subject=sanitize_text(_WS.sub(" ", msg.get("Subject") or "").strip()),
        from_addr=from_addr,
        from_name=sanitize_text(from_name),
        date_utc=_parse_date(msg, path),
        body_text=sanitize_text(_extract_body(msg)),
        refs=_parse_refs(msg),
        recipients=[(kind, address, sanitize_text(name)) for kind, address, name in recipients],
        attachments=attachments,
        size=path.stat().st_size,
    )
