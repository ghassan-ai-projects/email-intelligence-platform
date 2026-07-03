"""Resumable enrichment pipeline over the pipeline_jobs queue.

Stage order matters: attachments (PDF text) -> enrich (LLM) -> embed (Voyage),
so the LLM sees attachment text and embeddings include the summary.
Safe to interrupt; failed jobs retry up to enrich.max_attempts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..config import Config
from ..models import EnrichmentResult
from ..security import sanitize_text
from .attachments import extract_email_attachments
from .embeddings import (
    Embedder,
    embedding_input,
    ensure_vec_table,
    make_embedder,
    store_embeddings,
)
from .llm import LLMProvider, make_provider
from .prompts import ENRICH_SYSTEM, build_enrich_prompt

STAGE_ORDER = ["attachments", "enrich", "embed"]


@dataclass
class PipelineStats:
    done: dict[str, int] = field(default_factory=dict)
    failed: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"done": self.done, "failed": self.failed}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _mark(conn: sqlite3.Connection, job_id: int, status: str, error: str | None = None) -> None:
    conn.execute(
        "UPDATE pipeline_jobs SET status = ?, error = ?, attempts = attempts + 1, "
        "updated_at = ? WHERE id = ?",
        (status, error, _now(), job_id),
    )


def _pending_jobs(
    conn: sqlite3.Connection, stage: str, max_attempts: int, limit: int
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT j.id AS job_id, j.attempts, e.* FROM pipeline_jobs j "
        "JOIN emails e ON e.id = j.email_id "
        "WHERE j.stage = ? AND j.status IN ('pending', 'failed') AND j.attempts < ? "
        "ORDER BY e.date_utc DESC LIMIT ?",
        (stage, max_attempts, limit),
    ).fetchall()


def store_enrichment(conn: sqlite3.Connection, email_id: int, result: EnrichmentResult) -> None:
    conn.execute(
        "UPDATE emails SET language = ?, summary = ?, importance = ?, sentiment = ?, "
        "enriched_at = ? WHERE id = ?",
        (
            result.language,
            sanitize_text(result.summary),
            result.importance,
            result.sentiment,
            _now(),
            email_id,
        ),
    )
    # Re-enrichment replaces previous knowledge rows for the email.
    conn.execute("DELETE FROM action_items WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM facts WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM email_entities WHERE email_id = ?", (email_id,))

    for item in result.action_items:
        conn.execute(
            "INSERT INTO action_items (email_id, description, owner, due_date) "
            "VALUES (?, ?, ?, ?)",
            (email_id, sanitize_text(item.description), item.owner, item.due_date),
        )
    for fact in result.facts:
        conn.execute(
            "INSERT INTO facts (email_id, fact, category, due_date, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            (email_id, sanitize_text(fact.fact), fact.category, fact.due_date, fact.confidence),
        )
    entity_lists = [
        ("person", result.entities.people),
        ("company", result.entities.companies),
        ("project", result.entities.projects),
        ("topic", result.entities.topics),
    ]
    for etype, names in entity_lists:
        for name in names:
            name = name.strip()
            if not name:
                continue
            norm = name.lower()
            conn.execute(
                "INSERT OR IGNORE INTO entities (type, name, name_norm) VALUES (?, ?, ?)",
                (etype, name, norm),
            )
            entity_id = conn.execute(
                "SELECT id FROM entities WHERE type = ? AND name_norm = ?", (etype, norm)
            ).fetchone()["id"]
            conn.execute(
                "INSERT OR IGNORE INTO email_entities (email_id, entity_id) VALUES (?, ?)",
                (email_id, entity_id),
            )


def run_attachments_stage(conn: sqlite3.Connection, cfg: Config, limit: int) -> tuple[int, int]:
    done = failed = 0
    for job in _pending_jobs(conn, "attachments", cfg.enrich.max_attempts, limit):
        try:
            extract_email_attachments(conn, job["id"], cfg.maildir.path)
            _mark(conn, job["job_id"], "done")
            done += 1
        except Exception as exc:  # noqa: BLE001 - queue must survive any single failure
            _mark(conn, job["job_id"], "failed", str(exc)[:500])
            failed += 1
        conn.commit()
    return done, failed


def run_enrich_stage(
    conn: sqlite3.Connection, cfg: Config, limit: int, provider: LLMProvider | None = None
) -> tuple[int, int]:
    jobs = _pending_jobs(conn, "enrich", cfg.enrich.max_attempts, limit)
    if not jobs:
        return 0, 0
    provider = provider or make_provider(cfg.llm)
    done = failed = 0
    for job in jobs:
        try:
            prompt = build_enrich_prompt(conn, job, cfg.llm)
            raw = provider.complete_json(ENRICH_SYSTEM, prompt)
            result = EnrichmentResult.model_validate(raw)
            store_enrichment(conn, job["id"], result)
            _mark(conn, job["job_id"], "done")
            done += 1
        except Exception as exc:  # noqa: BLE001
            _mark(conn, job["job_id"], "failed", str(exc)[:500])
            failed += 1
        conn.commit()
    return done, failed


def run_embed_stage(
    conn: sqlite3.Connection, cfg: Config, limit: int, embedder: Embedder | None = None
) -> tuple[int, int]:
    # Only embed after enrichment so the summary is part of the vector; emails
    # whose enrich job terminally failed still get embedded (body-only).
    jobs = conn.execute(
        "SELECT j.id AS job_id, e.* FROM pipeline_jobs j "
        "JOIN emails e ON e.id = j.email_id "
        "WHERE j.stage = 'embed' AND j.status IN ('pending', 'failed') AND j.attempts < ? "
        "AND NOT EXISTS (SELECT 1 FROM pipeline_jobs j2 WHERE j2.email_id = j.email_id "
        "  AND j2.stage = 'enrich' AND j2.status IN ('pending', 'failed') AND j2.attempts < ?) "
        "ORDER BY e.date_utc DESC LIMIT ?",
        (cfg.enrich.max_attempts, cfg.enrich.max_attempts, limit),
    ).fetchall()
    if not jobs:
        return 0, 0
    embedder = embedder or make_embedder(cfg.embeddings)
    ensure_vec_table(conn, embedder.dimensions, cfg.embeddings.model)

    done = failed = 0
    batch_size = cfg.embeddings.batch_size
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i : i + batch_size]
        texts = [embedding_input(j, cfg.embeddings.max_chars) for j in batch]
        try:
            vectors = embedder.embed_documents(texts)
            store_embeddings(conn, [(j["id"], v) for j, v in zip(batch, vectors)])
            for j in batch:
                _mark(conn, j["job_id"], "done")
            done += len(batch)
        except Exception as exc:  # noqa: BLE001
            for j in batch:
                _mark(conn, j["job_id"], "failed", str(exc)[:500])
            failed += len(batch)
        conn.commit()
    return done, failed


def run_pipeline(
    conn: sqlite3.Connection,
    cfg: Config,
    limit: int = 200,
    provider: LLMProvider | None = None,
    embedder: Embedder | None = None,
) -> PipelineStats:
    stats = PipelineStats()
    runners = {
        "attachments": lambda: run_attachments_stage(conn, cfg, limit),
        "enrich": lambda: run_enrich_stage(conn, cfg, limit, provider),
        "embed": lambda: run_embed_stage(conn, cfg, limit, embedder),
    }
    for stage in STAGE_ORDER:
        if stage not in cfg.enrich.stages:
            continue
        done, failed = runners[stage]()
        if done:
            stats.done[stage] = done
        if failed:
            stats.failed[stage] = failed
    return stats
