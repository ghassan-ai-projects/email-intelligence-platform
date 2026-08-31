# Production Python Inventory

Generated from the branch baseline at commit `75d2247` on 2026-08-31. Test
files are intentionally excluded.

| Status | Lines | File |
|---|---:|---|
| Complete | 208 | `src/mailintel/guardrail/scanner.py` |
| Complete | 183 | `src/mailintel/mcp_server.py` |
| Complete | 202 | `src/mailintel/ingest.py` |
| Complete | 115 | `src/mailintel/db.py` |
| Complete | 247 | `src/mailintel/cli.py` |
| Complete | 197 | `src/mailintel/enrich/pipeline.py` |
| Complete | 223 | `src/mailintel/search.py` |
| Assessed (no change) | 248 | `src/mailintel/config.py` |
| Assessed (no change) | 221 | `src/mailintel/guardrail/threat_profiles.py` |
| Assessed (no change) | 213 | `src/mailintel/knowledge.py` |
| Assessed (no change) | 203 | `src/mailintel/guardrail/contacts.py` |
| Assessed (no change) | 199 | `src/mailintel/drafts.py` |
| Assessed (no change) | 192 | `src/mailintel/sender.py` |
| Assessed (no change) | 152 | `src/mailintel/enrich/embeddings.py` |
| Pending | 114 | `src/mailintel/enrich/attachments.py` |
| Pending | 109 | `src/mailintel/guardrail/scanner_wrapper.py` |
| Pending | 107 | `src/mailintel/actions.py` |
| Pending | 104 | `src/mailintel/threading_.py` |
| Pending | 104 | `src/mailintel/events.py` |
| Pending | 93 | `src/mailintel/enrich/llm.py` |
| Pending | 78 | `src/mailintel/enrich/prompts.py` |
| Pending | 69 | `src/mailintel/guardrail/db.py` |
| Pending | 68 | `src/mailintel/models.py` |
| Pending | 45 | `src/mailintel/security.py` |
| Pending | 33 | `src/mailintel/sync.py` |
| Pending | 23 | `src/mailintel/guardrail/__init__.py` |
| Pending | 3 | `src/mailintel/__init__.py` |
| Pending | 0 | `src/mailintel/enrich/__init__.py` |

The scanner slice also introduced these focused production modules; they are
covered by the scanner record and are all below the 250-line limit:

| Status | Lines | File |
|---|---:|---|
| Complete | 118 | `src/mailintel/guardrail/detectors/encoding.py` |
| Complete | 114 | `src/mailintel/guardrail/detectors/repetition.py` |
| Complete | 100 | `src/mailintel/guardrail/detectors/unicode_attack.py` |
| Complete | 89 | `src/mailintel/guardrail/detectors/exfiltration.py` |
| Complete | 73 | `src/mailintel/guardrail/detectors/reply_chain.py` |
| Complete | 72 | `src/mailintel/guardrail/detectors/structural.py` |
| Complete | 48 | `src/mailintel/guardrail/detectors/prompt_injection.py` |
| Complete | 46 | `src/mailintel/guardrail/detectors/size.py` |
| Complete | 30 | `src/mailintel/guardrail/detectors/base.py` |
| Complete | 24 | `src/mailintel/guardrail/detectors/__init__.py` |

The MCP server slice also introduced these focused production modules; they
are covered by the MCP server record and are all below the 250-line limit:

| Status | Lines | File |
|---|---:|---|
| Complete | 140 | `src/mailintel/mcp_tools/knowledge.py` |
| Complete | 131 | `src/mailintel/mcp_tools/drafts.py` |
| Complete | 116 | `src/mailintel/mcp_tools/details.py` |
| Complete | 112 | `src/mailintel/mcp_tools/search.py` |
| Complete | 91 | `src/mailintel/mcp_tools/agent_loop.py` |
| Complete | 68 | `src/mailintel/mcp_tools/http.py` |
| Complete | 45 | `src/mailintel/mcp_tools/mail.py` |
| Complete | 1 | `src/mailintel/mcp_tools/__init__.py` |

The ingestion slice also introduced these focused production modules; they are
covered by the ingestion record and are all below the 250-line limit:

| Status | Lines | File |
|---|---:|---|
| Complete | 146 | `src/mailintel/ingest_parser.py` |
| Complete | 118 | `src/mailintel/ingest_storage.py` |
| Complete | 71 | `src/mailintel/ingest_cleanup.py` |
| Complete | 47 | `src/mailintel/ingest_maildir.py` |

The database slice also introduced this focused production module:

| Status | Lines | File |
|---|---:|---|
| Complete | 222 | `src/mailintel/db_schema.py` |

The CLI slice also introduced this focused production module:

| Status | Lines | File |
|---|---:|---|
| Complete | 72 | `src/mailintel/cli_setup.py` |

The enrichment pipeline slice also introduced this focused production module:

| Status | Lines | File |
|---|---:|---|
| Complete | 115 | `src/mailintel/enrich/enrichment_storage.py` |

The search slice also introduced this focused production module:

| Status | Lines | File |
|---|---:|---|
| Complete | 40 | `src/mailintel/store_stats.py` |

The line count is a prioritization signal, not a permission to split without a
cohesive responsibility boundary. `Assessed (no change)` records a reviewed
file that already satisfies the bar without a justified behavior-preserving
extraction.
