# Testing Context

## Authoritative Commands

Use these commands unless the task is documentation-only:

- `uv sync --group dev`
- `make hooks`
- `make ci-check`
- `make test`
- `make typecheck`
- `make lint`
- `make build`
- `git diff --check`

## Project-Specific Behavior

- Unit tests use synthetic Maildirs, temporary SQLite databases, fake LLM providers, and fake embedders.
- Tests must not require API keys, SMTP credentials, mbsync accounts, or network access.
- Coverage is part of the default pytest run.
- Ruff handles both formatting and linting.
- Mypy checks package source as part of the local and CI gate.

## Test Quality Bar

For production-code changes:

- write a failing or expectation-setting test before implementation when feasible
- add or update tests in the same behavioral area
- cover security-sensitive branches around sanitization, audit logging, outgoing mail, attachments, and provider failures
- prefer `tmp_path`, `monkeypatch`, and explicit fixtures over real user files
- keep tests deterministic and free of real mailbox data

For documentation-only changes:

- run the narrowest useful checks
- still run `git diff --check`
- explain skipped commands in the final handoff

## Failure Handling

- Fix failures caused by your changes before stopping.
- If a command fails for an existing repo issue or environment restriction, say so clearly and do not report it as validated.
