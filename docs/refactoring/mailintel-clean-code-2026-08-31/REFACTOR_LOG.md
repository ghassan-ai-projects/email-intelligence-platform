# Refactoring Loop Log

This log is updated after each candidate review, implementation review, commit,
and bar check. Tests remain deferred until the final gate.

## Current state

- Branch: `codex/refactor-mailintel-clean-code-20260831`
- Baseline: `75d2247`
- Completed files: 7 refactored baseline files plus 5 assessed baseline files
  and 26 focused modules
- Candidate reviews received: 12
- Production commits: 7
- Tests run: 0 (intentional)

## File records

Detailed records will be added in largest-first order. Each record includes the
candidate review source, changed paths, review findings and fixes, commit, bar
result, and any deferred behavior or feature notes.

## `src/mailintel/guardrail/scanner.py` — candidate, implementation, review

- Baseline: 1,092 lines; no individual function exceeded 250 lines.
- Candidate reviewer: delegated read-only review, which identified the mixed
  detector contracts, eight detector implementations, configuration, scoring,
  and logging as the cohesive split boundary. It specifically required keeping
  detector order, warning text/order, score caps, shallow config merging,
  truncation state, and best-effort logging unchanged.
- Implementation: moved the detector contract and each detector into
  `guardrail/detectors/`, leaving `scanner.py` as the public orchestration and
  compatibility facade. `scanner.py` is now 208 lines; every new module is
  below 250 lines. Extracted scanner steps are named for their intent.
- Review findings: initial static review found export/import ordering, mutable
  class-constant annotations, unused protocol parameters, and line-length
  issues. These were fixed with no behavior change. An accidental duplicate
  `detectors/unicode.py` from the delegated task was removed; the retained
  implementation is `detectors/unicode_attack.py`.
- Checks before commit: Ruff check passed, Ruff format passed, Python bytecode
  compilation passed, and `git diff --check` passed. Tests were not run by
  design.
- Commit: `8fa82e5` (`refactor: split mailintel guardrail detectors`).
- Bar result: PASS. Compatibility exports remain available from
  `mailintel.guardrail.scanner`; no persistence schema, MCP, sending, or
  sanitization behavior was changed.

## `src/mailintel/mcp_server.py` — candidate, implementation, review

- Baseline: 878 lines; the file combined audit infrastructure, 32 MCP tools,
  draft/send workflows, and HTTP transport.
- Candidate reviewer: delegated review confirmed that the 32 public tool names
  and Python signatures were preserved and identified module import coupling,
  audit error handling, and HTTP middleware as the main review risks.
- Implementation: grouped tools into `mcp_tools/search.py`, `details.py`,
  `mail.py`, `knowledge.py`, `agent_loop.py`, and `drafts.py`; moved HTTP
  transport to `mcp_tools/http.py`; left configuration, connection ownership,
  audit logging, FastMCP creation, and public re-exports in `mcp_server.py`.
  The facade is now 183 lines and every new module is below 250 lines.
- Review findings and fixes: restored all original MCP tool docstrings and
  descriptions after the reviewer identified lost safety and contract guidance;
  preserved the original audit distinction between truthy error results and
  successful/falsey values; preserved tool registration order; and checked the
  registered surface as 32 names with matching signatures and docstrings. The
  reviewer also found mypy could not infer the shared FastMCP object in leaf
  modules; an explicit `mcp: FastMCP` annotation fixed all 32 type errors.
- Checks before commit: 32 tools registered in the original order, Ruff check
  and formatting passed, mypy passed for all 9 MCP source files, Python
  bytecode compilation passed, and `git diff --check` passed. Tests were not
  run by design.
- Commit: `273d723` (`refactor: split mailintel MCP tool groups`).
- Bar result: PASS. MCP audit logging, untrusted-content notices,
  draft-first sending, SMTP delegation, token middleware, and public facade
  compatibility remain intact.

## `src/mailintel/ingest.py` — candidate, implementation, review

- Baseline: 442 lines; the file combined RFC822 parsing, Maildir discovery,
  SQLite projections, incremental synchronization, cleanup, events, guardrail
  scanning, and thread maintenance.
- Candidate reviewer: delegated read-only review identified four cohesive
  boundaries: parser, Maildir helpers, relational/FTS/enrichment projections,
  and cleanup/thread maintenance. It called out preserving traversal order,
  duplicate-copy mapping, deletion order, guardrail failure isolation, and the
  final transaction commit.
- Implementation: extracted `ingest_parser.py`, `ingest_maildir.py`,
  `ingest_storage.py`, and `ingest_cleanup.py`; left `ingest.py` as a 202-line
  orchestration facade with explicit historical aliases. Every extracted
  module is below 250 lines, and public steps read as ingestion operations.
- Review findings and fixes: the first review identified missing historical
  parser/storage/threading exports, an added assertion that changed an
  impossible-DB error type, and a skipped empty-thread refresh call. The
  follow-up identified that legacy private names were importable but not used
  as internal patch points. All findings were fixed; the facade now dispatches
  through the compatibility aliases and preserves the baseline call/order
  boundaries.
- Checks before commit: Ruff check and formatting passed, mypy passed for all
  five ingestion source files, Python bytecode compilation passed, and
  `git diff --check` passed. Tests were not run by design.
- Commit: `309444a` (`refactor: split mailintel ingest responsibilities`).
- Bar result: PASS. Maildir sanitization, duplicate mapping,
  guardrail isolation, audit/event behavior, enrichment job filtering, and
  schema usage remain unchanged.

## `src/mailintel/db.py` — candidate, implementation, review

- Baseline: 334 lines; the file combined four versioned schema scripts,
  connection setup, migrations, contact import, and metadata accessors.
- Candidate reviewer: delegated read-only review selected the schema scripts as
  the only required cohesive extraction for the 250-line bar. It required
  preserving the SQL byte-for-byte, migration order, sqlite-vec loading,
  transaction ownership, and all public/private names.
- Implementation: moved `_SCHEMA`, `_SCHEMA_V2`, `_SCHEMA_V3`, and `_SCHEMA_V4`
  into `db_schema.py`, retaining explicit re-exports from `db.py`. The facade
  is now 115 lines; the schema module is 222 lines.
- Review findings: no actionable findings. Static review confirmed exact SQL
  equality, preserved connection pragmas and extension lifecycle, unchanged
  migration order and commit semantics, and unchanged contact/meta behavior.
- Checks before commit: Ruff check and formatting passed, mypy passed for both
  database modules, Python bytecode compilation passed, the four SQL literals
  compared equal to baseline, and `git diff --check` passed. Tests were not run
  by design.
- Commit: `608b313` (`refactor: separate mailintel schema scripts`).
- Bar result: PASS. No schema version, migration, connection,
  contact-import, or metadata behavior changed.

## `src/mailintel/cli.py` — candidate, implementation, review

- Baseline: 296 lines; the file combined Typer command registration, setup
  scaffolding, sync/enrichment flows, watch-loop behavior, search, and store
  maintenance commands.
- Candidate reviewer: delegated read-only review selected the configuration
  template and `init` implementation as the only cohesive extraction needed for
  the 250-line bar. It required preserving command names/options, output text,
  lazy imports, connection closure, watch timing, and exit behavior.
- Implementation: moved setup scaffolding into `cli_setup.py`, leaving
  `cli.py` as a 247-line command facade. `CONFIG_TEMPLATE`, `config_path`, and
  `DEFAULT_CONFIG_DIR` remain available and are passed through the wrapper so
  historical import and monkeypatch seams still work.
- Review findings and fixes: the first review found that two setup symbols were
  no longer exposed and the template export was inert for monkeypatching. The
  wrapper and helper were changed to pass the current facade bindings. The
  follow-up review found no remaining issues; command registration, options,
  defaults, output, and timing remained unchanged.
- Checks before commit: Ruff check and formatting passed, mypy passed for both
  CLI modules, Python bytecode compilation passed, the configuration template
  compared equal to baseline, and `git diff --check` passed. Tests were not run
  by design.
- Commit: `44f5a96` (`refactor: separate mailintel CLI setup`).
- Bar result: PASS. No command, configuration-path, output,
  exit-code, connection-lifecycle, or subprocess behavior changed.

## `src/mailintel/enrich/pipeline.py` — candidate, implementation, review

- Baseline: 287 lines; the file combined queue state transitions, enrichment
  persistence, three stage runners, and stage-order orchestration.
- Candidate reviewer: delegated read-only review proposed the queue helpers as
  one possible extraction and required preserving claims, stale recovery,
  retries, commits, provider boundaries, stage order, and compatibility seams.
- Implementation: extracted the enrichment persistence projection and event
  writer into `enrich/enrichment_storage.py`, leaving queue state and stage
  runners together. `pipeline.py` is now 197 lines and the storage module is
  115 lines. A three-argument `store_enrichment` wrapper remains in the facade.
- Review findings and fixes: the first review found that moving persistence
  would hide the historical `pipeline.emit` and `pipeline.sanitize_text`
  bindings. The wrapper now passes those live facade callbacks, along with the
  facade `_now`, into the extracted function. The follow-up found no remaining
  issues; SQL, sanitization, event, timestamp, stage, and commit ordering are
  preserved.
- Checks before commit: Ruff check and formatting passed, mypy passed for both
  pipeline modules, Python bytecode compilation passed, and `git diff --check`
  passed. Tests were not run by design.
- Commit: `2dd453a` (`refactor: separate enrichment persistence`).
- Bar result: PASS. Queue claims/retries, provider and embedder
  boundaries, persistence projections, event emission, and stage ordering are
  unchanged.

## `src/mailintel/search.py` — candidate, implementation, review

- Baseline: 251 lines; the file combined FTS/filter search, email and thread
  details, thread search, and store statistics.
- Candidate reviewer: delegated read-only review selected `get_stats` as a
  cohesive store-metrics boundary, requiring its query order, result shape,
  public export, and all search/detail query behavior to remain unchanged.
- Implementation: moved `get_stats` into `store_stats.py` and re-exported the
  same callable from `search.py`. The facade is now 223 lines and the new
  metrics module is 40 lines.
- Review findings: no actionable findings. Static review confirmed exact stats
  queries, ordering, result shape, limits, FTS/LIKE/date/tag handling,
  guardrail warning parsing, and the `_like_escape` patch point.
- Checks before commit: Ruff check and formatting passed, mypy passed for both
  search modules, Python bytecode compilation passed, public signature/export
  checks passed, and `git diff --check` passed. Tests were not run by design.
- Commit: `3770576` (`refactor: separate search store statistics`).
- Bar result: PASS. Search result shapes, sanitization,
  guardrail exposure, query limits, SQL ordering, and stats output remain
  unchanged.

## `src/mailintel/config.py` — candidate, implementation, review

- Baseline: 248 lines; the file defines the shared configuration constants,
  dotenv loading, path expansion, section models, scanner flattening, and TOML
  loading contract.
- Candidate reviewer: delegated read-only review recommended no code change.
  The module is cohesive, already below 250 lines, and splitting model families
  or loader helpers would fragment the public configuration API.
- Implementation: no production code change. The existing model defaults,
  environment precedence, secret/token properties, path expansion, validation,
  scanner configuration flattening, and public symbols were preserved.
- Review findings: no actionable findings. The candidate explicitly covered
  `.env` setdefault behavior, configuration overrides, mutable-list isolation,
  missing/present TOML behavior, and consumer compatibility.
- Checks for the no-change bar: baseline comparison for `config.py` is empty
  and `git diff --check` passed. Tests were not run by design.
- Bar result: PASS (assessed, no code change). No refactor is justified for
  this file without a separate configuration-contract decision.

## `src/mailintel/guardrail/threat_profiles.py` — candidate, implementation, review

- Baseline: 221 lines; the file is the single source of truth for guardrail
  attack-pattern data and its two regex compilation helpers.
- Candidate reviewer: delegated read-only review recommended no code change.
  Splitting security profile categories would scatter the contract and add
  import/patch compatibility risk without approaching the size limit.
- Implementation: no production code change. Every profile constant, list/dict
  ordering, regex flag, compiler shape, and detector import path is preserved.
- Review findings: no actionable findings. Detector consumers and the
  scanner's sanitization/scoring boundary were explicitly checked.
- Checks for the no-change bar: baseline comparison for the file is empty and
  `git diff --check` passed. Tests were not run by design.
- Bar result: PASS (assessed, no code change). Any typed profile model,
  compilation cache, or external profile format belongs in a separate design.

## `src/mailintel/knowledge.py` — candidate, implementation, review

- Baseline: 213 lines; the file is a cohesive knowledge/read model for action
  items, facts, decisions, sender summaries, waiting replies, and daily
  summaries.
- Candidate reviewer: delegated read-only review recommended no code change.
  Splitting by query would fragment the public knowledge API without
  approaching the size limit.
- Implementation: no production code change. Existing wildcard escaping,
  limits, SQL predicates/order, date calculations, source context, result
  shapes, and public symbols remain unchanged.
- Review findings: no actionable findings. MCP consumers, untrusted-content
  boundaries, and private helper compatibility were checked.
- Checks for the no-change bar: baseline comparison for the file is empty and
  `git diff --check` passed. Tests were not run by design.
- Bar result: PASS (assessed, no code change). Query builders, typed result
  schemas, pagination, or deterministic ordering need a separate contract
  decision.

## `src/mailintel/guardrail/contacts.py` — candidate, implementation, review

- Baseline: 203 lines; the file is one cohesive `ContactsDB` domain object with
  shared address normalization, value objects, lookup/list reads, mutations,
  interaction writes, commits, and JSON import.
- Candidate reviewer: delegated read-only review recommended no code change.
  Splitting methods would fragment transaction ownership and the public contact
  API without approaching the size limit.
- Implementation: no production code change. Normalization, ordering, tier
  validation, defaults, commit boundaries, interaction sequence, import count,
  and public exports remain unchanged.
- Review findings: no actionable findings for this refactor. The candidate
  explicitly preserved the current asymmetry where invalid tiers are validated
  for existing contacts but not new rows.
- Checks for the no-change bar: baseline comparison for the file is empty and
  `git diff --check` passed. Tests were not run by design.
- Bar result: PASS (assessed, no code change). Tier validation consistency or
  other contact policy changes require a separate security review.

## `src/mailintel/drafts.py` — candidate, implementation, review

- Baseline: 199 lines; the file is a cohesive draft lifecycle covering
  serialization, sanitized CRUD, transaction ownership, atomic send claiming,
  sender guardrails, and sent-state events.
- Candidate reviewer: delegated read-only review recommended no code change.
  Splitting CRUD from sending would fragment the draft state machine and risk
  its safety/monkeypatch seams without a size-limit need.
- Implementation: no production code change. Recipient and attachment JSON
  handling, sanitization, status transitions, commits, sender delegation,
  rollback, event payloads, and public MCP-facing functions remain unchanged.
- Review findings: no actionable findings. Draft-first behavior, attachment
  fences, allowlists, rate-cap delegation, and module-level compatibility seams
  were explicitly checked.
- Checks for the no-change bar: baseline comparison for the file is empty and
  `git diff --check` passed. Tests were not run by design.
- Bar result: PASS (assessed, no code change). Stronger recipient normalization,
  status transition modeling, or an outbox would require a separate safety and
  transaction design.
