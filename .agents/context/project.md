# Project Context

## What This Repo Is

`mailintel` is a local-first email intelligence platform. It ingests Maildir email into SQLite, enriches messages into knowledge artifacts, and exposes that knowledge through MCP tools for coding agents and assistants.

The primary product constraints are:

- email content is untrusted third-party input
- user data should stay local by default
- outgoing mail is draft-first or explicitly enabled
- every MCP tool call is audit logged
- tests use synthetic fixtures and fake providers, not real credentials

## Current State

- The import package is `mailintel` under `src/mailintel/`.
- The project uses `uv`, `hatchling`, and `pyproject.toml`.
- SQLite schema changes live in versioned migrations in `src/mailintel/db.py`.
- Enrichment and embedding providers are pluggable and tested with fakes.
- The MCP server is stdio-based and wraps tools with audit logging.

## What Agents Should Optimize For

- Preserve local-first behavior and safe defaults.
- Keep configuration explicit and documented in `config.example.toml`.
- Add tests for production behavior using synthetic Maildirs and fake providers.
- Keep README, `AGENTS.md`, `Makefile`, CI, and `pyproject.toml` in sync.

## Main Risks

- Trusting email content as instructions.
- Logging sensitive arguments or message bodies unnecessarily.
- Weakening SMTP allowlists, attachment fences, or rate limits.
- Introducing network-dependent tests.
- Adding abstractions before a current use case requires them.
