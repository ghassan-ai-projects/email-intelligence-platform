# Agent Guide: mailintel

This is a local-first email intelligence platform. The source lives in
`src/mailintel/` and is packaged with `uv` + `pyproject.toml`.

Read this file first, then load only the `.agents/context/` files needed for
the task.

## Build & test

```sh
uv sync --group dev    # install dependencies
make ci-check          # format, lint, typecheck, test, build
make test              # run pytest with coverage
make lint              # run Ruff lint
make typecheck         # run mypy over package source
```

Tests use synthetic Maildirs, fake LLM providers, and fake embedders — no
external credentials are required.

## Read order

Before editing:

1. Read this file.
2. Read [README.md](README.md).
3. Check the worktree with `git status --short`.
4. Read the smallest relevant context files under `.agents/context/`.
5. Make a short plan before broad, security-sensitive, dependency-changing, or
   architectural work.

Start with these context files:

- [.agents/context/project.md](.agents/context/project.md) for repository scope.
- [.agents/context/architecture.md](.agents/context/architecture.md) for module boundaries.
- [.agents/context/testing.md](.agents/context/testing.md) for validation commands.
- [.agents/context/python-style.md](.agents/context/python-style.md) for coding conventions.
- [.agents/context/review-checklist.md](.agents/context/review-checklist.md) before handoff.

Use the prompt files under `.agents/prompts/` when the task matches them.

## Code conventions

- Python 3.12+.
- Line length 100 (`tool.ruff.line-length` in `pyproject.toml`).
- Prefer explicit types; import `from __future__ import annotations` in new modules.
- SQLite schema changes go through versioned migrations in `src/mailintel/db.py`.
- Every MCP tool in `src/mailintel/mcp_server.py` is automatically audit-logged by the
  `_audit_tool` decorator.
- Keep `README.md`, `config.example.toml`, `Makefile`, CI, and `pyproject.toml`
  consistent when commands or public behavior change.

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
5. Run `make ci-check` and `git diff --check` before committing.
