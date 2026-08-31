"""Prompt-injection phrase detector."""

from __future__ import annotations

from re import Pattern
from typing import ClassVar

from ..threat_profiles import PROMPT_INJECTION, compile_patterns
from .base import BaseDetector, DetectorResult


class PromptInjectionDetector(BaseDetector):
    """Detect known prompt-injection phrases and role-play hijacks."""

    TIER_SCORES: ClassVar[dict[str, int]] = {"tier1": 40, "tier2": 20, "tier3": 10}
    MAX_SCORE: ClassVar[int] = 100

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._patterns: dict[str, list[Pattern]] = compile_patterns(PROMPT_INJECTION)
        self._enabled_tiers = {
            tier for tier in ("tier1", "tier2", "tier3") if config.get(f"{tier}_enabled", True)
        }

    @property
    def name(self) -> str:
        return "prompt_injection"

    def scan(
        self, _sender: str, subject: str, body: str, _headers: dict[str, str]
    ) -> DetectorResult:
        text = f"{subject}\n{body}".lower()
        score = 0
        details: list[str] = []

        for tier, patterns in self._patterns.items():
            if tier not in self._enabled_tiers:
                continue
            for pattern in patterns:
                if pattern.search(text):
                    points = self.TIER_SCORES[tier]
                    score += points
                    details.append(
                        f"Prompt injection [{tier}] (+{points}): matched /{pattern.pattern}/"
                    )

        score = min(score, self.MAX_SCORE)
        return DetectorResult(risk_score=score, triggered=score > 0, details=details)
