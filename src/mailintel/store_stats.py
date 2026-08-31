"""Store-level metrics used by search and operational commands."""

from __future__ import annotations

import sqlite3
from typing import Any


def get_stats(conn: sqlite3.Connection) -> dict:
    """Return counts, date range, folder totals, and pipeline job totals."""

    def one(sql: str, params: tuple = ()) -> Any:
        return conn.execute(sql, params).fetchone()[0]

    folders = [
        {"folder": row["folder"], "count": row["n"]}
        for row in conn.execute(
            "SELECT folder, COUNT(*) AS n FROM emails GROUP BY folder ORDER BY n DESC"
        )
    ]
    jobs = {
        f"{row['stage']}:{row['status']}": row["n"]
        for row in conn.execute(
            "SELECT stage, status, COUNT(*) AS n FROM pipeline_jobs GROUP BY stage, status"
        )
    }
    return {
        "emails": one("SELECT COUNT(*) FROM emails"),
        "threads": one("SELECT COUNT(*) FROM threads"),
        "enriched": one("SELECT COUNT(*) FROM emails WHERE enriched_at IS NOT NULL"),
        "action_items_open": one("SELECT COUNT(*) FROM action_items WHERE status = 'open'"),
        "facts": one("SELECT COUNT(*) FROM facts"),
        "entities": one("SELECT COUNT(*) FROM entities"),
        "date_range": {
            "first": one("SELECT MIN(date_utc) FROM emails"),
            "last": one("SELECT MAX(date_utc) FROM emails"),
        },
        "folders": folders,
        "pipeline_jobs": jobs,
    }
