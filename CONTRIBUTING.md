# Contributing

mailintel is a local-first email intelligence platform. Contributions should preserve that shape: user mail stays local, write-back is explicit, and sending remains opt-in and guarded.

## Before You Start

1. Read [AGENTS.md](AGENTS.md).
2. Check existing issues and pull requests for related work.
3. Keep changes focused. Avoid mixing tooling, docs, and behavior changes unless they must ship together.
4. Run `git status --short` before editing so you do not overwrite someone else's work.

## Development Workflow

Use this loop for non-trivial changes:

1. Clarify the goal, constraints, affected files, and risks.
2. Choose the simplest correct path and the checks that will validate it.
3. Write the proving test before implementation when feasible for behavior changes.
4. Implement a cohesive, reviewable diff.
5. Validate the change locally.
6. Summarize checks run, skipped checks, remaining risk, and any security impact.

## Definition of Done

A change is done when:

- The requested scope is complete without unrelated refactors.
- Production-code behavior changes include meaningful tests.
- `make ci-check` passes, unless the change is documentation-only and a narrower check is clearly sufficient.
- `git diff --check` passes.
- Documentation is updated when behavior, commands, setup, or agent expectations change.
- Secrets, credentials, customer mail, and machine-local data are not committed.
- Security-sensitive changes call out impact on ingestion sanitization, prompt-injection handling, MCP audit logging, drafts, SMTP allowlists, or rate limits.
- `Makefile`, `pyproject.toml`, CI, hooks, and documented commands agree.

```sh
make help
make hooks
make ci-check
```

## Pull Request Expectations

Every PR should include:

- A short summary of what changed and why.
- Tests or checks run.
- Whether test-first was used for behavior changes, and if not, why not.
- Any skipped checks and the reason.
- Any new dependency, generated file, security implication, or migration step.
- Updates to [AGENTS.md](AGENTS.md) when the change affects future agent behavior.

## Commit Style

Use Conventional Commits:

- `feat:` for user-visible features
- `fix:` for bug fixes
- `docs:` for documentation
- `test:` for tests
- `ci:` for CI changes
- `build:` for build tooling
- `chore:` for maintenance

## Agent Contributions

Agent-authored changes are welcome, but the handoff must be reviewable:

- Keep diffs small enough for a human to audit.
- Prefer existing patterns over new abstractions.
- Do not commit secrets, private email, credentials, cookies, tokens, or private keys.
- Include command output summaries rather than noisy logs.
