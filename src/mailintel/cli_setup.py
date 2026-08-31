"""Configuration scaffolding for the mailintel CLI."""

from __future__ import annotations

from pathlib import Path

import typer

CONFIG_TEMPLATE = """\
# mailintel configuration. Secrets stay in ~/.mailintel/.env (auto-loaded):
#   EMAIL_USER / EMAIL_PASSWORD, DEEPSEEK_API_KEY, VOYAGE_API_KEY, ...
# See config.example.toml in the repo for every option (Ollama embeddings,
# SMTP sending with guardrails, GMX folder names, ...).

[storage]
db_path = "{db_path}"

[maildir]
path = "~/Mail"                     # or set MAILINTEL_MAILDIR
sent_folders = ["Sent", "Sent Mail", "Sent Messages", "Sent Items", "Gesendet"]
exclude_folders = ["Trash", "Spam", "Junk", "Drafts", "Papierkorb", "Entwürfe"]

[sync]
command = "mbsync -a"
interval_minutes = 5

[llm]
provider = "openai-compat"          # or "anthropic"
base_url = "https://api.deepseek.com"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"

[embeddings]
provider = "voyage"                 # or "openai-compat" (e.g. local Ollama)
model = "voyage-3.5-lite"
api_key_env = "VOYAGE_API_KEY"
dimensions = 1024

[smtp]
enabled = false                     # opt-in: allows the send_email MCP tool
host = ""
allowed_recipients = []             # guardrail, e.g. ["*@mycompany.com"]
"""


def initialize_config(path: Path, default_config_dir: Path, template: str) -> None:
    """Create the default config file and print first-run guidance."""
    _write_config_if_missing(path, default_config_dir, template)
    _print_setup_guidance()


def _write_config_if_missing(path: Path, default_config_dir: Path, template: str) -> None:
    if path.exists():
        typer.echo(f"Config already exists: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.format(db_path=str(default_config_dir / "mail.db")))
    typer.echo(f"Wrote {path}")


def _print_setup_guidance() -> None:
    typer.echo(
        "\nNext steps:\n"
        "  1. Install mbsync:        brew install isync\n"
        "  2. Configure ~/.mbsyncrc  (see docs/mbsync-setup.md in the repo)\n"
        "  3. Edit the [maildir] path in the config to your mbsync target\n"
        "     (or set the MAILINTEL_MAILDIR environment variable)\n"
        "  4. Put secrets in ~/.mailintel/.env — EMAIL_USER, EMAIL_PASSWORD,\n"
        "     DEEPSEEK_API_KEY (or your provider), VOYAGE_API_KEY\n"
        "  5. Run:                   mailintel sync && mailintel enrich\n"
        "  6. Register MCP server:   claude mcp add mailintel -- mailintel serve"
    )
