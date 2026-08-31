"""Email structure anomaly detector."""

from __future__ import annotations

import re

from ..threat_profiles import SUSPICIOUS_ATTACHMENT_EXTENSIONS, SUSPICIOUS_CONTENT_TYPES
from .base import BaseDetector, DetectorResult


class StructuralAnomalyDetector(BaseDetector):
    """Detect suspicious MIME types, headers, filenames, and extensions."""

    ENCODED_WORD_RE = re.compile(r"=\?[^?]+\?[BbQq]\?[^?]*\?=")

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._max_headers = config.get("max_headers", 50)
        self._check_mime = config.get("check_mime", True)
        self._check_attachments = config.get("check_attachments", True)

    @property
    def name(self) -> str:
        return "structural_anomaly"

    def scan(
        self, _sender: str, subject: str, body: str, headers: dict[str, str]
    ) -> DetectorResult:
        score = 0
        details: list[str] = []
        if self._check_mime:
            score += self._score_content_type(headers, details)
        score += self._score_encoded_filenames(headers, details)
        score += self._score_header_count(headers, details)
        if self._check_attachments:
            score += self._score_attachment_extensions(subject, body, details)
        return DetectorResult(risk_score=min(score, 100), triggered=score > 0, details=details)

    @staticmethod
    def _score_content_type(headers: dict[str, str], details: list[str]) -> int:
        content_type = headers.get("Content-Type", headers.get("content-type", "")).lower()
        if not content_type:
            return 0
        if any(bad_type in content_type for bad_type in SUSPICIOUS_CONTENT_TYPES):
            details.append(f"Suspicious Content-Type: {content_type}")
            return 30
        return 0

    def _score_encoded_filenames(self, headers: dict[str, str], details: list[str]) -> int:
        score = 0
        for key, value in headers.items():
            names_attachment = "filename" in key.lower() or "name" in key.lower()
            values_attachment = "filename" in value.lower() or "name" in value.lower()
            if (names_attachment or values_attachment) and self.ENCODED_WORD_RE.search(value):
                score += 15
                details.append(f"Encoded attachment filename in header {key}")
        return score

    def _score_header_count(self, headers: dict[str, str], details: list[str]) -> int:
        if len(headers) <= self._max_headers:
            return 0
        details.append(f"Excessive headers: {len(headers)} > {self._max_headers}")
        return 10

    @staticmethod
    def _score_attachment_extensions(subject: str, body: str, details: list[str]) -> int:
        for extension in SUSPICIOUS_ATTACHMENT_EXTENSIONS:
            pattern = re.compile(re.escape(extension) + r"\b", re.IGNORECASE)
            if pattern.search(body) or pattern.search(subject):
                details.append(f"Suspicious attachment extension in content: {extension}")
                return 10
        return 0
