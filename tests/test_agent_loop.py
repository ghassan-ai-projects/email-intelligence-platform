"""Events feed, write-back operations, and draft-first sending."""

from __future__ import annotations

from email.message import EmailMessage

from mailintel import actions, drafts, mcp_server
from mailintel.enrich.pipeline import run_pipeline
from mailintel.events import get_events_since
from mailintel.ingest import ingest
from mailintel.search import get_email, search_emails
from tests.test_enrich import FakeEmbedder, FakeProvider


def _setup(conn, cfg):
    ingest(conn, cfg)
    run_pipeline(conn, cfg, provider=FakeProvider(), embedder=FakeEmbedder())


# --- events ------------------------------------------------------------------


def test_ingest_and_enrich_emit_events(conn, cfg):
    _setup(conn, cfg)
    feed = get_events_since(conn, cursor=0, limit=500)
    types = [e["type"] for e in feed["events"]]
    assert types.count("email_ingested") == 5
    assert types.count("email_enriched") == 5
    assert "action_item_created" in types
    assert "fact_extracted" in types
    # ingested events carry enough payload to triage without another call
    ing = next(e for e in feed["events"] if e["type"] == "email_ingested")
    assert {"subject", "from", "folder", "date"} <= set(ing["payload"])


def test_event_cursor_pagination(conn, cfg):
    _setup(conn, cfg)
    seen: list[int] = []
    cursor = 0
    while True:
        feed = get_events_since(conn, cursor=cursor, limit=3)
        seen.extend(e["id"] for e in feed["events"])
        cursor = feed["next_cursor"]
        if not feed["has_more"] and not feed["events"]:
            break
        if not feed["events"]:
            break
    assert seen == sorted(set(seen))  # strictly increasing, no duplicates
    assert cursor == get_events_since(conn, 0, limit=1)["latest_cursor"]
    # delta semantics: nothing new after consuming everything
    assert get_events_since(conn, cursor=cursor)["events"] == []


def test_event_type_filter(conn, cfg):
    _setup(conn, cfg)
    feed = get_events_since(conn, types=["action_item_created"], limit=100)
    assert feed["events"]
    assert all(e["type"] == "action_item_created" for e in feed["events"])


def test_email_deleted_event(conn, cfg, maildir):
    _setup(conn, cfg)
    cursor = get_events_since(conn, 0, limit=1)["latest_cursor"]
    (maildir / "cur" / "1002.invoice.host:2,").unlink()
    ingest(conn, cfg)
    feed = get_events_since(conn, cursor=cursor)
    assert [e["type"] for e in feed["events"]] == ["email_deleted"]
    assert feed["events"][0]["payload"]["subject"] == "Invoice July"


# --- write-back --------------------------------------------------------------


def test_complete_action_item(conn, cfg):
    _setup(conn, cfg)
    item = conn.execute("SELECT id, email_id FROM action_items").fetchone()
    result = actions.complete_action_item(conn, item["id"])
    assert result["status"] == "done"
    row = conn.execute(
        "SELECT status, completed_at FROM action_items WHERE id = ?", (item["id"],)
    ).fetchone()
    assert row["status"] == "done" and row["completed_at"]
    events = get_events_since(conn, types=["action_item_completed"])["events"]
    assert events[0]["email_id"] == item["email_id"]
    # reopen
    assert actions.complete_action_item(conn, item["id"], done=False)["status"] == "open"
    assert "error" in actions.complete_action_item(conn, 999_999)


def test_set_importance_clamps(conn, cfg):
    _setup(conn, cfg)
    eid = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    assert actions.set_importance(conn, eid, 99)["importance"] == 5
    assert actions.set_importance(conn, eid, -1)["importance"] == 1
    assert "error" in actions.set_importance(conn, 999_999, 3)


def test_tags_roundtrip_and_search_filter(conn, cfg):
    _setup(conn, cfg)
    eid = conn.execute("SELECT id FROM emails WHERE message_id = '<m3@example.com>'").fetchone()[
        "id"
    ]
    actions.tag_email(conn, eid, "  Invoice ")  # normalized to lowercase
    actions.tag_email(conn, eid, "triaged")
    assert actions.get_tags(conn, eid) == ["invoice", "triaged"]

    hits = search_emails(conn, tag="invoice")
    assert [h["id"] for h in hits] == [eid]
    assert search_emails(conn, tag="nonexistent") == []

    assert get_email(conn, eid)["tags"] == ["invoice", "triaged"]
    actions.untag_email(conn, eid, "invoice")
    assert actions.get_tags(conn, eid) == ["triaged"]
    assert actions.list_tags(conn) == [{"tag": "triaged", "count": 1}]


def test_agent_notes_accumulate(conn, cfg):
    _setup(conn, cfg)
    eid = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    actions.add_note(conn, eid, "checked with Bob")
    result = actions.add_note(conn, eid, "resolved")
    assert "checked with Bob" in result["agent_notes"]
    assert "resolved" in result["agent_notes"]
    assert get_email(conn, eid)["agent_notes"] == result["agent_notes"]
    assert "error" in actions.add_note(conn, eid, "   ")


# --- drafts ------------------------------------------------------------------


def test_draft_lifecycle(conn, cfg):
    _setup(conn, cfg)
    d = drafts.create_draft(
        conn,
        ["dave@client.example"],
        "Re: contract",
        "Following up.",
    )
    assert d["status"] == "draft"
    draft_id = d["draft_id"]

    d2 = drafts.update_draft(conn, draft_id, body="Following up politely.")
    assert d2["body"] == "Following up politely."
    assert d2["to"] == ["dave@client.example"]

    assert len(drafts.list_drafts(conn)) == 1
    assert drafts.delete_draft(conn, draft_id)["status"] == "deleted"
    assert drafts.list_drafts(conn) == []
    assert "error" in drafts.get_draft(conn, draft_id)


def test_send_draft_respects_guardrails(conn, cfg):
    _setup(conn, cfg)
    d = drafts.create_draft(conn, ["x@y.com"], "hi", "body")
    result = drafts.send_draft(conn, cfg, d["draft_id"])
    assert "disabled" in result["error"]  # smtp off by default
    assert drafts.get_draft(conn, d["draft_id"])["status"] == "draft"  # unchanged


def test_send_draft_happy_path(conn, cfg, monkeypatch):
    _setup(conn, cfg)
    sent = {}

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
            sent["msg"] = msg

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("EMAIL_USER", "me@gmx.de")
    monkeypatch.setenv("EMAIL_PASSWORD", "pw")
    cfg.smtp.enabled = True
    cfg.smtp.host = "mail.gmx.net"

    reply_to = conn.execute(
        "SELECT id, message_id FROM emails WHERE message_id = '<m1@example.com>'"
    ).fetchone()
    d = drafts.create_draft(
        conn,
        ["alice@example.com"],
        "Re: upgrade",
        "On it.",
        in_reply_to_email_id=reply_to["id"],
    )
    result = drafts.send_draft(conn, cfg, d["draft_id"])
    assert result["status"] == "sent"
    assert sent["msg"]["In-Reply-To"] == "<m1@example.com>"
    assert drafts.get_draft(conn, d["draft_id"])["status"] == "sent"
    # double-send blocked
    assert "already sent" in drafts.send_draft(conn, cfg, d["draft_id"])["error"]
    # update/delete of sent draft blocked
    assert "error" in drafts.update_draft(conn, d["draft_id"], body="x")
    assert "error" in drafts.delete_draft(conn, d["draft_id"])
    # events recorded
    types = [
        e["type"] for e in get_events_since(conn, types=["draft_sent", "email_sent"])["events"]
    ]
    assert "draft_sent" in types and "email_sent" in types


# --- MCP surface -------------------------------------------------------------


def test_mcp_agent_loop_tools(conn, cfg, monkeypatch):
    _setup(conn, cfg)
    monkeypatch.setattr(mcp_server, "_config", cfg)

    feed = mcp_server.get_events_since(cursor=0, limit=10)
    assert feed["events"] and feed["next_cursor"] > 0

    eid = mcp_server.search_emails(query="invoice")[0]["id"]
    assert mcp_server.tag_email(eid, "billing")["tags"] == ["billing"]
    assert mcp_server.search_emails(tag="billing")[0]["id"] == eid
    assert mcp_server.list_tags() == [{"tag": "billing", "count": 1}]
    assert mcp_server.add_email_note(eid, "paid")["agent_notes"].endswith("paid")

    item = mcp_server.find_action_items()[0]
    assert mcp_server.complete_action_item(item["id"])["status"] == "done"
    assert mcp_server.find_action_items(status="open") == []

    d = mcp_server.create_draft(["dave@client.example"], "s", "b")
    assert mcp_server.list_drafts()[0]["draft_id"] == d["draft_id"]
    assert "disabled" in mcp_server.send_draft(d["draft_id"])["error"]
    assert mcp_server.delete_draft(d["draft_id"])["status"] == "deleted"
