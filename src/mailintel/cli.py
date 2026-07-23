"""mailintel command-line interface."""

from __future__ import annotations

import json
import time

import typer

from . import db
from .config import DEFAULT_CONFIG_DIR, Config, config_path, load_config

app = typer.Typer(
    name="mailintel",
    help="Local-first email intelligence platform (Maildir -> knowledge base -> MCP).",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

CONFIG_TEMPLATE = """\
# mailintel configuration. Secrets stay in ~/.mailintel/.env (auto-loaded):
#   EMAIL_USER / EMAIL_PASSWORD, DEEPSEEK_API_KEY, VOYAGE_API_KEY, ...
# See config.example.toml in the repo for every option (Ollama embeddings,
# SMTP sending with guardrails, GMX folder names, ...).

[storage]
db_path = "{db_path}"

[maildir]
path = "~/Mail"                     # or set MAILINTEL_MAILDIR
sent_folders = ["Sent", "Sent Mail", "Sent Messages", "Sent Items", "Gesendet"]
exclude_folders = ["Trash", "Spam", "Junk", "Drafts", "Papierkorb", "Entwürfe"]

[sync]
command = "mbsync -a"
interval_minutes = 5

[llm]
provider = "openai-compat"          # or "anthropic"
base_url = "https://api.deepseek.com"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"

[embeddings]
provider = "voyage"                 # or "openai-compat" (e.g. local Ollama)
model = "voyage-3.5-lite"
api_key_env = "VOYAGE_API_KEY"
dimensions = 1024

[smtp]
enabled = false                     # opt-in: allows the send_email MCP tool
host = ""
allowed_recipients = []             # guardrail, e.g. ["*@mycompany.com"]
"""


def _cfg() -> Config:
    return load_config()


def _echo_json(data: object) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


@app.command()
def init() -> None:
    """Create ~/.mailintel/config.toml and print setup guidance."""
    path = config_path()
    if path.exists():
        typer.echo(f"Config already exists: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CONFIG_TEMPLATE.format(db_path=str(DEFAULT_CONFIG_DIR / "mail.db")))
        typer.echo(f"Wrote {path}")
    typer.echo(
        "\nNext steps:\n"
        "  1. Install mbsync:        brew install isync\n"
        "  2. Configure ~/.mbsyncrc  (see docs/mbsync-setup.md in the repo)\n"
        "  3. Edit the [maildir] path in the config to your mbsync target\n"
        "     (or set the MAILINTEL_MAILDIR environment variable)\n"
        "  4. Put secrets in ~/.mailintel/.env — EMAIL_USER, EMAIL_PASSWORD,\n"
        "     DEEPSEEK_API_KEY (or your provider), VOYAGE_API_KEY\n"
        "  5. Run:                   mailintel sync && mailintel enrich\n"
        "  6. Register MCP server:   claude mcp add mailintel -- mailintel serve"
    )


@app.command()
def sync(
    enrich_after: bool = typer.Option(True, help="Run the enrichment queue after ingesting."),
    limit: int = typer.Option(200, help="Max enrichment jobs per stage."),
) -> None:
    """Run mbsync, ingest new mail, then (optionally) enrich."""
    from .enrich.pipeline import run_pipeline
    from .ingest import ingest as run_ingest
    from .sync import run_sync

    cfg = _cfg()
    typer.echo(f"Running: {cfg.sync.command}")
    run_sync(cfg)
    conn = db.connect(cfg.storage.db_path)
    try:
        stats = run_ingest(conn, cfg)
        typer.echo(f"Ingest: {stats.as_dict()}")
        if enrich_after:
            pstats = run_pipeline(conn, cfg, limit=limit)
            typer.echo(f"Enrich: {pstats.as_dict()}")
    finally:
        conn.close()


@app.command()
def ingest() -> None:
    """Scan the Maildir and index new/changed/removed messages."""
    from .ingest import ingest as run_ingest

    cfg = _cfg()
    conn = db.connect(cfg.storage.db_path)
    try:
        stats = run_ingest(conn, cfg)
    finally:
        conn.close()
    _echo_json(stats.as_dict())


@app.command()
def enrich(
    limit: int = typer.Option(200, help="Max jobs per stage in this run."),
    stage: str = typer.Option(None, help="Run one stage only: attachments | enrich | embed."),
) -> None:
    """Process the enrichment queue (attachments -> LLM enrichment -> embeddings)."""
    from .enrich.pipeline import run_pipeline

    cfg = _cfg()
    if stage:
        cfg = cfg.model_copy(deep=True)
        cfg.enrich.stages = [stage]
    conn = db.connect(cfg.storage.db_path)
    try:
        stats = run_pipeline(conn, cfg, limit=limit)
    finally:
        conn.close()
    _echo_json(stats.as_dict())


@app.command()
def serve(
    transport: str = typer.Option("stdio", help="MCP transport: stdio | http."),
    host: str = typer.Option(None, help="HTTP bind host (default: [http] host in config)."),
    port: int = typer.Option(None, help="HTTP bind port (default: [http] port in config)."),
) -> None:
    """Run the MCP server (stdio by default; --transport http for Streamable HTTP)."""
    from .mcp_server import main as serve_main

    if transport not in ("stdio", "http"):
        raise typer.BadParameter("transport must be 'stdio' or 'http'")
    serve_main(transport=transport, host=host, port=port)


@app.command()
def watch() -> None:
    """Loop forever: sync + ingest + enrich every sync.interval_minutes."""
    from .enrich.pipeline import run_pipeline
    from .ingest import ingest as run_ingest
    from .sync import SyncError, run_sync

    cfg = _cfg()
    interval = max(1, cfg.sync.interval_minutes) * 60
    typer.echo(f"Watching: sync every {cfg.sync.interval_minutes} min (Ctrl-C to stop)")
    while True:
        started = time.monotonic()
        try:
            run_sync(cfg)
            conn = db.connect(cfg.storage.db_path)
            try:
                istats = run_ingest(conn, cfg)
                pstats = run_pipeline(conn, cfg, limit=200)
            finally:
                conn.close()
            if istats.new or istats.deleted or pstats.done:
                typer.echo(
                    f"[{time.strftime('%H:%M:%S')}] ingest={istats.as_dict()} "
                    f"enrich={pstats.as_dict()}"
                )
        except SyncError as exc:
            typer.echo(f"[{time.strftime('%H:%M:%S')}] sync error: {exc}", err=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            typer.echo(f"[{time.strftime('%H:%M:%S')}] error: {exc}", err=True)
        time.sleep(max(5.0, interval - (time.monotonic() - started)))


@app.command()
def search(
    query: str = typer.Argument(..., help="Full-text query."),
    limit: int = typer.Option(10),
    semantic: bool = typer.Option(False, "--semantic", help="Use vector search instead of FTS."),
) -> None:
    """Quick search from the terminal (debugging aid)."""
    from . import search as search_mod

    cfg = _cfg()
    conn = db.connect(cfg.storage.db_path)
    try:
        if semantic:
            from .enrich.embeddings import knn_email_ids, make_embedder

            embedder = make_embedder(cfg.embeddings)
            hits = knn_email_ids(conn, embedder.embed_query(query), limit)
            results = []
            for eid, dist in hits:
                row = conn.execute("SELECT * FROM emails WHERE id = ?", (eid,)).fetchone()
                if row:
                    results.append(search_mod.email_row_brief(row, {"distance": round(dist, 4)}))
        else:
            results = search_mod.search_emails(conn, query=query, limit=limit)
    finally:
        conn.close()
    _echo_json(results)


@app.command()
def stats() -> None:
    """Show store statistics."""
    from .search import get_stats

    cfg = _cfg()
    conn = db.connect(cfg.storage.db_path)
    try:
        _echo_json(get_stats(conn))
    finally:
        conn.close()


@app.command()
def contacts_import(
    path: str = typer.Argument(
        None,
        help="JSON file to import (defaults to ~/.mailintel/contacts.json).",
    ),
) -> None:
    """Import contacts from a JSON file into the contacts table."""
    cfg = _cfg()
    conn = db.connect(cfg.storage.db_path)
    try:
        count = db.import_contacts_json(conn, path)
    finally:
        conn.close()
    typer.echo(f"Imported {count} contacts")


@app.command()
def audit(
    limit: int = typer.Option(50, help="Maximum rows to return."),
    tool: str = typer.Option(None, help="Filter by tool name."),
) -> None:
    """Inspect the MCP tool audit log."""
    cfg = _cfg()
    conn = db.connect(cfg.storage.db_path)
    try:
        if tool:
            rows = conn.execute(
                "SELECT id, tool, args, caller, account, result_summary, error, created_at "
                "FROM audit_log WHERE tool = ? ORDER BY id DESC LIMIT ?",
                (tool, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, tool, args, caller, account, result_summary, error, created_at "
                "FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    _echo_json([dict(r) for r in rows])


@app.command()
def events_prune(
    before_id: int = typer.Argument(..., help="Delete events with id lower than this."),
) -> None:
    """Prune old events from the event log."""
    from .events import prune_events

    cfg = _cfg()
    conn = db.connect(cfg.storage.db_path)
    try:
        deleted = prune_events(conn, before_id)
    finally:
        conn.close()
    typer.echo(f"Deleted {deleted} events")


if __name__ == "__main__":
    app()
