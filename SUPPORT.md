# Support

## Documentation First

Most questions are answered in the tracked documentation:

- [README.md](README.md) — setup, CLI, MCP tools, and security guardrails.
- [config.example.toml](config.example.toml) — every configuration option.
- [docs/mbsync-setup.md](docs/mbsync-setup.md) — Maildir sync with mbsync.
- [docs/agent-guide.md](docs/agent-guide.md) — the MCP-agent operating loop.
- [CONTRIBUTING.md](CONTRIBUTING.md) — development setup and PR expectations.

## When To Open An Issue

Open an issue for reproducible bugs, unclear documentation, or well-scoped
improvement proposals. Use the provided issue templates. For questions that
are neither bugs nor proposals, start a discussion instead if discussions are
enabled on the repository.

Do not open public issues for suspected security vulnerabilities — follow
[SECURITY.md](SECURITY.md) instead.

## What To Include

- mailintel version or commit, OS, Python version, and `uv` version.
- The relevant config sections with secrets and personal data redacted.
- Actual behavior versus expected behavior.
- Logs or command output — never include raw email content, credentials, or
  API keys.
