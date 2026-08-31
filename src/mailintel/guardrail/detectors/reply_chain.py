"""Reply-chain manipulation detector."""

from __future__ import annotations

import re

from ..threat_profiles import QUOTE_PREFIXES, compile_suspicious_decoded
from .base import BaseDetector, DetectorResult


class ReplyChainManipulationDetector(BaseDetector):
    """Detect suspicious instructions hidden only in quoted reply content."""

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._quote_patterns = [
            re.compile(prefix, re.MULTILINE)
            for prefix in config.get("quote_prefixes", QUOTE_PREFIXES)
        ]
        self._suspicious_patterns = compile_suspicious_decoded()

    @property
    def name(self) -> str:
        return "reply_chain_manipulation"

    def scan(
        self, _sender: str, _subject: str, body: str, _headers: dict[str, str]
    ) -> DetectorResult:
        if not body:
            return DetectorResult()
        quoted_text, new_text = self._split_quoted(body)
        if not quoted_text:
            return DetectorResult()
        quoted_suspicious = self._count_suspicious(quoted_text)
        new_suspicious = self._count_suspicious(new_text)
        if quoted_suspicious > 0 and new_suspicious == 0:
            score = min(100, quoted_suspicious * 15)
            return DetectorResult(
                risk_score=score,
                triggered=True,
                details=[
                    f"Manipulation detected: {quoted_suspicious} suspicious "
                    f"pattern(s) in quoted text, 0 in new content. "
                    f"Instructions may be hidden in reply chain."
                ],
            )
        if quoted_suspicious > 0 and new_suspicious > 0:
            return DetectorResult()
        return DetectorResult()

    def _split_quoted(self, body: str) -> tuple[str, str]:
        quoted_lines: list[str] = []
        new_lines: list[str] = []
        in_quoted = False
        for line in body.split("\n"):
            if self._is_quoted_line(line):
                in_quoted = True
                quoted_lines.append(line)
            elif in_quoted and line.strip() == "":
                quoted_lines.append(line)
            elif in_quoted:
                in_quoted = False
                new_lines.append(line)
            else:
                new_lines.append(line)
        return "\n".join(quoted_lines), "\n".join(new_lines)

    def _is_quoted_line(self, line: str) -> bool:
        return any(pattern.match(line) for pattern in self._quote_patterns)

    def _count_suspicious(self, text: str) -> int:
        lower = text.lower()
        return sum(len(pattern.findall(lower)) for pattern in self._suspicious_patterns)
