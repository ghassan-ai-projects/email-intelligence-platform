# Agent Guide: mailintel

This is a local-first email intelligence platform. The source lives in
`src/mailintel/` and is packaged with `uv` + `pyproject.toml`.

## Build & test

```sh
uv sync                # install dependencies
uv run pytest -q       # run the test suite (no API keys needed)
uv run ruff check .    # lint
```

Tests use synthetic Maildirs, fake LLM providers, and fake embedders — no
external credentials are required.

## Code conventions

- Python 3.12+.
- Line length 100 (`tool.ruff.line-length` in `pyproject.toml`).
- Prefer explicit types; import `from __future__ import annotations` in new modules.
- SQLite schema changes go through versioned migrations in `src/mailintel/db.py`.
- Every MCP tool in `src/mailintel/mcp_server.py` is automatically audit-logged by the
  `_audit_tool` decorator.

## Module layout

| File | Responsibility |
|---|---|
| `db.py` | SQLite connection, migrations, `sqlite-vec` loading. |
| `config.py` | Pydantic config with env-var overrides. |
| `ingest.py` | Maildir → SQLite parsing and indexing. |
| `threading_.py` | Conversation threading. |
| `search.py` / `knowledge.py` | Read-side queries. |
| `enrich/` | LLM enrichment, embeddings, pipeline queue. |
| `events.py` | Append-only event feed. |
| `actions.py` | Agent write-back. |
| `drafts.py` | Draft-first outgoing mail. |
| `sender.py` | SMTP sending with guardrails and rate caps. |
| `mcp_server.py` | MCP tool surface over stdio. |
| `cli.py` | Typer CLI. |

## Security notes

- Email content is treated as untrusted third-party input.
- Sending is opt-in (`[smtp] enabled = true`) and fenced by `allowed_recipients`.
- Outgoing mail is rate-limited via `smtp.max_sends_per_hour`.
- The audit log records every MCP tool call; be cautious about logging sensitive
  arguments.

## When adding features

1. Add or update the schema migration in `db.py` and bump `SCHEMA_VERSION`.
2. Update `config.py` for new tunables, with defaults that keep the project safe
   (e.g., sending off by default, low rate caps).
3. Add tests in `tests/` mirroring the module under test.
4. Update `README.md` and `config.example.toml`.
5. Run `uv run pytest -q && uv run ruff check .` before committing.
