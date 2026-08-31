"""Wrapper around EmailScanner for use within mailintel.

Provides a typed `scan_email()` function that accepts mailintel's native data
types and returns a `GuardrailResult`.  Configuration overrides come from the
mailintel config file's [guardrail] section.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .scanner import EmailScanner, ScanResult

# Re-export the scanner class so consumers can instantiate their own if needed.
EmailScanner = EmailScanner


@dataclass
class GuardrailResult:
    """Sanitised result tailored for the mailintel pipeline."""

    blocked: bool = False
    risk_score: int = 0
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    scan_duration_ms: float = 0.0

    @classmethod
    def from_scan_result(cls, sr: ScanResult) -> GuardrailResult:
        return cls(
            blocked=sr.blocked,
            risk_score=sr.risk_score,
            warnings=sr.warnings,
            truncated=sr.truncated,
            scan_duration_ms=sr.scan_duration_ms,
        )


def _get_scanner(config_override: dict[str, Any] | None = None) -> EmailScanner:
    """Build a request-local scanner so concurrent configurations cannot leak."""
    return EmailScanner(config_override)


def scan_email(
    sender: str,
    subject: str,
    body: str,
    headers: dict[str, str] | None = None,
    config_override: dict[str, Any] | None = None,
) -> GuardrailResult:
    """Run the full guardrail scanner pipeline on one email.

    Args:
        sender: From-address of the email.
        subject: Subject line text.
        body: Plain-text body content.
        headers: Optional dict of email headers (lowercase keys recommended).
        config_override: Optional dict merged on top of scanner defaults
                         (same structure as EmailScanner.DEFAULT_CONFIG).

    Returns:
        A GuardrailResult with the aggregated scan verdict.
    """
    scanner = _get_scanner(config_override)
    t0 = time.perf_counter()
    raw = scanner.scan(sender=sender, subject=subject, body=body, headers=headers or {})
    result = GuardrailResult.from_scan_result(raw)
    result.scan_duration_ms = (time.perf_counter() - t0) * 1000
    return result


def scan_email_parsed(
    from_addr: str,
    subject: str,
    body_text: str,
    config_override: dict[str, Any] | None = None,
) -> GuardrailResult:
    """Convenience wrapper that requires only the fields available post-parse."""
    return scan_email(
        sender=from_addr,
        subject=subject,
        body=body_text,
        config_override=config_override,
    )


def scan_email_from_config(
    from_addr: str,
    subject: str,
    body_text: str,
    guardrail_config: Any = None,
) -> GuardrailResult:
    """Scan using a mailintel GuardrailConfig object (from config.toml).

    Converts the Pydantic config into the flat dict expected by EmailScanner.
    """
    cfg = guardrail_config.scanner_config() if guardrail_config else None
    return scan_email_parsed(from_addr, subject, body_text, config_override=cfg)
