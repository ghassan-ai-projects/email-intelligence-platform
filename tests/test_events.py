"""Tests for the append-only event log."""

from __future__ import annotations

import pytest

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


def test_prune_events(conn):
    emit(conn, "email_ingested", 1, {})
    emit(conn, "email_enriched", 1, {})
    emit(conn, "email_deleted", 1, {})
    deleted = prune_events(conn, before_id=2)
    assert deleted == 1
    rows = conn.execute("SELECT id FROM events ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == [2, 3]
