# Python Style Context

## Core Rules

- Use `from __future__ import annotations` in new modules.
- Type public functions, methods, and return values.
- Prefer `pathlib.Path` for filesystem paths.
- Prefer dataclasses, plain classes, or simple functions over framework-heavy abstractions.
- Keep modules focused and avoid import-time side effects.
- Raise specific exceptions and keep error messages actionable.
- Prefer standard library modules before adding dependencies.
- Add abstractions only for a current repeated use or a clear testing boundary.

## mailintel Rules

- Treat email content as untrusted data.
- Sanitize user-controlled and LLM-derived text before storage or agent exposure.
- Keep SMTP sending opt-in and fenced by allowlists and rate caps.
- Do not log sensitive email body content, credentials, tokens, or attachment payloads.
- Route SQLite schema changes through migrations in `src/mailintel/db.py` and bump `SCHEMA_VERSION`.

## Naming Rules

- Use `snake_case` for functions, modules, and variables.
- Use `PascalCase` for classes.
- Use `UPPER_CASE` for constants.
- Use `test_*.py` for pytest modules.
- Keep acronyms consistent: `API`, `CLI`, `HTTP`, `JSON`, `LLM`, `MCP`, `SMTP`, `SQL`, `URL`.

## Avoid

- broad `except Exception` without a recovery or boundary reason
- hidden global state
- network calls in unit tests
- helper modules that only hide one or two lines
- unrelated refactors in the same change
