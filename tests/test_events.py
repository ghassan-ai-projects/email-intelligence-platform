"""Tests for the append-only event log."""

from __future__ import annotations

import pytest

from mailintel import db
from mailintel.events import emit, get_events_since, prune_events


def test_emit_rejects_unknown_event_type(conn):
    with pytest.raises(ValueError, match="unknown event type"):
        emit(conn, "bogus_type", 1, {})


def test_emit_and_get_events_since(conn):
    emit(conn, "email_ingested", 1, {"subject": "hello"}, account="default")
    emit(conn, "email_enriched", 1, {"importance": 5}, account="default")
    result = get_events_since(conn, cursor=0)
    assert len(result["events"]) == 2
    assert result["events"][0]["type"] == "email_ingested"
    assert result["next_cursor"] == result["events"][-1]["id"]
    assert result["latest_cursor"] == result["events"][-1]["id"]


def test_get_events_since_negative_cursor(conn):
    emit(conn, "email_ingested", 1, {})
    result = get_events_since(conn, cursor=-10)
    assert result["next_cursor"] >= 0
    assert len(result["events"]) == 1


def test_get_events_since_filter_types(conn):
    emit(conn, "email_ingested", 1, {})
    emit(conn, "email_enriched", 1, {})
    result = get_events_since(conn, cursor=0, types=["email_ingested"])
    assert len(result["events"]) == 1
    assert result["events"][0]["type"] == "email_ingested"
    assert result["latest_cursor"] == 2


def test_filtered_cursor_does_not_skip_event_committed_between_reads(conn, cfg):
    emit(conn, "email_ingested", 1, {})
    conn.commit()
    other = db.connect(cfg.storage.db_path)

    class InterleavingConnection:
        def __init__(self, inner):
            self.inner = inner
            self.inserted = False

        @property
        def in_transaction(self):
            return self.inner.in_transaction

        def execute(self, sql, parameters=()):
            result = self.inner.execute(sql, parameters)
            if "SELECT COALESCE(MAX(id), 0) FROM events" in sql and not self.inserted:
                emit(other, "draft_created", 1, {})
                other.commit()
                self.inserted = True
            return result

        def rollback(self):
            return self.inner.rollback()

    interleaved = InterleavingConnection(conn)
    try:
        first = get_events_since(interleaved, types=["draft_created"])
        assert first["events"] == []
        assert first["next_cursor"] == 1

        second = get_events_since(interleaved, cursor=first["next_cursor"], types=["draft_created"])
        assert [event["id"] for event in second["events"]] == [2]
    finally:
        other.close()


def test_prune_events(conn):
    emit(conn, "email_ingested", 1, {})
    emit(conn, "email_enriched", 1, {})
    emit(conn, "email_deleted", 1, {})
    deleted = prune_events(conn, before_id=2)
    assert deleted == 1
    rows = conn.execute("SELECT id FROM events ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == [2, 3]
