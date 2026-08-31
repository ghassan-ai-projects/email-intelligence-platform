"""Email-size guard detector."""

from __future__ import annotations

from .base import BaseDetector, DetectorResult


class SizeGuardDetector(BaseDetector):
    """Detect oversized email bodies and report the configured truncation plan."""

    DEFAULT_MAX_BYTES = 1_048_576
    DEFAULT_MAX_CHARS = 1_000_000
    DEFAULT_TRUNCATION_LENGTH = 100_000

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.max_bytes = config.get("max_bytes", self.DEFAULT_MAX_BYTES)
        self.max_chars = config.get("max_chars", self.DEFAULT_MAX_CHARS)
        self.truncation_length = config.get("truncation_length", self.DEFAULT_TRUNCATION_LENGTH)
        self.truncated = False

    @property
    def name(self) -> str:
        return "size_guard"

    def scan(
        self, _sender: str, _subject: str, body: str, _headers: dict[str, str]
    ) -> DetectorResult:
        byte_length = len(body.encode("utf-8"))
        char_length = len(body)
        if byte_length <= self.max_bytes and char_length <= self.max_chars:
            self.truncated = False
            return DetectorResult()

        max_ratio = max(
            byte_length / self.max_bytes if byte_length > self.max_bytes else 1.0,
            char_length / self.max_chars if char_length > self.max_chars else 1.0,
        )
        score = max(10, min(100, int((max_ratio - 1.0) * 50)))
        self.truncated = True
        details = [
            f"Email size: {byte_length:,} bytes / {char_length:,} chars — "
            f"limit: {self.max_bytes:,} bytes / {self.max_chars:,} chars. "
            f"Would truncate to {self.truncation_length:,} chars."
        ]
        return DetectorResult(risk_score=score, triggered=True, details=details)
