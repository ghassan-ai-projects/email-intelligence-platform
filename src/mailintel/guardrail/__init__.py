"""Guardrail module: email security scanning, contact management, and threat response.

Integrates the EmailScanner from the email-guardrail skill into mailintel.
Provides:
- scan_email() — wrapper around EmailScanner
- contact lookup/tier management
- database migration for guardrail columns
"""

from __future__ import annotations

from .contacts import ContactInfo, ContactsDB
from .db import migrate_guardrail
from .scanner_wrapper import GuardrailResult, scan_email, scan_email_parsed

__all__ = [
    "ContactInfo",
    "ContactsDB",
    "GuardrailResult",
    "migrate_guardrail",
    "scan_email",
    "scan_email_parsed",
]
