"""Parser edge cases for malformed and minimally specified RFC822 messages."""

from __future__ import annotations

from email.message import EmailMessage

from mailintel.ingest_parser import (
    _addresses,
    _clean_text,
    _extract_body,
    _parse_date,
    _parse_refs,
    parse_message,
)


def test_parse_message_generates_id_and_uses_file_time_for_invalid_date(tmp_path) -> None:
    message = EmailMessage()
    message["Subject"] = "Minimal message"
    message["From"] = "Alice <ALICE@example.com>"
    message["To"] = "Me <me@example.com>"
    message["Date"] = "not a valid date"
    message.set_content("hello")
    path = tmp_path / "message.eml"
    path.write_bytes(message.as_bytes())

    parsed = parse_message(path)
    assert parsed.message_id.startswith("<mailintel-")
    assert parsed.from_addr == "alice@example.com"
    assert parsed.body_text == "hello"
    assert parsed.size == path.stat().st_size
    assert _parse_date(message, path) == parsed.date_utc


def test_parser_helpers_normalize_references_addresses_and_blank_lines() -> None:
    message = EmailMessage()
    message["References"] = "<a@example.com> <a@example.com> <b@example.com>"
    message["In-Reply-To"] = "<b@example.com> <c@example.com>"
    message["To"] = "One <one@example.com>, invalid, Two <two@example.com>"
    assert _parse_refs(message) == ["<a@example.com>", "<b@example.com>", "<c@example.com>"]
    assert _addresses(message, "To") == [("one@example.com", "One"), ("two@example.com", "Two")]
    assert _clean_text("first\n\n\nsecond\n") == "first\n\nsecond"


def test_extract_body_returns_empty_for_message_without_body() -> None:
    assert _extract_body(EmailMessage()) == ""

