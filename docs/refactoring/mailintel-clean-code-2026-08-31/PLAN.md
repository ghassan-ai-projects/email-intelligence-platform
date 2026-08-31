# Mailintel Clean-Code Refactoring Plan

## Operating loop

Each production file follows this sequence:

1. Freeze the file's bar and scope.
2. Obtain a read-only candidate review from a sub-agent.
3. Implement the smallest cohesive behavior-preserving change.
4. Perform an independent review and fix findings.
5. Commit the file-scoped change.
6. Re-check the bar and update the inventory.

Tests were not run during the per-file loop. They ran once at the final gate.

## Constraints

- Production code is under `src/mailintel/`; tests are excluded.
- Email, attachment, provider, and LLM content remain untrusted.
- MCP audit logging, local-first defaults, draft-first sending, recipient
  allowlists, attachment fences, and rate limits must remain intact.
- No new dependencies or speculative features are introduced.
- Suggestions discovered during review go to `IDEAS.md` only.
- Behavior changes go to `BEHAVIOR_CHANGES.md` and are not silently implemented.

## Work order

Largest files are assessed first. Files at or above 250 lines are split only
where the resulting modules have clear responsibilities. Smaller files still
receive a candidate assessment and a bar decision.

## Completion evidence

- 28 candidate reviews completed in largest-first order.
- 7 production refactor commits completed; no-change files are recorded as
  assessed checkpoints.
- Final `make ci-check`: PASS, 117 tests, 79.05% coverage.
