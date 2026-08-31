# Mailintel Quality Refactoring Bar — Round 2

This bar governs the repository-wide Python quality pass on branch
`codex/refactor-mailintel-clean-code-20260831`.

## Scope

- Review every Python file under `src/` and `tests/`.
- Keep style-only, formatting-only, and lint-only cleanup out of scope.
- Preserve local-first behavior, untrusted-content handling, MCP audit logging,
  draft-first sending, SMTP allowlists, attachment fences, and send-rate caps.
- Make only evidence-backed behavior-preserving refactors or test improvements.
- Do not add dependencies or speculative abstractions.

## Four-lens review requirement

Every Python file receives a read-only assessment from each of these lenses:

1. correctness
2. architecture and dependency boundaries
3. duplication, dead code, and stale compatibility surfaces
4. substantive clean implementation, maintainability, observability, and testability

Each actionable finding must include an exact absolute path, line range, impact,
confidence, and a focused verification. Style-only observations do not count as
findings. A finding is accepted only after source-level verification by the
integrating agent.

## Final result criteria

- All Python files are accounted for in the inventory and review summary.
- Every accepted finding is fixed or explicitly recorded as a justified deferral.
- Production behavior changes have meaningful tests; coverage tests prove
  behavior rather than merely execute lines.
- Combined branch coverage is at least 90%, enforced by pytest.
- Mypy and diff checks remain green as regression gates. Ruff and formatting
  are explicitly outside this round's scope; no time is spent on cosmetic
  cleanup. Packaging/build checks are reported separately when the offline
  environment cannot resolve the build backend.
- Each cohesive implementation/test slice has a Conventional Commit.
- Final review repeats all four lenses over the changed areas and finds no
  unresolved high- or medium-confidence actionable issue.
- No secrets, private mail, credentials, tokens, or machine-local data enter
  the repository.

## Evidence boundary

Fixtures, fake providers, and unit tests prove deterministic software behavior
only. They do not prove real-provider, SMTP, network, or physical-world behavior.
