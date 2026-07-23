# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/) from its public release
line.

## [Unreleased]

### Added

- HTTP transport for the MCP server: `mailintel serve --transport http`
  exposes the same tool surface over Streamable HTTP on `/mcp`, with
  `[http]` config for host/port and an optional shared-token guard
  (`X-MAILINTEL-TOKEN` header), following the ALMS pattern. stdio remains
  the default.

## [0.1.0] - 2026-07-23

Initial public release.

### Added

- Maildir ingestion into a single SQLite file: parsing, sanitization,
  conversation threading, FTS5 full-text index, and attachment metadata.
- LLM enrichment pipeline with a resumable job queue: summaries, importance,
  sentiment, action items, entities, and structured facts per email. Works
  with any OpenAI-compatible provider (DeepSeek, Ollama, Groq, OpenRouter,
  OpenAI) or the native Anthropic API.
- Pluggable embeddings: hosted Voyage or fully local OpenAI-compatible
  endpoints such as Ollama, stored in sqlite-vec.
- MCP server over stdio with knowledge-level tools: semantic and full-text
  search, thread retrieval, action items, facts, decisions, sender summaries,
  waiting replies, daily digests, and attachment reading.
- Append-only event feed (`get_events_since`) for reactive agent loops.
- Agent write-back: tags, notes, importance, and completed action items.
- Draft-first outgoing mail with opt-in SMTP sending, recipient allowlists,
  attachment directory allowlists, and per-hour send-rate caps.
- Audit logging of every MCP tool call.
- Prompt-injection defenses: ingest sanitization, hardened enrichment
  prompts, and untrusted-content notices on tools that return mail content.
- Typer CLI: `init`, `sync`, `ingest`, `enrich`, `serve`, `watch`, `search`,
  and `stats`.

[0.1.0]: https://github.com/ghassan-ai-projects/email-intelligence-platform/releases/tag/v0.1.0
