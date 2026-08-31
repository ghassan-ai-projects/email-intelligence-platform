# Deferred Ideas and Improvements

This document contains suggestions discovered during the audit. They are not
implemented as part of the clean-code refactoring unless separately approved.

| Status | Area | Idea | Evidence / rationale |
|---|---|---|---|
| Open | MCP imports | Introduce a small registration/runtime context module so tool groups do not import the facade back into itself. | Current tool groups import `mcp`, `_audit_tool`, `get_config`, and `get_conn` from `mcp_server`; the import works and preserves test patch points, but the coupling deserves a separately tested design. |
| Open | MCP connections | Consider a shared context manager for per-tool SQLite connection lifecycle. | The tool groups repeat `get_conn()` plus `try/finally: conn.close()`; any future abstraction must preserve audit ordering and error behavior. |
| Open | MCP contract tests | Add an exact ordered `mcp.list_tools()` contract assertion covering names, input schemas, and descriptions. | The existing registration test checks only set containment; the independent review identified that it would miss reorderings, removals, additions, or metadata drift. |
| Open | Ingest failure telemetry | Add bounded counters or an operator-visible report for parse failures and guardrail failures that are currently intentionally ignored. | The existing behavior keeps one malformed message or scanner failure from aborting sync, but silent skips reduce diagnosability; any future change needs an explicit privacy and retry policy. |
| Open | Ingest account mapping | Replace hard-coded `account="default"` with an explicit account source when multi-account Maildir ingestion is designed. | The current behavior consistently uses the default account across emails, recipients, sync state, events, and guardrail results; changing it requires a schema and configuration decision. |
| Open | CLI diagnostics | Consider a consistent user-facing error/reporting policy for command failures and long-running `watch` iterations. | Current commands preserve their existing exception and exit behavior; a future diagnostics design should define redaction, exit codes, and whether errors are actionable without changing this compatibility refactor. |
| Open | Pipeline retry telemetry | Add explicit retry/lease telemetry for jobs reset from `running` or marked `failed`. | The current queue intentionally preserves its status and attempt semantics; richer observability or ownership leases would need a separate design and migration decision. |
| Open | Search result schemas | Introduce typed result models for search, detail, thread, and stats payloads after their compatibility shapes are formally specified. | Current callers consume stable dictionaries; typed models would improve contract clarity but could alter serialization and must be designed separately. |
| Open | Config contract types | Consider enums and numeric validators for provider names, enrichment stages, intervals, dimensions, and limits. | Current config accepts broad strings and integers for compatibility; stricter validation would be a behavior change requiring migration guidance. |
