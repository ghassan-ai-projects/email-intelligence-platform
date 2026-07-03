# Email Intelligence Platform (mailintel)

Local-first email intelligence: your mail becomes a continuously enriched
**knowledge base** that AI agents query through **MCP** — not a pile of messages
behind a raw IMAP API.

```
IMAP ──mbsync──▶ Maildir (immutable source of truth)
                    │  ingest: parse, thread, full-text index
                    ▼
        SQLite: metadata + FTS5 + sqlite-vec + knowledge tables
                    │  enrichment: LLM summaries, action items,
                    │  entities, facts + Voyage embeddings
                    ▼
          MCP server (stdio) ──▶ Claude Code / any MCP agent
```

Everything lives in one SQLite file. No servers, no Docker, no UI.

## What agents get

Instead of `ReadEmail` / `SearchEmail`, the MCP server exposes knowledge-level tools:

| Tool | Answers |
|---|---|
| `search_emails` | full-text + filters (sender, folder, dates, attachments, unread) |
| `semantic_search` | "complaints about latency" — meaning, not keywords |
| `related_emails` | emails similar to a given one (vector distance) |
| `get_email` / `get_thread` / `search_threads` | full detail, whole conversations |
| `find_action_items` | open tasks extracted from mail, with owner and due date |
| `search_facts` / `find_decisions` | structured facts: deadlines, decisions, changes, commitments |
| `summarize_sender` | profile of a correspondent: volume, topics, open items |
| `find_waiting_replies` | sent mail nobody answered |
| `daily_summary` | digest of a day: important mail, new tasks, key facts |
| `get_stats` / `list_folders` / `sync_now` | store state and on-demand sync |

## Setup

```sh
# 1. Install
uv tool install .                 # or: uv sync && uv run mailintel ...

# 2. Mail sync (Maildir source of truth)
brew install isync                # then configure ~/.mbsyncrc — see docs/mbsync-setup.md

# 3. Configure
mailintel init                    # writes ~/.mailintel/config.toml
$EDITOR ~/.mailintel/config.toml  # point [maildir] path at your mbsync target

# 4. API keys (enrichment + embeddings)
export DEEPSEEK_API_KEY=...       # or any OpenAI-compatible provider / Anthropic
export VOYAGE_API_KEY=...         # semantic search embeddings

# 5. Sync, index, enrich
mailintel sync                    # mbsync -> ingest -> enrich queue
mailintel stats

# 6. Plug into Claude Code
claude mcp add mailintel -- mailintel serve
```

`mailintel watch` keeps everything fresh in a loop (`sync.interval_minutes`).

## Multi-provider enrichment

Every new email gets **one structured LLM call** (summary, importance, sentiment,
action items, entities, facts) and one embedding. The `[llm]` config block works
with any OpenAI-compatible API — DeepSeek, Ollama (fully local), Groq,
OpenRouter, OpenAI — or the native Anthropic API. See
[config.example.toml](config.example.toml).

The pipeline is a resumable queue (`pipeline_jobs`): interrupt it any time,
re-run `mailintel enrich --limit 500` to work through backlogs, failures retry
with a cap. Emails whose enrichment terminally fails still get body-only
embeddings.

## CLI

```
mailintel init      scaffold config + setup guidance
mailintel sync      run mbsync, ingest changes, process enrichment queue
mailintel ingest    index the Maildir only
mailintel enrich    process the enrichment queue (--limit, --stage)
mailintel serve     MCP server on stdio
mailintel watch     continuous sync/ingest/enrich loop
mailintel search    quick FTS (--semantic for vector search)
mailintel stats     store statistics
```

## Development

```sh
uv sync
uv run pytest       # fixture Maildir, fake LLM/embedders — no keys needed
```

Layout: `src/mailintel/` — `ingest.py` (Maildir → SQLite), `threading_.py`
(conversation graph), `search.py` (FTS), `enrich/` (LLM providers, prompts,
Voyage + sqlite-vec, job pipeline), `knowledge.py` (facts/tasks/digests),
`mcp_server.py` (tools), `cli.py`.

Future work: OCR for scanned attachments, event webhooks for new-knowledge
notifications, promotion of high-value facts into shared agent memory (ALMS).
