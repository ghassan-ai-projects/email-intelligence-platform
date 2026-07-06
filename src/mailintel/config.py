"""Configuration loading: ~/.mailintel/config.toml with env-var overrides for secrets."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

DEFAULT_CONFIG_DIR = Path("~/.mailintel").expanduser()
CONFIG_ENV_VAR = "MAILINTEL_CONFIG"
MAILDIR_ENV_VAR = "MAILINTEL_MAILDIR"


def load_env_files(extra: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env files into os.environ (existing vars win).

    Looked up in ./.env and ~/.mailintel/.env — mail credentials and API keys
    live there instead of the config file. Child processes (mbsync) inherit them.
    """
    candidates = [Path.cwd() / ".env", DEFAULT_CONFIG_DIR / ".env"]
    if extra:
        candidates.insert(0, extra)
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


def _expand(p: Path | str) -> Path:
    return Path(p).expanduser()


class StorageConfig(BaseModel):
    db_path: Path = Field(default_factory=lambda: DEFAULT_CONFIG_DIR / "mail.db")

    @field_validator("db_path", mode="after")
    @classmethod
    def _expand_path(cls, v: Path) -> Path:
        return _expand(v)


class MaildirConfig(BaseModel):
    path: Path = Field(default_factory=lambda: Path("~/Mail").expanduser())
    # Folder names (any path segment, case-insensitive) treated as sent mail.
    # German names cover GMX / web.de accounts.
    sent_folders: list[str] = [
        "Sent",
        "Sent Mail",
        "Sent Messages",
        "Sent Items",
        "Gesendet",
    ]
    # Folders skipped entirely during ingest (matched per path segment, case-insensitive).
    exclude_folders: list[str] = [
        "Trash",
        "Spam",
        "Junk",
        "Drafts",
        "Papierkorb",
        "Entwürfe",
        "Gelöscht",
    ]

    @field_validator("path", mode="after")
    @classmethod
    def _expand_path(cls, v: Path) -> Path:
        return _expand(v)


class SyncConfig(BaseModel):
    command: str = "mbsync -a"
    interval_minutes: int = 5


class LLMConfig(BaseModel):
    provider: str = "openai-compat"  # "openai-compat" | "anthropic"
    base_url: str | None = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"
    temperature: float = 0.1
    max_tokens: int = 2000
    # Truncation budgets keep enrichment cheap on huge emails.
    max_body_chars: int = 8000
    max_attachment_chars: int = 2000

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


class EmbeddingsConfig(BaseModel):
    provider: str = "voyage"  # "voyage" | "openai-compat" (Ollama, LM Studio, OpenAI, ...)
    base_url: str | None = None  # e.g. "http://localhost:11434/v1" for Ollama
    model: str = "voyage-3.5-lite"
    api_key_env: str = "VOYAGE_API_KEY"
    dimensions: int = 1024
    max_chars: int = 6000
    batch_size: int = 64

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


class SmtpConfig(BaseModel):
    """Outgoing mail. Disabled by default: sending is opt-in for safety."""

    enabled: bool = False
    host: str = ""  # e.g. "mail.gmx.net"
    port: int = 587
    starttls: bool = True
    username_env: str = "EMAIL_USER"
    password_env: str = "EMAIL_PASSWORD"
    from_addr: str = ""  # defaults to the username
    # Glob patterns; if non-empty, every recipient must match one (guardrail
    # against prompt-injected exfiltration). Example: ["*@mycompany.com"]
    allowed_recipients: list[str] = []
    # Local directories that may be used as attachment sources when sending.
    # Empty = only stored email attachments can be forwarded, no local files.
    attachment_dirs: list[Path] = []
    # Global cap on outgoing mail. Counts send_email and send_draft calls in the
    # last hour from the audit log. 0 = unlimited.
    max_sends_per_hour: int = 10

    @field_validator("attachment_dirs", mode="after")
    @classmethod
    def _expand_dirs(cls, v: list[Path]) -> list[Path]:
        return [_expand(p) for p in v]

    @property
    def username(self) -> str | None:
        return os.environ.get(self.username_env)

    @property
    def password(self) -> str | None:
        return os.environ.get(self.password_env)


class GuardrailConfig(BaseModel):
    """Email security guardrail scanner configuration."""

    block_threshold: int = 60
    scan_on_ingest: bool = True
    trusted_domains: list[str] = ["gmx.de", "gmx.net", "github.com", "thunderbird.net"]
    contacts_path: Path | None = Field(
        default_factory=lambda: DEFAULT_CONFIG_DIR / "contacts.json"
    )
    # Per-detector overrides are passed as-is to EmailScanner._load_config.
    prompt_injection: dict | None = None
    encoding_anomaly: dict | None = None
    size_guard: dict | None = None
    unicode_attack: dict | None = None
    structural_anomaly: dict | None = None
    reply_chain: dict | None = None
    repetition: dict | None = None
    exfiltration_guard: dict | None = None

    @field_validator("contacts_path", mode="after")
    @classmethod
    def _expand_path(cls, v: Path | None) -> Path | None:
        return _expand(v) if v else None

    def scanner_config(self) -> dict:
        """Build a flat config dict for the EmailScanner constructor."""
        cfg: dict = {"block_threshold": self.block_threshold}
        if self.trusted_domains:
            cfg["exfiltration_guard"] = {
                **(self.exfiltration_guard or {}),
                "trusted_domains": self.trusted_domains,
            }
        for key in (
            "prompt_injection",
            "encoding_anomaly",
            "size_guard",
            "unicode_attack",
            "structural_anomaly",
            "reply_chain",
            "repetition",
        ):
            val = getattr(self, key, None)
            if val is not None:
                cfg[key] = val
        return cfg


class EnrichConfig(BaseModel):
    max_attempts: int = 3
    stages: list[str] = ["attachments", "enrich", "embed"]


class Config(BaseModel):
    storage: StorageConfig = Field(default_factory=StorageConfig)
    maildir: MaildirConfig = Field(default_factory=MaildirConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    enrich: EnrichConfig = Field(default_factory=EnrichConfig)
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    guardrail: GuardrailConfig = Field(default_factory=GuardrailConfig)


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_CONFIG_DIR / "config.toml"


def load_config(path: Path | None = None) -> Config:
    load_env_files()
    path = path or config_path()
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)
        cfg = Config.model_validate(data)
    else:
        cfg = Config()
    maildir_override = os.environ.get(MAILDIR_ENV_VAR)
    if maildir_override:
        cfg.maildir.path = Path(maildir_override).expanduser()
    return cfg
