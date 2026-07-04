# Architecture Context

## Repository Structure

- `src/mailintel/`: importable package
- `tests/`: pytest suites with synthetic Maildirs and fake providers
- `docs/`: durable setup and operations notes
- `config.example.toml`: documented configuration surface
- `AGENTS.md`: canonical agent entrypoint
- `Makefile`: authoritative local development commands
- `.github/workflows/ci.yml`: CI parity for core checks

## Module Boundaries

- `cli.py`: Typer CLI entrypoint; keep orchestration thin.
- `config.py`: Pydantic settings and environment overrides.
- `db.py`: SQLite connection, migrations, and `sqlite-vec` loading.
- `ingest.py`: Maildir parsing, sanitization, indexing, and attachment metadata.
- `threading_.py`: conversation threading.
- `search.py` and `knowledge.py`: read-side query behavior.
- `enrich/`: LLM enrichment, embeddings, attachment extraction, and queue processing.
- `events.py`: append-only event feed.
- `actions.py`: agent write-back.
- `drafts.py`: draft-first outgoing mail state.
- `sender.py`: SMTP sending guardrails and rate caps.
- `mcp_server.py`: stdio MCP tool surface and audit wrappers.

## Dependency Direction

- CLI and MCP entrypoints call module-level services.
- Services depend on config, database helpers, and domain models.
- External I/O stays at boundaries: filesystem, SQLite, LLM APIs, SMTP, and mbsync.
- Tests should exercise stable public functions and tool behavior when practical.

Avoid:

- circular imports
- business logic hidden in CLI command bodies
- untested schema changes
- new global mutable state
- speculative adapter layers with no current consumer
