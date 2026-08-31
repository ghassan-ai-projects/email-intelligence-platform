# Production Python Inventory

Generated from the branch baseline at commit `75d2247` on 2026-08-31. Test
files are intentionally excluded.

| Status | Lines | File |
|---|---:|---|
| Complete | 208 | `src/mailintel/guardrail/scanner.py` |
| Pending | 878 | `src/mailintel/mcp_server.py` |
| Pending | 442 | `src/mailintel/ingest.py` |
| Pending | 334 | `src/mailintel/db.py` |
| Pending | 296 | `src/mailintel/cli.py` |
| Pending | 287 | `src/mailintel/enrich/pipeline.py` |
| Pending | 251 | `src/mailintel/search.py` |
| Pending | 248 | `src/mailintel/config.py` |
| Pending | 221 | `src/mailintel/guardrail/threat_profiles.py` |
| Pending | 213 | `src/mailintel/knowledge.py` |
| Pending | 203 | `src/mailintel/guardrail/contacts.py` |
| Pending | 199 | `src/mailintel/drafts.py` |
| Pending | 192 | `src/mailintel/sender.py` |
| Pending | 152 | `src/mailintel/enrich/embeddings.py` |
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

The line count is a prioritization signal, not a permission to split without a
cohesive responsibility boundary.
