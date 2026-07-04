"""MCP server tools tested against a real (temp) store; tool fns are plain callables."""

from __future__ import annotations

import pytest

from mailintel import mcp_server
from mailintel.enrich.pipeline import run_pipeline
from mailintel.ingest import ingest
from tests.test_enrich import FakeEmbedder, FakeProvider


@pytest.fixture
def served(conn, cfg, monkeypatch):
    ingest(conn, cfg)
    run_pipeline(conn, cfg, provider=FakeProvider(), embedder=FakeEmbedder())
    conn.commit()
    monkeypatch.setattr(mcp_server, "_config", cfg)
    return cfg


def test_tools_registered():
    import anyio

    tools = anyio.run(mcp_server.mcp.list_tools)
    names = {t.name for t in tools}
    assert {
        "search_emails",
        "semantic_search",
        "related_emails",
        "get_email",
        "get_thread",
        "search_threads",
        "find_action_items",
        "find_decisions",
        "search_facts",
        "summarize_sender",
        "find_waiting_replies",
        "daily_summary",
        "list_folders",
        "get_stats",
        "sync_now",
    } <= names


def test_search_emails_tool(served):
    results = mcp_server.search_emails(query="kubernetes")
    assert len(results) == 2
    assert "body" not in results[0]  # brief results only


def test_get_email_and_thread_tools(served):
    email = mcp_server.search_emails(query="quarterly")[0]
    detail = mcp_server.get_email(email["id"])
    assert detail["attachments"][0]["filename"] == "doc.pdf"
    thread = mcp_server.get_thread(mcp_server.search_emails(query="kubernetes")[0]["thread_id"])
    assert thread["message_count"] == 2
    assert mcp_server.get_email(999_999)["error"]


def test_knowledge_tools(served):
    items = mcp_server.find_action_items()
    assert items and items[0]["owner"] == "Bob"
    facts = mcp_server.search_facts(category="deadline")
    assert facts and "420" in facts[0]["fact"]
    profile = mcp_server.summarize_sender("alice@example.com")
    assert profile["total_received"] == 1
    digest = mcp_server.daily_summary("2025-06-05")
    assert digest["received"] == 2
    waiting = mcp_server.find_waiting_replies()
    assert waiting[0]["subject"] == "Follow-up on contract"


def test_stats_and_folders(served):
    stats = mcp_server.get_stats()
    assert stats["emails"] == 5
    assert stats["enriched"] == 5
    folders = mcp_server.list_folders()
    assert {f["folder"] for f in folders} == {"INBOX", "Projects", "Sent"}


def test_related_emails_uses_stored_vector(served):
    eid = mcp_server.search_emails(query="kubernetes")[0]["id"]
    related = mcp_server.related_emails(eid, limit=3)
    assert eid not in [r["id"] for r in related]
    assert len(related) == 3
