"""Pydantic models for structured LLM enrichment output."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

FACT_CATEGORIES = {"deadline", "decision", "change", "commitment", "info"}
SENTIMENTS = {"positive", "neutral", "negative"}


class ActionItem(BaseModel):
    description: str
    owner: str | None = None
    due_date: str | None = None  # ISO date if known


class Fact(BaseModel):
    fact: str
    category: str = "info"
    due_date: str | None = None
    confidence: float = 0.8

    @field_validator("category", mode="before")
    @classmethod
    def _norm_category(cls, v: object) -> str:
        s = str(v or "info").lower().strip()
        return s if s in FACT_CATEGORIES else "info"

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: object) -> float:
        try:
            return min(1.0, max(0.0, float(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.8


class Entities(BaseModel):
    people: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class EnrichmentResult(BaseModel):
    language: str = "en"
    summary: str = ""
    importance: int = 3
    sentiment: str = "neutral"
    action_items: list[ActionItem] = Field(default_factory=list)
    entities: Entities = Field(default_factory=Entities)
    facts: list[Fact] = Field(default_factory=list)

    @field_validator("importance", mode="before")
    @classmethod
    def _clamp_importance(cls, v: object) -> int:
        if not isinstance(v, int | float | str | bytes | bytearray):
            return 3
        try:
            return min(5, max(1, int(v)))
        except (TypeError, ValueError):
            return 3

    @field_validator("sentiment", mode="before")
    @classmethod
    def _norm_sentiment(cls, v: object) -> str:
        s = str(v or "neutral").lower().strip()
        return s if s in SENTIMENTS else "neutral"
