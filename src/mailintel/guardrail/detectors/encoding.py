"""Encoded-payload anomaly detector."""

from __future__ import annotations

import base64
import re
from re import Pattern
from urllib.parse import unquote

from ..threat_profiles import compile_suspicious_decoded
from .base import BaseDetector, DetectorResult


class EncodingAnomalyDetector(BaseDetector):
    """Detect hidden instructions in base64, hex, and URL-encoded payloads."""

    BASE64_RE = re.compile(rb"[A-Za-z0-9+/=]{40,}")
    HEX_RE = re.compile(r"(?:\\x[0-9a-fA-F]{2}){4,}|(?:0x[0-9a-fA-F]{2}){4,}")
    URLENC_RE = re.compile(r"%[0-9a-fA-F]{2}")

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._min_base64 = config.get("min_base64_length", 40)
        self._decode_nested = config.get("decode_nested", True)
        self._suspicious_patterns: list[Pattern] = compile_suspicious_decoded()

    @property
    def name(self) -> str:
        return "encoding_anomaly"

    def scan(
        self, _sender: str, _subject: str, body: str, _headers: dict[str, str]
    ) -> DetectorResult:
        score = 0
        details: list[str] = []
        score += self._scan_base64(body, details)
        score += self._scan_hex(body, details)
        score += self._scan_urlencoded(body, details)
        score = min(score, 100)
        return DetectorResult(risk_score=score, triggered=score > 0, details=details)

    def _scan_base64(self, body: str, details: list[str]) -> int:
        score = 0
        seen: set[str] = set()

        for match in self.BASE64_RE.finditer(body.encode("utf-8")):
            chunk = match.group()
            if len(chunk) < self._min_base64 or not self._looks_like_base64(chunk):
                continue
            decoded_text = self._decode_base64(chunk)
            if decoded_text is None or decoded_text in seen:
                continue
            seen.add(decoded_text)
            if self._contains_suspicious(decoded_text):
                score += 30
                details.append(
                    f"Base64 blob decodes to suspicious text "
                    f"(len={len(decoded_text)}): {decoded_text[:120]!r}"
                )
            if self._decode_nested:
                score += self._scan_nested(decoded_text, details)

        return min(score, 60)

    @staticmethod
    def _looks_like_base64(chunk: bytes) -> bool:
        uppercase = sum(1 for byte in chunk if 65 <= byte <= 90)
        digits = sum(1 for byte in chunk if 48 <= byte <= 57)
        return uppercase > 0 or digits > 0

    @staticmethod
    def _decode_base64(chunk: bytes) -> str | None:
        try:
            padded = chunk + b"=" * (-len(chunk) % 4)
            decoded_bytes = base64.b64decode(padded, validate=True)
        except Exception:
            return None
        return decoded_bytes.decode("utf-8", errors="replace")

    def _scan_hex(self, body: str, details: list[str]) -> int:
        if not self.HEX_RE.findall(body):
            return 0
        decoded = self._decode_hex(body)
        if self._contains_suspicious(decoded):
            details.append("Hex-encoded suspicious content detected")
            return 25
        return 5

    def _scan_urlencoded(self, body: str, details: list[str]) -> int:
        if len(self.URLENC_RE.findall(body)) < 4:
            return 0
        decoded = unquote(body)
        if self._contains_suspicious(decoded):
            details.append("URL-encoded suspicious content detected")
            return 20
        return 5

    def _scan_nested(self, text: str, details: list[str]) -> int:
        score = 0
        for match in self.BASE64_RE.finditer(text.encode("utf-8")):
            double_text = self._decode_base64(match.group())
            if double_text is not None and self._contains_suspicious(double_text):
                score += 15
                details.append("Nested base64 encoding detected")
        return score

    @staticmethod
    def _decode_hex(body: str) -> str:
        result = []
        for match in re.finditer(r"\\x([0-9a-fA-F]{2})", body):
            result.append(chr(int(match.group(1), 16)))
        for match in re.finditer(r"0x([0-9a-fA-F]{2})", body):
            result.append(chr(int(match.group(1), 16)))
        return "".join(result)

    def _contains_suspicious(self, text: str) -> bool:
        lower = text.lower()
        return any(pattern.search(lower) for pattern in self._suspicious_patterns)
