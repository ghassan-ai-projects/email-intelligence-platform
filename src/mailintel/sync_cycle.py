"""Shared sync, ingest, and optional enrichment orchestration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import db, ingest as ingest_module, sync as sync_module
from .config import Config
from .enrich import pipeline as pipeline_module
from .enrich.pipeline import PipelineStats
from .ingest import IngestStats


@dataclass
class SyncCycle:
    """Results from one complete mailbox refresh."""

    sync_output: str
    ingest: IngestStats
    enrich: PipelineStats | None = None

    def as_dict(self) -> dict:
        result = {"sync": self.sync_output, "ingest": self.ingest.as_dict()}
        if self.enrich is not None:
            result["enrich"] = self.enrich.as_dict()
        return result


def run_sync_cycle(
    cfg: Config,
    enrich: bool = True,
    limit: int = 200,
    conn: sqlite3.Connection | None = None,
) -> SyncCycle:
    """Run external sync, ingestion, and optional enrichment on one connection."""
    sync_output = sync_module.run_sync(cfg) or "ok"
    def run(connection: sqlite3.Connection) -> tuple[IngestStats, PipelineStats | None]:
        ingest_stats = ingest_module.ingest(connection, cfg)
        enrich_stats = (
            pipeline_module.run_pipeline(connection, cfg, limit=limit) if enrich else None
        )
        return ingest_stats, enrich_stats

    if conn is not None:
        ingest_stats, enrich_stats = run(conn)
    else:
        with db.connection(cfg.storage.db_path) as connection:
            ingest_stats, enrich_stats = run(connection)
    return SyncCycle(sync_output, ingest_stats, enrich_stats)
