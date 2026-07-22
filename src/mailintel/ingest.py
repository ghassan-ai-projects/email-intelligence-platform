"""Maildir ingestion: scan folders, parse RFC822 messages, index into SQLite + FTS.

Incremental: files already seen (tracked in sync_state by Maildir unique name) are
skipped; flag-only renames update read status without re-parsing; files that
disappear remove their emails once no folder still holds a copy.
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import re
import sqlite3
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import html2text

from .config import Config
from .events import emit
from .guardrail.db import store_guardrail_result
from .guardrail.scanner_wrapper import scan_email_from_config
from .security import sanitize_text
from .threading_ import assign_thread, refresh_thread_stats

_WS = re.compile(r"\s+")
_MSGID = re.compile(r"<[^<>]+>")

SNIPPET_LEN = 300


@dataclass
class IngestStats:
    new: int = 0
    updated_flags: int = 0
    deleted: int = 0
    skipped_folders: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "new": self.new,
            "updated_flags": self.updated_flags,
            "deleted": self.deleted,
            "skipped_folders": self.skipped_folders,
        }


@dataclass
class ParsedEmail:
    message_id: str
    subject: str
    from_addr: str
    from_name: str
    date_utc: str
    body_text: str
    refs: list[str]
    recipients: list[tuple[str, str, str]]  # (kind, addr, name)
    attachments: list[tuple[str, str, int]]  # (filename, mime, size)
    size: int


def _html_to_text(html: str) -> str:
    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    return h.handle(html)


def _clean_text(text: str) -> str:
    # Collapse the blank-line noise typical of HTML-derived text.
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    blank = 0
    for ln in lines:
        blank = blank + 1 if not ln else 0
        if blank <= 1:
            out.append(ln)
    return "\n".join(out).strip()


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
    seen: list[str] = []
    for m in _MSGID.findall(raw):
        if m not in seen:
            seen.append(m)
    return seen


def _parse_date(msg: EmailMessage, path: Path) -> str:
    try:
        raw_date = msg.get("Date")
        if not isinstance(raw_date, str):
            raise ValueError("missing Date header")
        dt = email.utils.parsedate_to_datetime(raw_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    except Exception:
        dt = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _addresses(msg: EmailMessage, header: str) -> list[tuple[str, str]]:
    out = []
    for name, addr in email.utils.getaddresses([msg.get(header, "")]):
        if addr:
            out.append((addr.lower(), name))
    return out


def parse_message(path: Path) -> ParsedEmail:
    with path.open("rb") as f:
        msg: EmailMessage = email.message_from_binary_file(f, policy=email.policy.default)

    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:
        with path.open("rb") as f:
            message_id = f"<mailintel-{hashlib.sha256(f.read()).hexdigest()[:32]}>"

    from_pairs = _addresses(msg, "From")
    from_addr, from_name = from_pairs[0] if from_pairs else ("", "")

    recipients = []
    for kind in ("to", "cc", "bcc"):
        for addr, name in _addresses(msg, kind):
            recipients.append((kind, addr, name))

    attachments = []
    try:
        for part in msg.iter_attachments():
            payload = part.get_payload(decode=True) or b""
            attachments.append((part.get_filename() or "", part.get_content_type(), len(payload)))
    except Exception:
        pass

    body = _extract_body(msg)

    return ParsedEmail(
        message_id=message_id,
        # sanitize_text strips control/invisible chars (prompt-injection hiding).
        subject=sanitize_text(_WS.sub(" ", msg.get("Subject") or "").strip()),
        from_addr=from_addr,
        from_name=sanitize_text(from_name),
        date_utc=_parse_date(msg, path),
        body_text=sanitize_text(body),
        refs=_parse_refs(msg),
        recipients=[(k, a, sanitize_text(n)) for k, a, n in recipients],
        attachments=attachments,
        size=path.stat().st_size,
    )


def iter_maildirs(root: Path) -> list[tuple[str, Path]]:
    """Find Maildir folders under root. Supports nested dirs and Maildir++ dot-names."""
    found: list[tuple[str, Path]] = []

    def is_maildir(p: Path) -> bool:
        return (p / "cur").is_dir() and (p / "new").is_dir()

    def folder_name(p: Path) -> str:
        rel = p.relative_to(root)
        if rel == Path():
            return "INBOX"
        parts: list[str] = []
        for seg in rel.parts:
            seg = seg.lstrip(".")
            parts.extend(s for s in seg.split(".") if s)
        return "/".join(parts) or "INBOX"

    if is_maildir(root):
        found.append((folder_name(root), root))
    for p in sorted(root.rglob("*")):
        if p.is_dir() and p.name not in ("cur", "new", "tmp") and is_maildir(p):
            if any(seg in ("cur", "new", "tmp") for seg in p.relative_to(root).parts[:-1]):
                continue
            found.append((folder_name(p), p))
    return found


def _split_flags(filename: str) -> tuple[str, bool]:
    """Return (maildir unique name, seen flag) for a Maildir filename."""
    uniq, _, info = filename.partition(":")
    seen = "S" in info.partition(",")[2] if info.startswith("2") else False
    return uniq, seen


def _segment_match(folder: str, names: list[str]) -> bool:
    segs = {s.lower() for s in folder.split("/")}
    return any(n.lower() in segs for n in names)


def _fts_upsert(conn: sqlite3.Connection, email_id: int, parsed: ParsedEmail) -> None:
    conn.execute("DELETE FROM emails_fts WHERE rowid = ?", (email_id,))
    conn.execute(
        "INSERT INTO emails_fts (rowid, subject, body_text, from_text) VALUES (?, ?, ?, ?)",
        (email_id, parsed.subject, parsed.body_text, f"{parsed.from_name} {parsed.from_addr}"),
    )


def _enqueue_jobs(
    conn: sqlite3.Connection, email_id: int, parsed: ParsedEmail, cfg: Config
) -> None:
    stages = list(cfg.enrich.stages)
    if "attachments" in stages and not any(
        mime == "application/pdf" or fn.lower().endswith(".pdf")
        for fn, mime, _ in parsed.attachments
    ):
        stages.remove("attachments")
    for stage in stages:
        conn.execute(
            "INSERT OR IGNORE INTO pipeline_jobs (email_id, stage, status) "
            "VALUES (?, ?, 'pending')",
            (email_id, stage),
        )


def _insert_email(
    conn: sqlite3.Connection,
    parsed: ParsedEmail,
    folder: str,
    rel_path: str,
    is_sent: bool,
    is_read: bool,
    cfg: Config,
    account: str = "default",
) -> int:
    thread_id = assign_thread(
        conn, parsed.message_id, parsed.subject, parsed.date_utc, parsed.refs, account
    )
    snippet = _WS.sub(" ", parsed.body_text)[:SNIPPET_LEN].strip()
    cur = conn.execute(
        "INSERT INTO emails (message_id, thread_id, folder, maildir_path, subject, from_addr, "
        "from_name, date_utc, body_text, snippet, size, has_attachments, "
        "is_sent, is_read, account) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            parsed.message_id,
            thread_id,
            folder,
            rel_path,
            parsed.subject,
            parsed.from_addr,
            parsed.from_name,
            parsed.date_utc,
            parsed.body_text,
            snippet,
            parsed.size,
            int(bool(parsed.attachments)),
            int(is_sent),
            int(is_read),
            account,
        ),
    )
    email_id = cur.lastrowid
    assert email_id is not None
    for ref in parsed.refs:
        conn.execute(
            "INSERT INTO email_refs (email_id, ref_message_id) VALUES (?, ?)", (email_id, ref)
        )
    for kind, addr, name in parsed.recipients:
        conn.execute(
            "INSERT INTO recipients (email_id, kind, addr, name, account) VALUES (?, ?, ?, ?, ?)",
            (email_id, kind, addr, name, account),
        )
    for fn, mime, size in parsed.attachments:
        conn.execute(
            "INSERT INTO attachments (email_id, filename, mime, size, account) "
            "VALUES (?, ?, ?, ?, ?)",
            (email_id, fn, mime, size, account),
        )
    _fts_upsert(conn, email_id, parsed)
    _enqueue_jobs(conn, email_id, parsed, cfg)
    return email_id


def ingest(conn: sqlite3.Connection, cfg: Config) -> IngestStats:
    root = cfg.maildir.path
    if not root.is_dir():
        raise FileNotFoundError(f"Maildir root not found: {root}")

    stats = IngestStats()
    touched_threads: set[int] = set()
    seen: set[tuple[str, str]] = set()

    known = {
        (r["folder"], r["uniq"]): (r["filename"], r["email_id"])
        for r in conn.execute("SELECT folder, uniq, filename, email_id FROM sync_state")
    }

    for folder, fpath in iter_maildirs(root):
        if _segment_match(folder, cfg.maildir.exclude_folders):
            stats.skipped_folders.append(folder)
            continue
        is_sent = _segment_match(folder, cfg.maildir.sent_folders)

        for sub in ("cur", "new"):
            for f in sorted((fpath / sub).iterdir()):
                if not f.is_file() or f.name.startswith("."):
                    continue
                uniq, is_read = _split_flags(f.name)
                key = (folder, uniq)
                seen.add(key)

                if key in known:
                    old_filename, email_id = known[key]
                    if old_filename != f.name:
                        conn.execute(
                            "UPDATE sync_state SET filename = ? WHERE folder = ? AND uniq = ?",
                            (f.name, folder, uniq),
                        )
                        conn.execute(
                            "UPDATE emails SET is_read = ? WHERE id = ?", (int(is_read), email_id)
                        )
                        stats.updated_flags += 1
                    continue

                try:
                    parsed = parse_message(f)
                except Exception:
                    continue

                rel_path = str(f.relative_to(root))
                existing = conn.execute(
                    "SELECT id, thread_id FROM emails WHERE message_id = ?",
                    (parsed.message_id,),
                ).fetchone()
                if existing:
                    # Same message in another folder (e.g. Gmail label): map, don't duplicate.
                    email_id = existing["id"]
                else:
                    email_id = _insert_email(
                        conn, parsed, folder, rel_path, is_sent, is_read, cfg, account="default"
                    )
                    row = conn.execute(
                        "SELECT thread_id FROM emails WHERE id = ?", (email_id,)
                    ).fetchone()
                    touched_threads.add(row["thread_id"])
                    stats.new += 1
                    emit(
                        conn,
                        "email_ingested",
                        email_id,
                        {
                            "subject": parsed.subject,
                            "from": parsed.from_addr,
                            "folder": folder,
                            "date": parsed.date_utc,
                            "has_attachments": bool(parsed.attachments),
                        },
                        account="default",
                    )

                    # ── Guardrail scan ──
                    if cfg.guardrail.scan_on_ingest:
                        try:
                            gr = scan_email_from_config(
                                from_addr=parsed.from_addr,
                                subject=parsed.subject,
                                body_text=parsed.body_text,
                                guardrail_config=cfg.guardrail,
                            )
                            store_guardrail_result(
                                conn, email_id, gr.risk_score, gr.blocked, gr.warnings
                            )
                        except Exception:
                            # Never let a scanner failure abort the sync run.
                            pass

                conn.execute(
                    "INSERT OR REPLACE INTO sync_state (folder, uniq, filename, email_id, account) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (folder, uniq, f.name, email_id, "default"),
                )

    # Removal pass: drop mappings for vanished files, then emails with no remaining copy.
    for key, (_, email_id) in known.items():
        if key not in seen:
            conn.execute("DELETE FROM sync_state WHERE folder = ? AND uniq = ?", key)
            remaining = conn.execute(
                "SELECT COUNT(*) AS n FROM sync_state WHERE email_id = ?", (email_id,)
            ).fetchone()["n"]
            if remaining == 0:
                row = conn.execute(
                    "SELECT thread_id, subject FROM emails WHERE id = ?", (email_id,)
                ).fetchone()
                if row:
                    touched_threads.add(row["thread_id"])
                    emit(
                        conn,
                        "email_deleted",
                        email_id,
                        {"subject": row["subject"]},
                        account="default",
                    )
                conn.execute("DELETE FROM emails_fts WHERE rowid = ?", (email_id,))
                with suppress(sqlite3.OperationalError):
                    conn.execute("DELETE FROM vec_emails WHERE email_id = ?", (email_id,))
                conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
                stats.deleted += 1

    # Threads may have merged during ingest; recompute stats for survivors only.
    thread_placeholders = ",".join("?" * len(touched_threads))
    surviving = (
        {
            r["id"]
            for r in conn.execute(
                f"SELECT id FROM threads WHERE id IN ({thread_placeholders})",
                tuple(touched_threads),
            )
        }
        if touched_threads
        else set()
    )
    refresh_thread_stats(conn, surviving)

    conn.commit()
    return stats
