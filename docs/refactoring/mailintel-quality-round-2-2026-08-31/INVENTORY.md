# File-by-file order

The source order is descending `wc -l` as of the implementation pass. Each
file is reviewed through correctness, architecture, duplication/dead-code, and
clean-implementation lenses before its slice is accepted. Tests are paired
with the production file they exercise; no style-only changes are tracked.

## Production Python files

| Order | File | Lines | Status |
|---:|---|---:|---|
| 1 | `src/mailintel/config.py` | 254 | reviewed; behavior fixes applied |
| 2 | `src/mailintel/cli.py` | 234 | reviewed; adapter/orchestration fixes applied |
| 3 | `src/mailintel/db_schema.py` | 231 | reviewed; schema authority consolidated |
| 4 | `src/mailintel/search.py` | 228 | reviewed; query boundary fix applied |
| 5 | `src/mailintel/ingest.py` | 222 | reviewed; transaction/error/projection fixes applied |
| 6 | `src/mailintel/guardrail/threat_profiles.py` | 221 | reviewed; no substantive change required |
| 7 | `src/mailintel/knowledge.py` | 218 | reviewed; timestamp correctness fix applied |
| 8 | `src/mailintel/guardrail/contacts.py` | 216 | reviewed; validation/import fixes applied |
| 9 | `src/mailintel/drafts.py` | 213 | reviewed; durable claim/unknown outcome fixes applied |
| 10 | `src/mailintel/guardrail/scanner.py` | 208 | reviewed; private log-content fix applied |
| 11 | `src/mailintel/enrich/pipeline.py` | 204 | reviewed; queue/ordering fixes applied |
| 12 | `src/mailintel/sender.py` | 195 | reviewed; recipient/dead-code fixes applied |
| 13 | `src/mailintel/mcp_tools/runtime.py` | 184 | reviewed; neutral runtime extracted |
| 14 | `src/mailintel/enrich/enrichment_storage.py` | 156 | reviewed; provider-field/action identity fixes applied |
| 15 | `src/mailintel/enrich/embeddings.py` | 152 | reviewed; no substantive change required |
| 16 | `src/mailintel/ingest_parser.py` | 146 | reviewed; malformed-address fix applied |
| 17 | `src/mailintel/enrich/attachments.py` | 146 | reviewed; attachment identity fix applied |
| 18 | `src/mailintel/mcp_tools/drafts.py` | 136 | reviewed; config-aware scan/runtime fix applied |
| 19 | `src/mailintel/mcp_tools/knowledge.py` | 130 | reviewed; shared sync service/runtime fix applied |
| 20 | `src/mailintel/ingest_storage.py` | 118 | reviewed; no substantive change required |
| 21 | `src/mailintel/guardrail/detectors/encoding.py` | 118 | reviewed; edge coverage added |
| 22 | `src/mailintel/guardrail/detectors/repetition.py` | 114 | reviewed; edge coverage added |
| 23 | `src/mailintel/mcp_tools/search.py` | 112 | reviewed; runtime ownership fix applied |
| 24 | `src/mailintel/guardrail/scanner_wrapper.py` | 109 | reviewed; no substantive change required |
| 25 | `src/mailintel/events.py` | 107 | reviewed; filtered cursor fix applied |
| 26 | `src/mailintel/actions.py` | 107 | reviewed; idempotent completion fix applied |
| 27 | `src/mailintel/threading_.py` | 104 | reviewed; no substantive change required |
| 28 | `src/mailintel/guardrail/detectors/unicode_attack.py` | 100 | reviewed; no substantive change required |
| 29 | `src/mailintel/enrich/llm.py` | 96 | reviewed; JSON object contract fix applied |
| 30 | `src/mailintel/mcp_tools/agent_loop.py` | 91 | reviewed; runtime ownership fix applied |
| 31 | `src/mailintel/mcp_tools/details.py` | 90 | reviewed; runtime ownership fix applied |
| 32 | `src/mailintel/guardrail/detectors/exfiltration.py` | 89 | reviewed; no substantive change required |
| 33 | `src/mailintel/enrich/prompts.py` | 78 | reviewed; no substantive change required |
| 34 | `src/mailintel/mcp_server.py` | 77 | reviewed; facade/runtime cycle fix applied |
| 35 | `src/mailintel/guardrail/detectors/reply_chain.py` | 73 | reviewed; edge coverage added |
| 36 | `src/mailintel/guardrail/detectors/structural.py` | 72 | reviewed; edge coverage added |
| 37 | `src/mailintel/cli_setup.py` | 72 | reviewed; behavior coverage added |
| 38 | `src/mailintel/ingest_cleanup.py` | 71 | reviewed; no substantive change required |
| 39 | `src/mailintel/mcp_tools/http.py` | 70 | reviewed; unauthenticated bind fix applied |
| 40 | `src/mailintel/db.py` | 70 | reviewed; contact import authority fix applied |
| 41 | `src/mailintel/models.py` | 68 | reviewed; no substantive change required |
| 42 | `src/mailintel/guardrail/db.py` | 61 | reviewed; schema authority fix applied |
| 43 | `src/mailintel/sync_cycle.py` | 48 | reviewed; shared service added |
| 44 | `src/mailintel/guardrail/detectors/prompt_injection.py` | 48 | reviewed; no substantive change required |
| 45 | `src/mailintel/ingest_maildir.py` | 47 | reviewed; no substantive change required |
| 46 | `src/mailintel/guardrail/detectors/size.py` | 46 | reviewed; no substantive change required |
| 47 | `src/mailintel/security.py` | 45 | reviewed; no substantive change required |
| 48 | `src/mailintel/mcp_tools/mail.py` | 45 | reviewed; runtime ownership fix applied |
| 49 | `src/mailintel/store_stats.py` | 40 | reviewed; no substantive change required |
| 50 | `src/mailintel/sync.py` | 33 | reviewed; no substantive change required |
| 51 | `src/mailintel/guardrail/detectors/base.py` | 30 | reviewed; no substantive change required |
| 52 | `src/mailintel/guardrail/detectors/__init__.py` | 24 | reviewed; no substantive change required |
| 53 | `src/mailintel/guardrail/__init__.py` | 23 | reviewed; no substantive change required |
| 54 | `src/mailintel/__init__.py` | 3 | reviewed; no substantive change required |
| 55 | `src/mailintel/mcp_tools/__init__.py` | 1 | reviewed; no substantive change required |
| 56 | `src/mailintel/enrich/__init__.py` | 0 | reviewed; no substantive change required |

The shared prerequisite work was deliberately completed before the strict
largest-to-smallest slices because configuration, schema, audit runtime, and
sync ownership are cross-file contracts.

## Test Python files

All test files were included in the four-lens review. The current behavioral
test set includes the original files plus focused additions:

`tests/__init__.py`, `tests/conftest.py`, `tests/fakes.py`, `tests/test_agent_loop.py`,
`tests/test_audit.py`, `tests/test_cli.py`, `tests/test_cli_setup.py`,
`tests/test_detector_edges.py`, `tests/test_embedders.py`, `tests/test_enrich.py`,
`tests/test_events.py`, `tests/test_guardrail.py`, `tests/test_http_transport.py`,
`tests/test_ingest.py`, `tests/test_db.py`, `tests/test_knowledge_edges.py`, `tests/test_mcp.py`,
`tests/test_mcp_surface.py`, `tests/test_parser_edges.py`,
`tests/test_provider_adapters.py`, `tests/test_quality_boundaries.py`,
`tests/test_security.py`, `tests/test_sender_edges.py`, `tests/test_search.py`,
`tests/test_sync.py`, and `tests/test_threading.py`.
