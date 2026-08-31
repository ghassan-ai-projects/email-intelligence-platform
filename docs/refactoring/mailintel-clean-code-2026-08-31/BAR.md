# Mailintel Clean-Code Refactoring Bar

This bar governs the file-by-file refactoring on branch
`codex/refactor-mailintel-clean-code-20260831`.

## Scope

- Inspect every production Python file under `src/` in descending size order.
- Do not refactor test files.
- Refactor only behavior-preserving structure unless a behavior improvement is
  explicitly recorded in `BEHAVIOR_CHANGES.md` and approved before implementation.
- Split files above 250 lines when the split has a clear module boundary and
  does not create speculative abstractions.

## Per-file completion criteria

For every inventory item, the tracking log must record:

1. A frozen candidate assessment with exact paths and line ranges.
2. The intended clean-code change or a justified no-change decision.
3. A read-only review of the implementation against the five requested principles.
4. Fixes for all review findings, or an explicit documented deferral.
5. A dedicated Conventional Commit for the file's production change, unless the
   file is a justified no-op; no-op decisions are still recorded.
6. A bar check confirming public interfaces, data shapes, errors, ordering,
   side-effect boundaries, security controls, and module ownership are unchanged.

Tests are intentionally deferred until the final gate, per the task request.
Static inspection, formatting, type, and diff checks may be used before then
only when they do not execute the test suite.

## Final completion criteria

- Every production Python file is assessed; test files remain out of scope.
- Every changed file has a per-file log entry and commit.
- No file remains above 250 lines without a documented, reviewed reason.
- The final test suite and repository checks pass, or failures are classified as
  pre-existing/environmental with evidence.
- `BEHAVIOR_CHANGES.md` and `IDEAS.md` contain all deferred behavior changes and
  suggested improvements discovered during the work.
- `git diff --check` passes and the final worktree status is reported.

## Final result

- PASS on 2026-08-31 for branch
  `codex/refactor-mailintel-clean-code-20260831`.
- All 28 baseline production Python files were handled: 7 refactored and 21
  assessed with no justified change.
- All 26 focused modules created by the refactors are below 250 lines; no
  production Python file in `src/` exceeds 250 lines.
- Each file has a candidate review record, implementation/no-change decision,
  review result, and commit or tracking checkpoint in `REFACTOR_LOG.md`.
- Final `make ci-check` passed: formatting, Ruff, mypy over 54 source files,
  117 tests, 79.05% coverage, and source/wheel builds.
- `BEHAVIOR_CHANGES.md` records no approved or implemented behavior changes;
  future improvements are listed only in `IDEAS.md`.
