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
from ..events import emit
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
from .enrichment_storage import persist_enrichment
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


def _reset_stale_running(conn: sqlite3.Connection, max_age_seconds: int = 3600) -> None:
    """Reset jobs stuck in 'running' back to 'pending' after a crash."""
    cutoff = datetime.now(UTC).timestamp() - max_age_seconds
    cutoff_str = datetime.fromtimestamp(cutoff, UTC).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE pipeline_jobs SET status = 'pending' WHERE status = 'running' AND updated_at < ?",
        (cutoff_str,),
    )


def _claim_job(conn: sqlite3.Connection, job_id: int) -> bool:
    """Atomically claim a pending/failed job for processing."""
    cur = conn.execute(
        "UPDATE pipeline_jobs SET status = 'running', updated_at = ? "
        "WHERE id = ? AND status IN ('pending', 'failed')",
        (_now(), job_id),
    )
    return cur.rowcount == 1


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
    """Replace one email's knowledge projections using the pipeline clock."""
    persist_enrichment(conn, email_id, result, _now, emit, sanitize_text)


def run_attachments_stage(conn: sqlite3.Connection, cfg: Config, limit: int) -> tuple[int, int]:
    _reset_stale_running(conn)
    done = failed = 0
    for job in _pending_jobs(conn, "attachments", cfg.enrich.max_attempts, limit):
        if not _claim_job(conn, job["job_id"]):
            continue
        try:
            extract_email_attachments(conn, job["id"], cfg.maildir.path)
            _mark(conn, job["job_id"], "done")
            done += 1
        except Exception as exc:
            _mark(conn, job["job_id"], "failed", str(exc)[:500])
            failed += 1
        conn.commit()
    return done, failed


def run_enrich_stage(
    conn: sqlite3.Connection, cfg: Config, limit: int, provider: LLMProvider | None = None
) -> tuple[int, int]:
    _reset_stale_running(conn)
    jobs = _pending_jobs(conn, "enrich", cfg.enrich.max_attempts, limit)
    if not jobs:
        return 0, 0
    provider = provider or make_provider(cfg.llm)
    done = failed = 0
    for job in jobs:
        if not _claim_job(conn, job["job_id"]):
            continue
        try:
            prompt = build_enrich_prompt(conn, job, cfg.llm)
            raw = provider.complete_json(ENRICH_SYSTEM, prompt)
            result = EnrichmentResult.model_validate(raw)
            store_enrichment(conn, job["id"], result)
            _mark(conn, job["job_id"], "done")
            done += 1
        except Exception as exc:
            _mark(conn, job["job_id"], "failed", str(exc)[:500])
            failed += 1
        conn.commit()
    return done, failed


def run_embed_stage(
    conn: sqlite3.Connection, cfg: Config, limit: int, embedder: Embedder | None = None
) -> tuple[int, int]:
    _reset_stale_running(conn)
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
        claimed = [j for j in batch if _claim_job(conn, j["job_id"])]
        if not claimed:
            continue
        texts = [embedding_input(j, cfg.embeddings.max_chars) for j in claimed]
        try:
            vectors = embedder.embed_documents(texts)
            store_embeddings(conn, [(j["id"], v) for j, v in zip(claimed, vectors, strict=True)])
            for j in claimed:
                _mark(conn, j["job_id"], "done")
            done += len(claimed)
        except Exception as exc:
            for j in claimed:
                _mark(conn, j["job_id"], "failed", str(exc)[:500])
            failed += len(claimed)
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
