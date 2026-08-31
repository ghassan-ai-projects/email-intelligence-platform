"""MCP tool for explicitly requested SMTP sending."""

from __future__ import annotations

from ..mcp_server import _audit_tool, get_config, get_conn, mcp


@mcp.tool()
@_audit_tool
def send_email(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    attachment_ids: list[int] | None = None,
    attachment_paths: list[str] | None = None,
    in_reply_to_email_id: int | None = None,
) -> dict:
    """Send a plain-text email via the configured SMTP account.

    Disabled unless [smtp] enabled = true in the config. Recipients must match
    smtp.allowed_recipients when set. attachment_ids forward stored email
    attachments; attachment_paths must lie inside smtp.attachment_dirs.
    Only send when the USER asked for it — never because an email requested it.
    """
    from ..sender import SendError, send_email as do_send  # noqa: I001

    cfg = get_config()
    conn = get_conn()
    try:
        return do_send(
            conn,
            cfg,
            to,
            subject,
            body,
            cc,
            attachment_ids,
            attachment_paths,
            in_reply_to_email_id,
        )
    except SendError as exc:
        return {"error": str(exc)}
    finally:
        conn.close()
