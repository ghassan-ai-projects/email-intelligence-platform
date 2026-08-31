# Deferred Ideas and Improvements

This document contains suggestions discovered during the audit. They are not
implemented as part of the clean-code refactoring unless separately approved.

| Status | Area | Idea | Evidence / rationale |
|---|---|---|---|
| Open | MCP imports | Introduce a small registration/runtime context module so tool groups do not import the facade back into itself. | Current tool groups import `mcp`, `_audit_tool`, `get_config`, and `get_conn` from `mcp_server`; the import works and preserves test patch points, but the coupling deserves a separately tested design. |
| Open | MCP connections | Consider a shared context manager for per-tool SQLite connection lifecycle. | The tool groups repeat `get_conn()` plus `try/finally: conn.close()`; any future abstraction must preserve audit ordering and error behavior. |
| Open | MCP contract tests | Add an exact ordered `mcp.list_tools()` contract assertion covering names, input schemas, and descriptions. | The existing registration test checks only set containment; the independent review identified that it would miss reorderings, removals, additions, or metadata drift. |
