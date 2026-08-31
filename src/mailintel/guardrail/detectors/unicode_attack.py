"""Unicode anomaly detector."""

from __future__ import annotations

import re

from ..threat_profiles import BIDI_OVERRIDE_CHARS, HOMOGLYPH_MAP, ZERO_WIDTH_CHARS
from .base import BaseDetector, DetectorResult


class UnicodeAttackDetector(BaseDetector):
    """Detect invisible characters, confusables, bidi controls, and emoji density."""

    EMOJI_RANGE = re.compile(
        "[\U0001f600-\U0001f64f"
        "\U0001f300-\U0001f5ff"
        "\U0001f680-\U0001f6ff"
        "\U0001f1e0-\U0001f1ff"
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "\U0001f900-\U0001f9ff"
        "\U0001fa00-\U0001fa6f"
        "\U0001fa70-\U0001faff"
        "\U00002600-\U000026ff"
        "\U0000fe00-\U0000fe0f]"
    )

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._zw_score_per_char = config.get("zw_score_per_char", 5)
        self._bidi_score_per_char = config.get("bidi_score_per_char", 10)
        self._homoglyph_score = config.get("homoglyph_score", 10)
        self._emoji_threshold = config.get("emoji_threshold", 0.20)
        self._emoji_score = config.get("emoji_score", 15)

    @property
    def name(self) -> str:
        return "unicode_attack"

    def scan(
        self, _sender: str, subject: str, body: str, _headers: dict[str, str]
    ) -> DetectorResult:
        text = f"{subject}\n{body}"
        score = 0
        details: list[str] = []
        score += self._score_invisible_characters(
            text, ZERO_WIDTH_CHARS, self._zw_score_per_char, "Zero-width characters", details
        )
        score += self._score_invisible_characters(
            text,
            BIDI_OVERRIDE_CHARS,
            self._bidi_score_per_char,
            "Bidirectional override characters",
            details,
        )
        score += self._score_homoglyphs(text, details)
        score += self._score_emoji_density(text, details)
        return DetectorResult(risk_score=min(score, 100), triggered=score > 0, details=details)

    @staticmethod
    def _score_invisible_characters(
        text: str,
        characters: dict[str, str],
        points_per_character: int,
        label: str,
        details: list[str],
    ) -> int:
        found = {name: text.count(char) for char, name in characters.items() if text.count(char)}
        if not found:
            return 0
        total = sum(found.values())
        description = ", ".join(f"{name}={count}" for name, count in found.items())
        details.append(f"{label} detected ({total} total): {description}")
        return total * points_per_character

    def _score_homoglyphs(self, text: str, details: list[str]) -> int:
        found = {
            char: (replacement, text.count(char))
            for char, replacement in HOMOGLYPH_MAP.items()
            if text.count(char)
        }
        if not found:
            return 0
        preview = ", ".join(
            f"'{char}'->'{replacement}' (x{count})" for char, (replacement, count) in found.items()
        )
        details.append(f"Homoglyph substitutions detected: {preview}")
        return self._homoglyph_score

    def _score_emoji_density(self, text: str, details: list[str]) -> int:
        emoji_count = len(self.EMOJI_RANGE.findall(text))
        printable_length = max(1, len([char for char in text if not char.isspace()]))
        emoji_ratio = emoji_count / printable_length
        if emoji_ratio <= self._emoji_threshold:
            return 0
        details.append(
            f"High emoji density ({emoji_count}/{printable_length} = "
            f"{emoji_ratio:.0%}) — potential steganography carrier"
        )
        return self._emoji_score
