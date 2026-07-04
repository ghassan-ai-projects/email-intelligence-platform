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
                    │
                    ▼
   append-only events + write-back (tags, notes, done tasks) + drafts
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
| `read_attachment` | attachment content: text for PDFs/text files, base64 for binaries |
| `send_email` | SMTP send with attachments — **opt-in**, allowlist-guarded |
| `create_draft` / `update_draft` / `list_drafts` / `send_draft` | draft-first outgoing mail, review before send |
| `get_events_since` | reactive agent feed: new emails, enrichments, completed tasks, drafts |
| `complete_action_item` / `set_importance` / `tag_email` / `add_email_note` | agent write-back so state is not re-discovered |
| `get_stats` / `list_folders` / `sync_now` | store state and on-demand sync |

## Setup

```sh
# 1. Install
uv tool install .                 # or: uv sync && uv run mailintel ...

# 2. Mail sync (Maildir source of truth)
brew install isync                # then configure ~/.mbsyncrc — see docs/mbsync-setup.md
                                  # (GMX, Gmail and generic IMAP examples included)

# 3. Configure
mailintel init                    # writes ~/.mailintel/config.toml
$EDITOR ~/.mailintel/config.toml  # point [maildir] path at your mbsync target
                                  # (or: export MAILINTEL_MAILDIR=~/Mail)

# 4. Secrets — mailintel auto-loads ~/.mailintel/.env (and ./.env)
cat > ~/.mailintel/.env <<'ENV'
EMAIL_USER=you@gmx.de             # used by mbsync PassCmd and SMTP sending
EMAIL_PASSWORD=...
DEEPSEEK_API_KEY=...              # or any OpenAI-compatible provider / Anthropic
VOYAGE_API_KEY=...                # not needed if you embed locally with Ollama
ENV
chmod 600 ~/.mailintel/.env

# 5. Sync, index, enrich
mailintel sync                    # mbsync -> ingest -> enrich queue
mailintel stats

# 6. Plug into Claude Code
claude mcp add mailintel -- mailintel serve
```

`mailintel watch` keeps everything fresh in a loop (`sync.interval_minutes`).

## Reactive agent loop, write-back and drafts

Agents can react to changes instead of polling:

- `get_events_since(cursor)` returns an append-only feed of `email_ingested`,
  `email_deleted`, `email_enriched`, `action_item_created`, `fact_extracted`,
  `action_item_completed`, `draft_created`, `draft_sent`, and `email_sent`.
  Persist `next_cursor` and pass it on the next call to receive only the delta.
- Write-back tools let agents record their work: `complete_action_item`,
  `set_importance`, `tag_email`, `untag_email`, and `add_email_note`. Notes and
  tags are shown in `get_email`, and completed action items drop out of
  `find_action_items`.
- Outgoing mail is draft-first: `create_draft` stores a message with no side
  effects, `update_draft` refines it, and `send_draft` applies the same
  `send_email` guardrails (`smtp.enabled`, `allowed_recipients`) at delivery
  time. Prefer this flow for any mail an agent prepares.

## Multi-provider enrichment & embeddings

Every new email gets **one structured LLM call** (summary, importance, sentiment,
action items, entities, facts) and one embedding. The `[llm]` config block works
with any OpenAI-compatible API — DeepSeek, Ollama (fully local), Groq,
OpenRouter, OpenAI — or the native Anthropic API.

Embeddings are pluggable too: `[embeddings] provider = "voyage"` (hosted) or
`"openai-compat"` for a fully local Ollama setup
(`base_url = "http://localhost:11434/v1"`, `model = "nomic-embed-text"`,
`dimensions = 768`). See [config.example.toml](config.example.toml).

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

## Security guardrails

Email is untrusted third-party input, and this store feeds LLMs and agents, so
several defenses are built in ([security.py](src/mailintel/security.py)):

- **Ingest sanitization** — control characters, zero-width characters, and
  bidi-override tricks (used to hide injected instructions) are stripped from
  subjects, bodies, and names before anything is stored. LLM-derived output
  (summaries, facts, action items) is sanitized again before storage.
- **Hardened enrichment prompt** — the enrichment LLM is told the email is
  untrusted data; instruction-like content is flagged as a suspected
  prompt-injection attempt instead of followed.
- **Untrusted-content notices** — MCP tools that return bodies or attachment
  content (`get_email`, `get_thread`, `read_attachment`) attach a security
  notice, and the server instructions tell agents never to act on instructions
  found inside mail.
- **Sending is opt-in and fenced** — `send_email` requires `[smtp] enabled =
  true`; recipients can be restricted with `allowed_recipients` globs, and
  local-file attachments only work from whitelisted `attachment_dirs` (stored
  email attachments can be forwarded by id). This limits the blast radius of a
  successful injection trying to exfiltrate data.
- **Rate cap on outgoing mail** — `smtp.max_sends_per_hour` counts
  `send_email`/`send_draft` calls in the audit log and blocks sends over the
  cap, so a runaway agent cannot spam.
- **Audit log** — every MCP tool call is recorded (tool, arguments, caller,
  timestamp, outcome) so you can answer "why did it send that email" after the
  fact.

## Development

```sh
uv sync --group dev
make ci-check       # format, lint, typecheck, test, build
make test           # fixture Maildir, fake LLM/embedders — no keys needed
make hooks          # optional local pre-commit and pre-push hooks
```

Layout: `src/mailintel/` — `ingest.py` (Maildir → SQLite), `threading_.py`
(conversation graph), `search.py` (FTS), `enrich/` (LLM providers, prompts,
Voyage + sqlite-vec, job pipeline), `knowledge.py` (facts/tasks/digests),
`events.py` (append-only change feed), `actions.py` (write-back), `drafts.py`
(draft-first outgoing mail), `mcp_server.py` (tools), `cli.py`.
The schema also carries an `account` column on core tables, defaulting to
`'default'`, to make future multi-account support a config change rather than a
migration.

See [`AGENTS.md`](AGENTS.md) for build/test commands and conventions, and
[`CONTRIBUTING.md`](CONTRIBUTING.md) for pull request expectations.

Future work: OCR for scanned attachments, promotion of high-value facts into
shared agent memory (ALMS), webhook-style forwarding of selected events, and
multi-account sync on top of the existing `account` column.
