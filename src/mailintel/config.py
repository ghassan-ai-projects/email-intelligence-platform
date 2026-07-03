"""Configuration loading: ~/.mailintel/config.toml with env-var overrides for secrets."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

DEFAULT_CONFIG_DIR = Path("~/.mailintel").expanduser()
CONFIG_ENV_VAR = "MAILINTEL_CONFIG"


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
    sent_folders: list[str] = ["Sent", "Sent Mail", "Sent Messages", "Sent Items"]
    # Folders skipped entirely during ingest (matched per path segment, case-insensitive).
    exclude_folders: list[str] = ["Trash", "Spam", "Junk", "Drafts"]

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
    model: str = "voyage-3.5-lite"
    api_key_env: str = "VOYAGE_API_KEY"
    dimensions: int = 1024
    max_chars: int = 6000
    batch_size: int = 64

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


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


def config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_CONFIG_DIR / "config.toml"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return Config.model_validate(data)
    return Config()
