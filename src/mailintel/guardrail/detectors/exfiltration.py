"""Sensitive-data exfiltration detector."""

from __future__ import annotations

import re
from re import Pattern
from typing import ClassVar

from .base import BaseDetector, DetectorResult


class ExfiltrationGuardDetector(BaseDetector):
    """Detect requests that seek secrets, credentials, or personal data."""

    TIER_SCORES: ClassVar[dict[str, int]] = {"tier1": 50, "tier2": 30, "tier3": 15}
    MAX_SCORE: ClassVar[int] = 100
    EXFIL_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "tier1": [
            r"send\s+me\s+(your\s+)?(key|password|secret|credential|token|api[\s-]*key)",
            r"give\s+me\s+(your\s+)?(key|password|secret|credential|token|access)",
            r"what(\s+is)?\s+(your|the)\s+(key|password|secret|credential|token|api[\s-]*key)",
            r"verify\s+(your|the)\s+(identity|account)\s+(by|with|using)",
            r"provide\s+(your|the)\s+(key|password|secret|credential|token|api[\s-]*key)",
            r"hand\s+over\s+(your|the)\s+",
            r"i\s+need\s+(your|the)\s+(key|password|secret|credential|token)",
            r"reveal\s+(your|the)",
        ],
        "tier2": [
            r"what(\s+is)?\s+(your|my|the)\s+(username|login|password|email|account)",
            r"send\s+me\s+(your|the)\s+(details|info|credentials|data)",
            r"what\s+(account|email|address)\s+do\s+you\s+(use|have)",
            r"can\s+you\s+(tell|send|give)\s+me\s+(your|the)\s+(email|address|phone|number)",
            r"forward\s+(this|the)\s+(to|for)\s+",
            r"share\s+(your|the)\s+(credentials|password|key|token|access)",
        ],
        "tier3": [
            r"where\s+(can|do)\s+i\s+(find|get|access)",
            r"how\s+do\s+i\s+(login|access|connect)",
            r"tell\s+me\s+(about|more|your)",
        ],
    }

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._patterns: dict[str, list[Pattern]] = {
            tier: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for tier, patterns in self.EXFIL_PATTERNS.items()
            if config.get(f"{tier}_enabled", True)
        }
        self._enabled_tiers = set(self._patterns)
        self._trusted_domains = config.get(
            "trusted_domains", ["gmx.de", "gmx.net", "github.com", "thunderbird.net"]
        )

    @property
    def name(self) -> str:
        return "exfiltration_guard"

    def scan(
        self, sender: str, subject: str, body: str, _headers: dict[str, str]
    ) -> DetectorResult:
        text = f"{subject}\n{body}\n{subject}".lower()
        domain_penalty = self._trusted_domain_penalty(sender)
        score = 0
        details: list[str] = []
        for tier, patterns in self._patterns.items():
            if tier not in self._enabled_tiers:
                continue
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    points = max(0, self.TIER_SCORES[tier] - domain_penalty)
                    score += points
                    details.append(
                        f"Exfiltration attempt [{tier}] (+{points}): matched '{match.group()}'"
                    )
                    break
        score = min(score, self.MAX_SCORE)
        return DetectorResult(risk_score=score, triggered=score > 0, details=details)

    def _trusted_domain_penalty(self, sender: str) -> int:
        sender_lower = sender.lower()
        sender_domain = sender_lower.rsplit("@", 1)[-1] if "@" in sender_lower else ""
        if any(
            sender_domain == domain or sender_domain.endswith("." + domain)
            for domain in self._trusted_domains
        ):
            return 15
        return 0
