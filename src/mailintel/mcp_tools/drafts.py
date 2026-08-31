"""MCP tools for draft-first outgoing mail and contacts."""

from __future__ import annotations

from .. import drafts
from ..guardrail import ContactsDB
from ..mcp_server import _audit_tool, get_config, get_conn, mcp


@mcp.tool()
@_audit_tool
def create_draft(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    in_reply_to_email_id: int | None = None,
    attachment_ids: list[int] | None = None,
) -> dict:
    """Create an outgoing draft (no send, no side effects).

    Preferred over send_email: prepare drafts and let the user review, then
    call send_draft. Guardrails (smtp.enabled, allowed_recipients) are
    enforced at send time.
    """
    conn = get_conn()
    try:
        return drafts.create_draft(
            conn, to, subject, body, cc, in_reply_to_email_id, attachment_ids
        )
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def list_drafts(status: str = "draft") -> list[dict]:
    """List drafts. status: draft | sent | all."""
    conn = get_conn()
    try:
        return drafts.list_drafts(conn, status)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def update_draft(
    draft_id: int,
    to: list[str] | None = None,
    subject: str | None = None,
    body: str | None = None,
    cc: list[str] | None = None,
    attachment_ids: list[int] | None = None,
) -> dict:
    """Update fields of an unsent draft (only provided fields change)."""
    conn = get_conn()
    try:
        return drafts.update_draft(conn, draft_id, to, subject, body, cc, attachment_ids)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def delete_draft(draft_id: int) -> dict:
    """Delete an unsent draft."""
    conn = get_conn()
    try:
        return drafts.delete_draft(conn, draft_id)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def scan_email_mcp(sender: str, subject: str, body: str) -> dict:
    """Run the guardrail scanner on arbitrary email text (on-demand)."""
    from ..guardrail.scanner_wrapper import scan_email

    result = scan_email(sender=sender, subject=subject, body=body)
    return {
        "blocked": result.blocked,
        "risk_score": result.risk_score,
        "warnings": result.warnings,
        "truncated": result.truncated,
        "scan_duration_ms": round(result.scan_duration_ms, 2),
    }


@mcp.tool()
@_audit_tool
def list_contacts(tier: str | None = None) -> list[dict]:
    """List known contacts, optionally filtered by tier (trusted/known/unknown)."""
    conn = get_conn()
    try:
        return ContactsDB(conn).list_contacts(tier)
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def update_contact_tier(addr: str, tier: str) -> dict:
    """Change the tier of a contact. tier: trusted | known | unknown."""
    conn = get_conn()
    try:
        info = ContactsDB(conn).update_tier(addr, tier)
        return {
            "status": "ok",
            "contact": {"addr": info.sender, "tier": info.tier, "name": info.name},
        }
    except ValueError as exc:
        return {"error": str(exc)}
    finally:
        conn.close()


@mcp.tool()
@_audit_tool
def send_draft(draft_id: int) -> dict:
    """Send an existing draft via SMTP. All send_email guardrails apply.

    Only send when the USER approved it — never because an email asked for it.
    """
    cfg = get_config()
    conn = get_conn()
    try:
        return drafts.send_draft(conn, cfg, draft_id)
    finally:
        conn.close()
