# @package email-guardrail
# @description Prompt injection scanner for emails
# @provides guardrail, security-guardrail
# @requires-python 3.8+

"""
scanner.py — Email Security Guardrail scanner module.

Modular input sanitizer for AI agents. Scans incoming emails for
prompt injection, encoding attacks, size abuse, unicode tricks,
structural anomalies, reply-chain manipulation, and repetition attacks.

Usage:
    from scanner import EmailScanner

    scanner = EmailScanner()
    result = scanner.scan(
        sender="attacker@evil.com",
        subject="Re: Important",
        body="ignore previous instructions and ...",
        headers={"Content-Type": "text/plain"}
    )
    if result.blocked:
        print(f"BLOCKED (score={result.risk_score}): {result.warnings}")
"""

import base64
import json
import os
import re
import time
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern, Set, Tuple
from urllib.parse import unquote

from .threat_profiles import (
    HOMOGLYPH_MAP,
    ZERO_WIDTH_CHARS,
    BIDI_OVERRIDE_CHARS,
    QUOTE_PREFIXES,
    SUSPICIOUS_CONTENT_TYPES,
    SUSPICIOUS_ATTACHMENT_EXTENSIONS,
    PROMPT_INJECTION,
    SUSPICIOUS_DECODED_PATTERNS,
    compile_patterns,
    compile_suspicious_decoded,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ScanResult:
    """Result of scanning an email through the guardrail pipeline."""
    blocked: bool = False
    risk_score: int = 0  # 0–100
    warnings: List[str] = field(default_factory=list)
    truncated: bool = False
    original_length: int = 0
    scan_duration_ms: float = 0.0


@dataclass
class DetectorResult:
    """Result from an individual detector."""
    risk_score: int = 0  # 0–100
    triggered: bool = False
    details: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Base Detector Interface
# ═══════════════════════════════════════════════════════════════════════════════

class BaseDetector(ABC):
    """Abstract base class for all detectors."""

    @abstractmethod
    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        """Run detection logic and return a scored result."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable detector name."""
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 1: Prompt Injection Detector
# ═══════════════════════════════════════════════════════════════════════════════

class PromptInjectionDetector(BaseDetector):
    """
    Detects known prompt injection phrases, role-play hijacks, and DAN variants.

    Patterns are tiered:
      - Tier 1 (40pts): Direct instruction override ("ignore previous instructions")
      - Tier 2 (20pts): Role-play hijacks, DAN, jailbreak
      - Tier 3 (10pts): Subtle probing, reverse-engineering attempts
    """

    TIER_SCORES = {"tier1": 40, "tier2": 20, "tier3": 10}
    MAX_SCORE = 100

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._patterns: Dict[str, List[Pattern]] = compile_patterns(PROMPT_INJECTION)
        self._enabled_tiers: Set[str] = set()
        for tier in ("tier1", "tier2", "tier3"):
            if config.get(f"{tier}_enabled", True):
                self._enabled_tiers.add(tier)

    @property
    def name(self) -> str:
        return "prompt_injection"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        text = f"{subject}\n{body}".lower()
        score = 0
        details: List[str] = []

        for tier, patterns in self._patterns.items():
            if tier not in self._enabled_tiers:
                continue
            for pattern in patterns:
                if pattern.search(text):
                    pts = self.TIER_SCORES[tier]
                    score += pts
                    details.append(
                        f"Prompt injection [{tier}] (+{pts}): "
                        f"matched /{pattern.pattern}/"
                    )

        score = min(score, self.MAX_SCORE)
        return DetectorResult(
            risk_score=score,
            triggered=score > 0,
            details=details,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 2: Encoding Anomaly Detector
# ═══════════════════════════════════════════════════════════════════════════════

class EncodingAnomalyDetector(BaseDetector):
    """
    Detects hidden instructions in encoded payloads.

    Scans for:
    - Base64 blobs that decode to suspicious instructions
    - Hex-encoded strings (\\xNN or 0xNN format)
    - URL-encoded payloads (%NN format)
    - Nested/stacked encodings
    """

    # Match long base64 strings (≥40 chars of [A-Za-z0-9+/=])
    BASE64_RE = re.compile(rb'[A-Za-z0-9+/=]{40,}')
    # Match hex escape sequences like \\x68\\x65\\x6c or 0x680x65
    HEX_RE = re.compile(r'(?:\\x[0-9a-fA-F]{2}){4,}|(?:0x[0-9a-fA-F]{2}){4,}')
    # Match URL-encoded sequences (allow non-consecutive — %20foo%20 is still encoded)
    URLENC_RE = re.compile(r'%[0-9a-fA-F]{2}')

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._min_base64 = config.get("min_base64_length", 40)
        self._decode_nested = config.get("decode_nested", True)
        self._suspicious_patterns = compile_suspicious_decoded()

    @property
    def name(self) -> str:
        return "encoding_anomaly"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        score = 0
        details: List[str] = []

        score += self._scan_base64(body, details)
        score += self._scan_hex(body, details)
        score += self._scan_urlencoded(body, details)

        score = min(score, 100)
        return DetectorResult(
            risk_score=score,
            triggered=score > 0,
            details=details,
        )

    def _scan_base64(self, body: str, details: List[str]) -> int:
        raw = body.encode("utf-8")
        score = 0
        seen = set()

        for match in self.BASE64_RE.finditer(raw):
            chunk = match.group()
            # Ensure proper padding and length (base64 length % 4 == 0 when padded)
            # Skip very short matches that are likely normal text
            if len(chunk) < self._min_base64:
                continue
            # Check that this actually looks like base64 with proper charset mix
            uc = sum(1 for b in chunk if 65 <= b <= 90)   # A-Z
            lc = sum(1 for b in chunk if 97 <= b <= 122)  # a-z
            digits = sum(1 for b in chunk if 48 <= b <= 57)  # 0-9
            if uc == 0 and digits == 0:
                continue  # all lowercase = probably normal text

            # Try decoding
            try:
                # Pad if needed
                padded = chunk + b'=' * (-len(chunk) % 4)
                decoded_bytes = base64.b64decode(padded, validate=True)
                decoded_text = decoded_bytes.decode("utf-8", errors="replace")
            except Exception:
                continue

            if decoded_text in seen:
                continue
            seen.add(decoded_text)

            if self._contains_suspicious(decoded_text):
                score += 30
                details.append(
                    f"Base64 blob decodes to suspicious text "
                    f"(len={len(decoded_text)}): "
                    f"{decoded_text[:120]!r}"
                )

            # Always try nested decoding (catches double-encoded payloads)
            if self._decode_nested:
                nested_score = self._scan_nested(decoded_text, details)
                score += nested_score

        return min(score, 60)

    def _scan_hex(self, body: str, details: List[str]) -> int:
        matches = self.HEX_RE.findall(body)
        if not matches:
            return 0

        decoded = self._decode_hex(body)
        if self._contains_suspicious(decoded):
            details.append("Hex-encoded suspicious content detected")
            return 25

        return 5  # Hex pattern found but not obviously suspicious

    def _scan_urlencoded(self, body: str, details: List[str]) -> int:
        matches = self.URLENC_RE.findall(body)
        if len(matches) < 4:  # Need at least 4 encoded sequences
            return 0

        decoded = unquote(body)
        if self._contains_suspicious(decoded):
            details.append("URL-encoded suspicious content detected")
            return 20

        return 5

    def _scan_nested(self, text: str, details: List[str]) -> int:
        """Recursively check if decoded text contains further encoding."""
        score = 0
        # Check for nested base64
        raw = text.encode("utf-8")
        for match in self.BASE64_RE.finditer(raw):
            try:
                padded = match.group() + b'=' * (-len(match.group()) % 4)
                double_decoded = base64.b64decode(padded, validate=True)
                double_text = double_decoded.decode("utf-8", errors="replace")
                if self._contains_suspicious(double_text):
                    score += 15
                    details.append("Nested base64 encoding detected")
            except Exception:
                pass
        return score

    @staticmethod
    def _decode_hex(body: str) -> str:
        """Decode \\xNN and 0xNN hex sequences from text."""
        result = []
        # Match \\xNN
        for m in re.finditer(r'\\x([0-9a-fA-F]{2})', body):
            result.append(chr(int(m.group(1), 16)))
        # Match 0xNN
        for m in re.finditer(r'0x([0-9a-fA-F]{2})', body):
            result.append(chr(int(m.group(1), 16)))
        return ''.join(result)

    def _contains_suspicious(self, text: str) -> bool:
        """Check decoded text against known suspicious patterns."""
        lower = text.lower()
        for pat in self._suspicious_patterns:
            if pat.search(lower):
                return True
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 3: Size Guard Detector
# ═══════════════════════════════════════════════════════════════════════════════

class SizeGuardDetector(BaseDetector):
    """
    Prevents cost explosion from oversized email bodies.

    Truncates emails exceeding configurable limits, reports original size.
    Scores proportionally to how much the email exceeds limits.
    """

    # 1 MB default
    DEFAULT_MAX_BYTES = 1_048_576
    DEFAULT_MAX_CHARS = 1_000_000
    DEFAULT_TRUNCATION_LENGTH = 100_000

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self.max_bytes = config.get("max_bytes", self.DEFAULT_MAX_BYTES)
        self.max_chars = config.get("max_chars", self.DEFAULT_MAX_CHARS)
        self.truncation_length = config.get("truncation_length",
                                             self.DEFAULT_TRUNCATION_LENGTH)
        self.truncated = False

    @property
    def name(self) -> str:
        return "size_guard"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        byte_len = len(body.encode("utf-8"))
        char_len = len(body)

        if byte_len <= self.max_bytes and char_len <= self.max_chars:
            self.truncated = False
            return DetectorResult(risk_score=0, triggered=False)

        # Score proportional to how much we exceed limits
        byte_ratio = byte_len / self.max_bytes if byte_len > self.max_bytes else 1.0
        char_ratio = char_len / self.max_chars if char_len > self.max_chars else 1.0
        max_ratio = max(byte_ratio, char_ratio)

        # 0 at threshold, ~50 at 2x, ~90 at 10x
        excess = max_ratio - 1.0
        score = min(100, int(excess * 50))

        # Even slightly over gets at least 10
        score = max(10, score)

        self.truncated = True
        details = [
            f"Email size: {byte_len:,} bytes / {char_len:,} chars — "
            f"limit: {self.max_bytes:,} bytes / {self.max_chars:,} chars. "
            f"Would truncate to {self.truncation_length:,} chars."
        ]

        return DetectorResult(
            risk_score=score,
            triggered=True,
            details=details,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 4: Unicode Attack Detector
# ═══════════════════════════════════════════════════════════════════════════════

class UnicodeAttackDetector(BaseDetector):
    """
    Detects unicode-based attacks:
    - Zero-width characters (steganography / invisible injection)
    - Bidirectional override characters (BIDI attacks)
    - Homoglyph/homograph substitution (confusable chars)
    - Excessive emoji density (steganography carrier)
    """

    EMOJI_RANGE = re.compile(
        "[\U0001F600-\U0001F64F"   # Emoticons
        "\U0001F300-\U0001F5FF"    # Misc Symbols & Pictographs
        "\U0001F680-\U0001F6FF"    # Transport & Map
        "\U0001F1E0-\U0001F1FF"    # Flags
        "\U00002702-\U000027B0"    # Dingbats
        "\U000024C2-\U0001F251"    # Enclosed characters
        "\U0001F900-\U0001F9FF"    # Supplemental Symbols
        "\U0001FA00-\U0001FA6F"    # Chess Symbols
        "\U0001FA70-\U0001FAFF"    # Symbols Extended-A
        "\U00002600-\U000026FF"    # Misc symbols
        "\U0000FE00-\U0000FE0F"    # Variation selectors
        "]"
    )

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._zw_score_per_char = config.get("zw_score_per_char", 5)
        self._bidi_score_per_char = config.get("bidi_score_per_char", 10)
        self._homoglyph_score = config.get("homoglyph_score", 10)
        self._emoji_threshold = config.get("emoji_threshold", 0.20)
        self._emoji_score = config.get("emoji_score", 15)

    @property
    def name(self) -> str:
        return "unicode_attack"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        text = f"{subject}\n{body}"
        score = 0
        details: List[str] = []

        # ── Zero-Width Character Scan ──
        zw_found: Dict[str, str] = {}
        for char, name in ZERO_WIDTH_CHARS.items():
            count = text.count(char)
            if count:
                zw_found[name] = count

        if zw_found:
            total_zw = sum(zw_found.values())
            score += total_zw * self._zw_score_per_char
            desc = ", ".join(f"{name}={n}" for name, n in zw_found.items())
            details.append(
                f"Zero-width characters detected ({total_zw} total): {desc}"
            )

        # ── BIDI Override Scan ──
        bidi_found: Dict[str, str] = {}
        for char, name in BIDI_OVERRIDE_CHARS.items():
            count = text.count(char)
            if count:
                bidi_found[name] = count

        if bidi_found:
            total_bidi = sum(bidi_found.values())
            score += total_bidi * self._bidi_score_per_char
            desc = ", ".join(f"{name}={n}" for name, n in bidi_found.items())
            details.append(
                f"Bidirectional override characters ({total_bidi} total): {desc}"
            )

        # ── Homoglyph Scan ──
        homoglyph_found: Dict[str, Tuple[str, int]] = {}
        for char, replacement in HOMOGLYPH_MAP.items():
            count = text.count(char)
            if count:
                homoglyph_found[char] = (replacement, count)

        if homoglyph_found:
            score += self._homoglyph_score
            char_preview = ", ".join(
                f"'{c}'→'{r}' (×{n})"
                for c, (r, n) in homoglyph_found.items()
            )
            details.append(
                f"Homoglyph substitutions detected: {char_preview}"
            )

        # ── Emoji Steganography Check ──
        emoji_count = len(self.EMOJI_RANGE.findall(text))
        printable_len = max(1, len([c for c in text if not c.isspace()]))
        emoji_ratio = emoji_count / printable_len

        if emoji_ratio > self._emoji_threshold:
            score += self._emoji_score
            details.append(
                f"High emoji density ({emoji_count}/{printable_len} = "
                f"{emoji_ratio:.0%}) — potential steganography carrier"
            )

        score = min(score, 100)
        return DetectorResult(
            risk_score=score,
            triggered=score > 0,
            details=details,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 5: Structural Anomaly Detector
# ═══════════════════════════════════════════════════════════════════════════════

class StructuralAnomalyDetector(BaseDetector):
    """
    Detects structural anomalies in email:
    - Suspicious Content-Type headers
    - Encoded/obfuscated attachment filenames
    - Excessive headers
    - Suspicious attachment extensions
    """

    # Match encoded-word in headers like =?utf-8?B?...?=
    ENCODED_WORD_RE = re.compile(r'=\?[^?]+\?[BbQq]\?[^?]*\?=')

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._max_headers = config.get("max_headers", 50)
        self._check_mime = config.get("check_mime", True)
        self._check_attachments = config.get("check_attachments", True)

    @property
    def name(self) -> str:
        return "structural_anomaly"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        score = 0
        details: List[str] = []

        # ── Content-Type Check ──
        if self._check_mime:
            content_type = headers.get("Content-Type", headers.get("content-type", "")).lower()
            if content_type:
                for bad_type in SUSPICIOUS_CONTENT_TYPES:
                    if bad_type in content_type:
                        score += 30
                        details.append(f"Suspicious Content-Type: {content_type}")
                        break

        # ── Encoded filenames in headers ──
        for key, value in headers.items():
            if ("filename" in key.lower() or "name" in key.lower()
                    or "filename" in value.lower() or "name" in value.lower()):
                if self.ENCODED_WORD_RE.search(value):
                    score += 15
                    details.append(
                        f"Encoded attachment filename in header {key}"
                    )

        # ── Excessive headers ──
        if len(headers) > self._max_headers:
            score += 10
            details.append(
                f"Excessive headers: {len(headers)} > {self._max_headers}"
            )

        # ── Suspicious attachment extensions in body ──
        if self._check_attachments:
            for ext in SUSPICIOUS_ATTACHMENT_EXTENSIONS:
                # Look for filename patterns in the body
                pattern = re.compile(
                    re.escape(ext) + r'\b',
                    re.IGNORECASE
                )
                if pattern.search(body) or pattern.search(subject):
                    score += 10
                    details.append(
                        f"Suspicious attachment extension in content: {ext}"
                    )
                    break

        score = min(score, 100)
        return DetectorResult(
            risk_score=score,
            triggered=score > 0,
            details=details,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 6: Reply-Chain Manipulation Detector
# ═══════════════════════════════════════════════════════════════════════════════

class ReplyChainManipulationDetector(BaseDetector):
    """
    Detects reply-chain manipulation — where quoted/replied-to text contains
    instructions that differ from the new content.

    Goal: catch attempts to smuggle instructions via "hidden" quoted context
    that the user might not notice but the AI would process.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._quote_patterns = [
            re.compile(q, re.MULTILINE) for q in config.get(
                "quote_prefixes", QUOTE_PREFIXES
            )
        ]
        self._suspicious_patterns = compile_suspicious_decoded()

    @property
    def name(self) -> str:
        return "reply_chain_manipulation"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        if not body:
            return DetectorResult(risk_score=0, triggered=False)

        # Split into quoted vs new content
        quoted_text, new_text = self._split_quoted(body)

        if not quoted_text:
            return DetectorResult(risk_score=0, triggered=False)

        # Check both parts for suspicious content
        quoted_suspicious = self._count_suspicious(quoted_text)
        new_suspicious = self._count_suspicious(new_text)

        if quoted_suspicious > 0 and new_suspicious == 0:
            # Instructions hidden in quoted text only — manipulation attempt
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
            # Both parts have suspicious content — genuine injection
            return DetectorResult(
                risk_score=0,
                triggered=False,
                details=[],
            )

        return DetectorResult(risk_score=0, triggered=False)

    def _split_quoted(self, body: str) -> Tuple[str, str]:
        """Split body into quoted and new text sections."""
        lines = body.split("\n")
        quoted_lines: List[str] = []
        new_lines: List[str] = []
        in_quoted = False

        for line in lines:
            # Check if line starts with a quote marker
            is_quoted = any(p.match(line) for p in self._quote_patterns)

            if is_quoted:
                in_quoted = True
                quoted_lines.append(line)
            elif in_quoted and line.strip() == "":
                # Empty line in quoted section
                quoted_lines.append(line)
            elif in_quoted:
                # Transition to new content
                in_quoted = False
                new_lines.append(line)
            else:
                new_lines.append(line)

        return "\n".join(quoted_lines), "\n".join(new_lines)

    def _count_suspicious(self, text: str) -> int:
        """Count suspicious pattern matches in text."""
        lower = text.lower()
        count = 0
        for pat in self._suspicious_patterns:
            matches = pat.findall(lower)
            count += len(matches)
        return count


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 7: Repetition Detector
# ═══════════════════════════════════════════════════════════════════════════════

class RepetitionDetector(BaseDetector):
    """
    Detects excessive repetition designed to overwhelm context or bypass
    pattern-matching.

    Checks:
    - Repeated lines (same line > N times)
    - Repeated n-grams (5-gram appearing > 50% of total length)
    - Character-level repetition (single char repeated)
    - Padding patterns (repeated whitespace/separators)
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._ngram_size = config.get("ngram_size", 5)
        self._max_repetition_ratio = config.get("max_repetition_ratio", 0.50)
        self._min_line_repeat = config.get("min_line_repeat", 3)

    @property
    def name(self) -> str:
        return "repetition"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        if not body:
            return DetectorResult(risk_score=0, triggered=False)

        score = 0
        details: List[str] = []

        text = f"{subject}\n{body}"

        # ── Line-level repetition ──
        score += self._check_line_repetition(body, details)

        # ── N-gram frequency analysis ──
        score += self._check_ngram_repetition(text, details)

        # ── Single-character padding ──
        score += self._check_character_padding(text, details)

        score = min(score, 100)
        return DetectorResult(
            risk_score=score,
            triggered=score > 0,
            details=details,
        )

    def _check_line_repetition(self, body: str, details: List[str]) -> int:
        """Check for repeated lines."""
        lines = [l.strip() for l in body.split("\n") if l.strip()]
        if not lines:
            return 0

        from collections import Counter
        line_counts = Counter(lines)
        repeated = {line: count for line, count in line_counts.most_common(5)
                    if count >= self._min_line_repeat}

        if repeated:
            total = sum(repeated.values())
            line_desc = "; ".join(
                f"'{l[:40]}' ×{n}" for l, n in repeated.items()
            )
            details.append(
                f"Excessive line repetition: {total} repeated lines. "
                f"{line_desc}"
            )
            # Scale: 3 repeats = 10, 10+ repeats = 50
            return min(50, total * 5)

        return 0

    def _check_ngram_repetition(self, text: str, details: List[str]) -> int:
        """Check for dominant n-grams (context filler)."""
        # Only check words, skip whitespace
        words = text.split()
        if len(words) < self._ngram_size * 2:
            return 0

        # Build n-grams as tuples of words
        ngrams: Dict[Tuple[str, ...], int] = {}
        for i in range(len(words) - self._ngram_size + 1):
            ngram = tuple(words[i:i + self._ngram_size])
            # Skip n-grams containing only noise
            if all(len(w) <= 2 for w in ngram):
                continue
            ngrams[ngram] = ngrams.get(ngram, 0) + 1

        if not ngrams:
            return 0

        most_common_ngram, max_count = max(ngrams.items(), key=lambda x: x[1])
        total_ngrams = len(ngrams)
        ratio = max_count / max(1, total_ngrams)

        if ratio > self._max_repetition_ratio:
            ngram_text = " ".join(most_common_ngram)
            details.append(
                f"N-gram repetition: '{ngram_text[:60]}' appears {max_count}x "
                f"({ratio:.0%} of unique n-grams)"
            )
            return min(40, int(ratio * 60))

        return 0

    def _check_character_padding(self, text: str, details: List[str]) -> int:
        """Detect excessive single-character repetition (padding)."""
        # Count runs of same character
        from collections import Counter
        char_runs = Counter()
        current_char = ""
        run_length = 0

        for ch in text.lower():
            if ch == current_char:
                run_length += 1
            else:
                if run_length >= 5:
                    char_runs[current_char] = max(
                        char_runs.get(current_char, 0), run_length
                    )
                current_char = ch
                run_length = 1

        # Final run
        if run_length >= 5:
            char_runs[current_char] = max(
                char_runs.get(current_char, 0), run_length
            )

        if char_runs:
            total_repeated = sum(char_runs.values())
            # Check if padding chars dominate
            padding_chars = {c for c in char_runs if c in " \t\n.,!?-~_*#"}
            padding_total = sum(v for c, v in char_runs.items() if c in padding_chars)
            non_padding_total = total_repeated - padding_total

            if padding_total > 200:
                details.append(
                    f"Character padding detected: {padding_total} repeated "
                    f"whitespace/separator chars"
                )
                return 20

            if non_padding_total > 50:
                desc = "; ".join(
                    f"'{c}' ×{n}" for c, n in char_runs.items()
                    if c not in padding_chars and n >= 10
                )
                if desc:
                    details.append(f"Excessive character runs: {desc}")
                    return 15

        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Detector 8: Sensitive Data Exfiltration Detector
# ═══════════════════════════════════════════════════════════════════════════════

class ExfiltrationGuardDetector(BaseDetector):
    """
    Detects requests designed to extract sensitive information.

    Unlike the PromptInjectionDetector which looks for attck patterns
    ("ignore previous instructions"), this looks for legitimate-sounding
    requests that aim to extract secrets, credentials, or personal data.

    Tier 1 (50pts): Direct extraction asks
      - "send me your key"
      - "what is your password"
      - "verify your identity by sending"
      - "give me access to"

    Tier 2 (30pts): Credential-like requests
      - "what is the api key"
      - "send me the token"
      - "provide your credentials"

    Tier 3 (15pts): Information gathering
      - "tell me your email address"
      - "what account do you use"
    """

    TIER_SCORES = {"tier1": 50, "tier2": 30, "tier3": 15}
    MAX_SCORE = 100

    # Patterns for sensitive info requests — word boundaries matter here
    # to avoid false positives on "key" in "keyboard" or "api" in "apical"
    EXFIL_PATTERNS: Dict[str, List[str]] = {
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

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        self._patterns: Dict[str, List[Pattern]] = {}
        for tier, patterns in self.EXFIL_PATTERNS.items():
            enabled = config.get(f"{tier}_enabled", True)
            if enabled:
                compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
                self._patterns[tier] = compiled
        self._enabled_tiers: Set[str] = set(self._patterns.keys())

        # Sender trust: if from YOUR trusted domain, reduce suspicion
        self._trusted_domains = config.get("trusted_domains", [
            "gmx.de", "gmx.net",
            "github.com", "thunderbird.net",
        ])

    @property
    def name(self) -> str:
        return "exfiltration_guard"

    def scan(self, sender: str, subject: str, body: str,
             headers: Dict[str, str]) -> DetectorResult:
        text = f"{subject}\n{body}\n{subject}".lower()
        score = 0
        details: List[str] = []

        # Reduce score if sender is from a known safe domain
        domain_penalty = 0
        sender_lower = sender.lower()
        for domain in self._trusted_domains:
            if domain in sender_lower:
                domain_penalty = 15  # known domain = less suspicious
                break

        for tier, patterns in self._patterns.items():
            if tier not in self._enabled_tiers:
                continue
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    pts = max(0, self.TIER_SCORES[tier] - domain_penalty)
                    score += pts
                    details.append(
                        f"Exfiltration attempt [{tier}] (+{pts}): "
                        f"matched '{match.group()}'"
                    )
                    break  # one match per tier is enough

        score = min(score, self.MAX_SCORE)
        return DetectorResult(
            risk_score=score,
            triggered=score > 0,
            details=details,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Main EmailScanner
# ═══════════════════════════════════════════════════════════════════════════════

class EmailScanner:
    """
    Main scanner orchestrator. Runs all detectors and aggregates scores.

    Args:
        config: Optional dict or path to JSON config file.
                If None, loads defaults for all detectors.
        block_threshold: Risk score threshold above which email is blocked (0-100).
    """

    # Default config baked in to avoid file dependency
    DEFAULT_CONFIG = {
        "block_threshold": 60,  # TODO: tune after 30+ real scans — track FP rate in Storage/email-guardrail-fp-log.md
        "prompt_injection": {"tier1_enabled": True, "tier2_enabled": True, "tier3_enabled": True},
        "encoding_anomaly": {"min_base64_length": 40, "decode_nested": True},
        "size_guard": {
            "max_bytes": SizeGuardDetector.DEFAULT_MAX_BYTES,
            "max_chars": SizeGuardDetector.DEFAULT_MAX_CHARS,
            "truncation_length": SizeGuardDetector.DEFAULT_TRUNCATION_LENGTH,
        },
        "unicode_attack": {
            "zw_score_per_char": 5,
            "bidi_score_per_char": 10,
            "homoglyph_score": 10,
            "emoji_threshold": 0.20,
            "emoji_score": 15,
        },
        "structural_anomaly": {
            "max_headers": 50,
            "check_mime": True,
            "check_attachments": True,
        },
        "reply_chain": {},
        "repetition": {
            "ngram_size": 5,
            "max_repetition_ratio": 0.50,
            "min_line_repeat": 3,
        },
        "exfiltration_guard": {
            "tier1_enabled": True,
            "tier2_enabled": True,
            "tier3_enabled": True,
        },
    }

    def __init__(self, config: Optional[dict] = None):
        self._config = self._load_config(config)
        self._block_threshold = self._config.get("block_threshold", self.DEFAULT_CONFIG["block_threshold"])
        self._detectors: List[BaseDetector] = self._init_detectors()

    def _load_config(self, config: Optional[dict] = None) -> dict:
        """Load config from dict, JSON string, or JSON file path."""
        if config is None:
            return dict(self.DEFAULT_CONFIG)

        if isinstance(config, str):
            if os.path.isfile(config):
                with open(config, "r") as f:
                    return {**self.DEFAULT_CONFIG, **json.load(f)}
            # Try as JSON string
            try:
                return {**self.DEFAULT_CONFIG, **json.loads(config)}
            except json.JSONDecodeError:
                return dict(self.DEFAULT_CONFIG)

        if isinstance(config, dict):
            return {**self.DEFAULT_CONFIG, **config}

        return dict(self.DEFAULT_CONFIG)

    def _init_detectors(self) -> List[BaseDetector]:
        """Instantiate all detectors with their subsection of config."""
        return [
            PromptInjectionDetector(self._config.get("prompt_injection", {})),
            EncodingAnomalyDetector(self._config.get("encoding_anomaly", {})),
            SizeGuardDetector(self._config.get("size_guard", {})),
            UnicodeAttackDetector(self._config.get("unicode_attack", {})),
            StructuralAnomalyDetector(self._config.get("structural_anomaly", {})),
            ReplyChainManipulationDetector(self._config.get("reply_chain", {})),
            RepetitionDetector(self._config.get("repetition", {})),
            ExfiltrationGuardDetector(self._config.get("exfiltration_guard", {})),
        ]

    def scan(self, sender: str, subject: str, body: str,
             headers: Optional[dict] = None) -> ScanResult:
        """
        Run the full scanner pipeline.

        Args:
            sender: Email sender address.
            subject: Email subject line.
            body: Email body content.
            headers: Dict of email headers (lowercase keys recommended).

        Returns:
            ScanResult with block decision, risk score, and warnings.
        """
        t0 = time.perf_counter()
        headers = headers or {}
        body_bytes = body.encode("utf-8")

        result = ScanResult(original_length=len(body_bytes))
        all_warnings: List[str] = []
        scores: List[int] = []
        truncated = False

        for detector in self._detectors:
            dr = detector.scan(sender, subject, body, headers)
            if dr.triggered:
                scores.append(dr.risk_score)
                all_warnings.extend(dr.details)
            if hasattr(detector, 'truncated') and detector.truncated:
                truncated = True

        # Aggregate scores
        if scores:
            result.risk_score = self._aggregate_scores(scores)

        result.warnings = all_warnings
        result.truncated = truncated
        result.blocked = result.risk_score >= self._block_threshold
        result.scan_duration_ms = (time.perf_counter() - t0) * 1000

        # Log scan result for FP tracking
        self._log_scan(sender, subject, result)

        return result

    @staticmethod
    def _aggregate_scores(scores: List[int]) -> int:
        """
        Final score = max(scores) + mean(scores) / 2, clamped to [0, 100].

        Rationale: The max ensures one highly suspicious detector triggers blocking.
        The weighted mean adds cumulative signal from multiple weaker signals.
        """
        if not scores:
            return 0
        max_s = max(scores)
        mean_s = sum(scores) / len(scores)
        raw = max_s + (mean_s / 2)
        return min(100, max(0, int(round(raw))))

    def _log_scan(self, sender: str, subject: str, result: 'ScanResult') -> None:
        """Log every scan result into the FP tracking log."""
        import json, os
        log_path = os.environ.get(
            "EMAIL_GUARDRAIL_LOG",
            os.path.expanduser("~/.mailintel/guardrail-scan-log.ndjson"),
        )
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sender": sender,
            "subject": subject[:60],
            "score": result.risk_score,
            "blocked": result.blocked,
            "warnings": result.warnings[:3],
        }
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # best-effort logging

    @property
    def detectors(self) -> List[BaseDetector]:
        """Return the list of registered detectors (for inspection/testing)."""
        return list(self._detectors)
