"""MCP tools for full email, thread, and attachment details."""

from __future__ import annotations

import base64

from .. import search
from ..attachment_store import attachment_text, load_attachment
from .runtime import _audit_tool, get_config, invocation_connection, mcp
from ..security import UNTRUSTED_NOTICE


@mcp.tool()
@_audit_tool
def get_email(email_id: int) -> dict:
    """Full detail for one email: body, recipients, attachments, extracted knowledge.

    Guardrail scan info (guardrail_score, guardrail_blocked, guardrail_warnings)
    is included when the email was scanned on ingest.
    """
    with invocation_connection() as conn:
        result = search.get_email(conn, email_id)
        if not result:
            return {"error": f"email {email_id} not found"}
        result["notice"] = UNTRUSTED_NOTICE
        return result


@mcp.tool()
@_audit_tool
def get_thread(thread_id: int) -> dict:
    """A whole conversation: participants, chronology, per-message summaries."""
    with invocation_connection() as conn:
        result = search.get_thread(conn, thread_id)
        if not result:
            return {"error": f"thread {thread_id} not found"}
        result["notice"] = UNTRUSTED_NOTICE
        return result


@mcp.tool()
@_audit_tool
def read_attachment(attachment_id: int, include_base64: bool = False) -> dict:
    """Read an attachment's content: text for PDFs/text files, base64 on request.

    Get attachment ids from get_email. include_base64 only works for files
    up to 2 MB.
    """
    cfg = get_config()
    with invocation_connection() as conn:
        meta = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if not meta:
            return {"error": f"attachment {attachment_id} not found"}
        result = {
            "attachment_id": attachment_id,
            "email_id": meta["email_id"],
            "filename": meta["filename"],
            "mime": meta["mime"],
            "size": meta["size"],
            "notice": UNTRUSTED_NOTICE,
        }
        text = meta["extracted_text"]
        raw = None
        if text is None or include_base64:
            loaded = load_attachment(conn, cfg.maildir.path, attachment_id)
            if not loaded:
                result["error"] = "attachment file no longer available in the Maildir"
                return result
            _, _, raw = loaded
            if text is None:
                text = attachment_text(meta["filename"], meta["mime"], raw)
        result["text"] = text
        if text is None:
            result["note"] = "binary attachment; use include_base64=true to fetch bytes"
        if include_base64:
            assert raw is not None
            if len(raw) > 2 * 1024 * 1024:
                result["error"] = f"file too large for base64 transfer ({len(raw)} bytes)"
            else:
                result["base64"] = base64.b64encode(raw).decode()
        return result
