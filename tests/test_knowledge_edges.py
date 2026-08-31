"""Boundary coverage for knowledge-level queries and their filters."""

from __future__ import annotations

from mailintel import knowledge
from mailintel.ingest import ingest


def test_action_fact_and_decision_filters(conn, cfg) -> None:
    ingest(conn, cfg)
    email_id = conn.execute(
        "SELECT id FROM emails WHERE message_id = '<m1@example.com>'"
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO action_items (email_id, description, owner, due_date) "
        "VALUES (?, ?, ?, ?)",
        (email_id, "Prepare checklist", "Bob", "2025-06-10"),
    )
    invoice_id = conn.execute(
        "SELECT id FROM emails WHERE message_id = '<m3@example.com>'"
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO facts (email_id, fact, category, due_date) VALUES (?, ?, ?, ?)",
        (invoice_id, "Invoice total is 420", "deadline", "2025-07-12"),
    )
    conn.commit()
    all_items = knowledge.find_action_items(conn, status="all", owner="Bob", due_before="2025-12-31")
    assert all_items and all_items[0]["source"]["email_id"]
    assert knowledge.find_action_items(conn, limit=0)

    facts = knowledge.search_facts(
        conn, query="420", category="deadline", date_from="2025-06-01", limit=0
    )
    assert facts and facts[0]["category"] == "deadline"
    decisions = knowledge.find_decisions(conn, query="Kubernetes", date_from="2025-06-01")
    assert decisions == []


def test_sender_and_daily_summary_handle_empty_results(conn, cfg) -> None:
    ingest(conn, cfg)
    profile = knowledge.summarize_sender(conn, "nobody@example.com")
    assert profile["total_received"] == 0
    assert profile["first_date"] is None
    assert profile["open_action_items"] == 0
    assert profile["recent_emails"] == []

    empty = knowledge.daily_summary(conn, "2099-01-01")
    assert empty == {
        "date": "2099-01-01",
        "received": 0,
        "unread": 0,
        "important": [],
        "new_action_items": [],
        "key_facts": [],
        "all_emails": [],
    }


def test_waiting_replies_does_not_report_same_second_inbound_mail(conn, cfg, maildir) -> None:
    from tests.conftest import make_email, write_message

    write_message(
        maildir / ".Sent",
        "9100.same.host:2,S",
        make_email(
            "<same-sent@example.com>",
            "Same-second question",
            from_="Me <me@example.com>",
            to="Bob <bob@example.com>",
            date="Sun, 08 Jun 2025 16:00:00 +0000",
        ),
    )
    write_message(
        maildir,
        "9101.same-reply.host:2,",
        make_email(
            "<same-inbound@example.com>",
            "Re: Same-second question",
            from_="Bob <bob@example.com>",
            refs=["<same-sent@example.com>"],
            date="Sun, 08 Jun 2025 16:00:00 +0000",
        ),
    )
    ingest(conn, cfg)
    assert not any(
        item["subject"] == "Same-second question"
        for item in knowledge.find_waiting_replies(conn)
    )
