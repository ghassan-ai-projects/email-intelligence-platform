"""Enrichment pipeline tests with fake LLM provider and embedder."""

from __future__ import annotations

import hashlib

from mailintel.enrich.embeddings import knn_email_ids
from mailintel.enrich.llm import parse_json_response
from mailintel.enrich.pipeline import run_pipeline
from mailintel.ingest import ingest
from mailintel.knowledge import (
    daily_summary,
    find_action_items,
    find_waiting_replies,
    search_facts,
    summarize_sender,
)
from mailintel.search import get_email


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def complete_json(self, _system: str, user: str) -> dict:
        self.calls += 1
        subject = user.splitlines()[3].removeprefix("Subject: ")
        is_k8s_root = subject == "Kubernetes cluster upgrade"
        return {
            "language": "en",
            "summary": "Summary of: " + subject,
            "importance": 4 if is_k8s_root else 2,
            "sentiment": "neutral",
            "action_items": (
                [
                    {
                        "description": "Prepare migration checklist",
                        "owner": "Bob",
                        "due_date": "2025-06-10",
                    }
                ]
                if is_k8s_root
                else []
            ),
            "entities": {
                "people": ["Alice Smith"] if "Alice" in user else [],
                "companies": ["Acme Corp"] if "Acme" in user else [],
                "projects": [],
                "topics": ["kubernetes"] if "Kubernetes" in user else ["billing"],
            },
            "facts": (
                [
                    {
                        "fact": "Invoice of $420 due July 12",
                        "category": "deadline",
                        "due_date": "2025-07-12",
                        "confidence": 0.95,
                    }
                ]
                if "Invoice" in user
                else []
            ),
        }


class FakeEmbedder:
    dimensions = 8

    def _vec(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        return [b / 255 for b in h[:8]]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str):
        return self._vec(text)


def _enrich_all(conn, cfg):
    ingest(conn, cfg)
    provider, embedder = FakeProvider(), FakeEmbedder()
    stats = run_pipeline(conn, cfg, provider=provider, embedder=embedder)
    return provider, embedder, stats


def test_pipeline_runs_all_stages(conn, cfg):
    provider, _, stats = _enrich_all(conn, cfg)
    assert stats.done.get("enrich") == 5
    assert stats.done.get("embed") == 5
    assert stats.done.get("attachments") == 1
    assert provider.calls == 5
    assert not stats.failed
    assert conn.execute("SELECT COUNT(*) FROM emails WHERE enriched_at IS NULL").fetchone()[0] == 0


def test_enrichment_stored(conn, cfg):
    _enrich_all(conn, cfg)
    eid = conn.execute("SELECT id FROM emails WHERE message_id = '<m1@example.com>'").fetchone()[
        "id"
    ]
    d = get_email(conn, eid)
    assert d["summary"].startswith("Summary of: Kubernetes")
    assert d["importance"] == 4
    assert {e["name"] for e in d["entities"]} >= {"Alice Smith", "Acme Corp"}

    items = find_action_items(conn)
    assert len(items) == 1
    assert items[0]["owner"] == "Bob"
    assert items[0]["source"]["email_id"] == eid

    facts = search_facts(conn, category="deadline")
    assert len(facts) == 1
    assert "420" in facts[0]["fact"]


def test_semantic_knn(conn, cfg):
    _, embedder, _ = _enrich_all(conn, cfg)
    # Embedding input for m1 = subject + summary + body; reproduce it exactly.
    from mailintel.enrich.embeddings import embedding_input

    row = conn.execute("SELECT * FROM emails WHERE message_id = '<m1@example.com>'").fetchone()
    query_vec = embedder.embed_query(embedding_input(row, cfg.embeddings.max_chars))
    hits = knn_email_ids(conn, query_vec, 3)
    assert hits[0][0] == row["id"]
    assert hits[0][1] < 1e-6  # exact match


def test_pipeline_idempotent(conn, cfg):
    _enrich_all(conn, cfg)
    provider = FakeProvider()
    stats = run_pipeline(conn, cfg, provider=provider, embedder=FakeEmbedder())
    assert provider.calls == 0
    assert not stats.done and not stats.failed


def test_failed_enrich_retries_then_gives_up(conn, cfg):
    ingest(conn, cfg)

    class BrokenProvider:
        def __init__(self):
            self.calls = 0

        def complete_json(self, _system, _user):
            self.calls += 1
            raise RuntimeError("api down")

    provider = BrokenProvider()
    for _ in range(cfg.enrich.max_attempts + 2):
        run_pipeline(conn, cfg, provider=provider, embedder=FakeEmbedder())
    assert provider.calls == 5 * cfg.enrich.max_attempts
    # Embeds still ran (body-only) once enrich jobs were terminally failed.
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM pipeline_jobs WHERE stage='embed' AND status='done'"
        ).fetchone()[0]
        == 5
    )


def test_knowledge_queries(conn, cfg):
    _enrich_all(conn, cfg)
    prof = summarize_sender(conn, "alice@example.com")
    assert prof["total_received"] == 1
    assert prof["open_action_items"] == 1
    assert prof["top_topics"][0]["topic"] == "kubernetes"

    waiting = find_waiting_replies(conn, min_age_days=2)
    assert len(waiting) == 1
    assert waiting[0]["subject"] == "Follow-up on contract"

    digest = daily_summary(conn, "2025-06-05")
    assert digest["received"] == 2
    assert len(digest["important"]) == 1
    assert digest["important"][0]["importance"] == 4


def test_parse_json_response_fenced():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_response('noise before {"a": {"b": 2}} noise after') == {"a": {"b": 2}}
