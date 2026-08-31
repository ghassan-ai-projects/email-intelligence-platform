"""Public email guardrail scanner and compatibility facade."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .detectors import (
    BaseDetector,
    DetectorResult,
    EncodingAnomalyDetector,
    ExfiltrationGuardDetector,
    PromptInjectionDetector,
    RepetitionDetector,
    ReplyChainManipulationDetector,
    SizeGuardDetector,
    StructuralAnomalyDetector,
    UnicodeAttackDetector,
)

__all__ = [
    "BaseDetector",
    "DetectorResult",
    "EmailScanner",
    "EncodingAnomalyDetector",
    "ExfiltrationGuardDetector",
    "PromptInjectionDetector",
    "RepetitionDetector",
    "ReplyChainManipulationDetector",
    "ScanResult",
    "SizeGuardDetector",
    "StructuralAnomalyDetector",
    "UnicodeAttackDetector",
]


@dataclass
class ScanResult:
    """Result of scanning an email through the guardrail pipeline."""

    blocked: bool = False
    risk_score: int = 0
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    original_length: int = 0
    scan_duration_ms: float = 0.0


class EmailScanner:
    """Run configured detectors and aggregate their email-risk signals."""

    DEFAULT_CONFIG = {
        "block_threshold": 60,
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
        "structural_anomaly": {"max_headers": 50, "check_mime": True, "check_attachments": True},
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

    def __init__(self, config: dict | str | None = None):
        self._config = self._load_config(config)
        self._block_threshold = self._config.get(
            "block_threshold", self.DEFAULT_CONFIG["block_threshold"]
        )
        self._detectors = self._init_detectors()

    def _load_config(self, config: dict | str | None = None) -> dict:
        """Load detector configuration from defaults, JSON, or a JSON file."""
        if config is None:
            return dict(self.DEFAULT_CONFIG)
        if isinstance(config, str):
            path = Path(config)
            if path.is_file():
                return {**self.DEFAULT_CONFIG, **json.loads(path.read_text(encoding="utf-8"))}
            try:
                return {**self.DEFAULT_CONFIG, **json.loads(config)}
            except json.JSONDecodeError:
                return dict(self.DEFAULT_CONFIG)
        return {**self.DEFAULT_CONFIG, **config}

    def _init_detectors(self) -> list[BaseDetector]:
        """Instantiate detectors in the stable warning and score order."""
        detector_configs = [
            (PromptInjectionDetector, "prompt_injection"),
            (EncodingAnomalyDetector, "encoding_anomaly"),
            (SizeGuardDetector, "size_guard"),
            (UnicodeAttackDetector, "unicode_attack"),
            (StructuralAnomalyDetector, "structural_anomaly"),
            (ReplyChainManipulationDetector, "reply_chain"),
            (RepetitionDetector, "repetition"),
            (ExfiltrationGuardDetector, "exfiltration_guard"),
        ]
        return [
            detector(self._config.get(config_key, {})) for detector, config_key in detector_configs
        ]

    def scan(self, sender: str, subject: str, body: str, headers: dict | None = None) -> ScanResult:
        """Scan one email, aggregate detector signals, and record the verdict."""
        started_at = time.perf_counter()
        normalized_headers = headers or {}
        original_length = len(body.encode("utf-8"))
        scores, warnings, truncated = self._scan_detectors(
            sender, subject, body, normalized_headers
        )
        result = self._build_result(
            original_length=original_length,
            scores=scores,
            warnings=warnings,
            truncated=truncated,
            started_at=started_at,
        )
        self._log_scan(sender, subject, result)
        return result

    def _scan_detectors(
        self, sender: str, subject: str, body: str, headers: dict[str, str]
    ) -> tuple[list[int], list[str], bool]:
        scores: list[int] = []
        warnings: list[str] = []
        truncated = False
        for detector in self._detectors:
            detector_result = detector.scan(sender, subject, body, headers)
            if detector_result.triggered:
                scores.append(detector_result.risk_score)
                warnings.extend(detector_result.details)
            if detector_result.truncated:
                truncated = True
        return scores, warnings, truncated

    def _build_result(
        self,
        original_length: int,
        scores: list[int],
        warnings: list[str],
        truncated: bool,
        started_at: float,
    ) -> ScanResult:
        risk_score = self._aggregate_scores(scores) if scores else 0
        return ScanResult(
            risk_score=risk_score,
            warnings=warnings,
            truncated=truncated,
            original_length=original_length,
            blocked=risk_score >= self._block_threshold,
            scan_duration_ms=(time.perf_counter() - started_at) * 1000,
        )

    @staticmethod
    def _aggregate_scores(scores: list[int]) -> int:
        """Combine detector scores as max plus half the mean, clamped to 100."""
        if not scores:
            return 0
        max_score = max(scores)
        mean_score = sum(scores) / len(scores)
        return min(100, max(0, round(max_score + (mean_score / 2))))

    def _log_scan(self, sender: str, subject: str, result: ScanResult) -> None:
        """Append a bounded scan summary to the best-effort tracking log."""
        log_path = Path(
            os.environ.get(
                "EMAIL_GUARDRAIL_LOG",
                str(Path.home() / ".mailintel" / "guardrail-scan-log.ndjson"),
            )
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sender_present": bool(sender),
            "subject_length": len(subject),
            "score": result.risk_score,
            "blocked": result.blocked,
            "warning_count": len(result.warnings),
        }
        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    @property
    def detectors(self) -> list[BaseDetector]:
        """Return registered detectors for inspection and extension."""
        return list(self._detectors)
