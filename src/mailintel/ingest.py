"""Incrementally ingest Maildir messages into SQLite projections."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from . import ingest_parser as _parser
from . import ingest_storage as _storage
from . import threading_ as _threading
from .config import Config
from .events import emit
from .guardrail.db import store_guardrail_failure, store_guardrail_result
from .guardrail.scanner_wrapper import scan_email_from_config
from .ingest_cleanup import refresh_touched_threads, remove_missing_files
from .ingest_maildir import iter_maildirs, segment_matches, split_flags

parse_message = _parser.parse_message
ParsedEmail = _parser.ParsedEmail

@dataclass
class IngestStats:
    new: int = 0
    updated_flags: int = 0
    deleted: int = 0
    parse_errors: int = 0
    skipped_folders: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "new": self.new,
            "updated_flags": self.updated_flags,
            "deleted": self.deleted,
            "parse_errors": self.parse_errors,
            "skipped_folders": self.skipped_folders,
        }


@dataclass
class _IngestState:
    conn: sqlite3.Connection
    cfg: Config
    root: Path
    stats: IngestStats
    known: dict[tuple[str, str], tuple[str, int]]
    seen: set[tuple[str, str]] = field(default_factory=set)
    touched_threads: set[int] = field(default_factory=set)


def ingest(conn: sqlite3.Connection, cfg: Config) -> IngestStats:
    """Synchronize Maildir files, projections, enrichment jobs, and events."""
    root = _validate_root(cfg)
    state = _create_state(conn, cfg, root)
    _process_maildirs(state)
    remove_missing_files(
        state.conn,
        state.known,
        state.seen,
        state.touched_threads,
        state.stats,
        state.root,
        state.cfg.maildir.sent_folders,
    )
    refresh_touched_threads(state.conn, state.touched_threads)
    conn.commit()
    return state.stats


def _validate_root(cfg: Config) -> Path:
    root = cfg.maildir.path
    if not root.is_dir():
        raise FileNotFoundError(f"Maildir root not found: {root}")
    return root


def _create_state(conn: sqlite3.Connection, cfg: Config, root: Path) -> _IngestState:
    known = {
        (row["folder"], row["uniq"]): (row["filename"], row["email_id"])
        for row in conn.execute("SELECT folder, uniq, filename, email_id FROM sync_state")
    }
    return _IngestState(conn, cfg, root, IngestStats(), known)


def _process_maildirs(state: _IngestState) -> None:
    for folder, path in iter_maildirs(state.root):
        if segment_matches(folder, state.cfg.maildir.exclude_folders):
            state.stats.skipped_folders.append(folder)
            continue
        _process_folder(state, folder, path)


def _process_folder(state: _IngestState, folder: str, path: Path) -> None:
    is_sent = segment_matches(folder, state.cfg.maildir.sent_folders)
    for subdirectory in ("cur", "new"):
        for message_path in sorted((path / subdirectory).iterdir()):
            _process_file(state, folder, message_path, is_sent)


def _process_file(state: _IngestState, folder: str, path: Path, is_sent: bool) -> None:
    if not path.is_file() or path.name.startswith("."):
        return
    unique_name, is_read = split_flags(path.name)
    key = (folder, unique_name)
    state.seen.add(key)

    if key in state.known:
        _update_existing_file(state, key, path.name, is_read, str(path.relative_to(state.root)))
        return

    try:
        parsed = parse_message(path)
    except Exception:
        state.stats.parse_errors += 1
        return

    rel_path = str(path.relative_to(state.root))
    email_id = _ingest_parsed_file(state, parsed, folder, rel_path, is_sent, is_read)
    state.conn.execute(
        "INSERT OR REPLACE INTO sync_state (folder, uniq, filename, email_id, account) "
        "VALUES (?, ?, ?, ?, ?)",
        (folder, unique_name, path.name, email_id, "default"),
    )


def _update_existing_file(
    state: _IngestState,
    key: tuple[str, str],
    filename: str,
    is_read: bool,
    rel_path: str,
) -> None:
    old_filename, email_id = state.known[key]
    if old_filename == filename:
        return
    state.conn.execute(
        "UPDATE sync_state SET filename = ? WHERE folder = ? AND uniq = ?",
        (filename, key[0], key[1]),
    )
    state.conn.execute(
        "UPDATE emails SET is_read = ?, maildir_path = ? WHERE id = ?",
        (int(is_read), rel_path, email_id),
    )
    state.stats.updated_flags += 1


def _ingest_parsed_file(
    state: _IngestState,
    parsed: ParsedEmail,
    folder: str,
    rel_path: str,
    is_sent: bool,
    is_read: bool,
) -> int:
    existing = state.conn.execute(
        "SELECT id, thread_id, maildir_path FROM emails WHERE message_id = ?", (parsed.message_id,)
    ).fetchone()
    if existing:
        state.conn.execute(
            "UPDATE emails SET is_sent = MAX(is_sent, ?), is_read = MIN(is_read, ?) WHERE id = ?",
            (int(is_sent), int(is_read), existing["id"]),
        )
        if not (state.root / existing["maildir_path"]).is_file():
            state.conn.execute(
                "UPDATE emails SET folder = ?, maildir_path = ? WHERE id = ?",
                (folder, rel_path, existing["id"]),
            )
        return existing["id"]

    email_id = _storage.insert_email(
        state.conn, parsed, folder, rel_path, is_sent, is_read, state.cfg, account="default"
    )
    row = state.conn.execute("SELECT thread_id FROM emails WHERE id = ?", (email_id,)).fetchone()
    state.touched_threads.add(row["thread_id"])
    state.stats.new += 1
    emit(
        state.conn,
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
    _store_guardrail_result(state, email_id, parsed)
    return email_id


def _store_guardrail_result(state: _IngestState, email_id: int, parsed: ParsedEmail) -> None:
    if not state.cfg.guardrail.scan_on_ingest:
        return
    try:
        result = scan_email_from_config(
            from_addr=parsed.from_addr,
            subject=parsed.subject,
            body_text=parsed.body_text,
            guardrail_config=state.cfg.guardrail,
        )
    except Exception as exc:
        # Scanner failures are visible and fail closed. Persistence failures
        # below must propagate so ingest does not misclassify database errors.
        store_guardrail_failure(state.conn, email_id, type(exc).__name__)
        return
    store_guardrail_result(state.conn, email_id, result.risk_score, result.blocked, result.warnings)
