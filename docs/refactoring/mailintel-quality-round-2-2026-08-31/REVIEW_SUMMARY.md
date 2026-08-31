# Review summary

This round covered the complete Python inventory: 58 production files and 26
test/support files. The execution order followed the recorded descending-size
inventory, with shared contract work handled first where a larger module
depended on it.

Four read-only review lanes were used for the baseline and changed areas:
correctness, architecture, duplication/dead code, and substantive clean
implementation. The returned findings were source-verified before changes were
made. Style-only and lint-only observations were intentionally excluded.

## Findings closed

- MCP runtime ownership and import-cycle coupling were moved into a neutral
  runtime module with one invocation connection.
- Audit arguments and result summaries now retain bounded metadata only, and a
  durable `in_progress` audit intent is written before tool effects.
- SMTP rate limits use durable reservations; invalid recipients, refused
  recipients, and ambiguous post-DATA failures have distinct safe outcomes.
- Draft sends persist claims, reconcile stale claims to `unknown`, and never
  automatically retry ambiguous delivery.
- Event polling uses one SQLite snapshot and has a deterministic interleaving
  regression test for filtered cursors.
- Ingest now observes parse failures, separates scanner failures from database
  persistence failures, and refreshes projections after duplicate-copy removal.
- Enrichment stage names and attachment access have one shared boundary;
  pipeline execution requires an explicit clean transaction contract.
- Guardrail schema ownership is canonical, scanner state is request-local, and
  scan logging is metadata-only with an injectable writer seam.
- LLM/provider adapters, attachment identity, contact imports, action
  completion, waiting-reply timestamps, and sanitized enrichment projections
  have focused behavior coverage.
- Duplicate test provider fakes and obsolete internal helpers were removed.

## Evidence

- `COVERAGE_FILE=/tmp/mailintel-final-coverage-3 PYTHONPATH=src .venv/bin/pytest -q`:
  188 passed; 90.76% combined branch coverage; the configured 90% threshold
  passed.
- `PYTHONPATH=src .venv/bin/mypy src`: passed for 58 source files.
- `PYTHONPATH=src .venv/bin/python -m compileall -q src tests`: passed.
- `git diff --check`: passed.
- The repository is clean after commits `a7dbc5b`, `7949442`, `dd48e87`,
  `98c643e`, and `f4b4842`.

## Boundaries

The tests use synthetic Maildirs, fake providers, fake embedders, and fake
SMTP. They prove deterministic local behavior only; they do not prove live
provider, SMTP-server, or network behavior. Ruff/formatting and the `uv`-based
build path were not used as acceptance gates because the user explicitly
excluded style work and the environment could not resolve `hatchling` offline.
