"""MCP server facade for mailintel's knowledge-level email tools."""

# Tool imports intentionally follow the public registration order.
# ruff: noqa: I001

from __future__ import annotations

from .mcp_tools.runtime import mcp


# Tool modules import these shared objects and register their tools at import time.
from .mcp_tools.search import related_emails, search_emails, semantic_search  # noqa: E402, F401
from .mcp_tools.details import get_email, get_thread, read_attachment  # noqa: E402, F401
from .mcp_tools.mail import send_email  # noqa: E402, F401
from .mcp_tools.knowledge import (  # noqa: E402, F401
    daily_summary,
    find_action_items,
    find_decisions,
    find_waiting_replies,
    get_stats,
    list_folders,
    search_facts,
    search_threads,
    summarize_sender,
    sync_now,
)
from .mcp_tools.agent_loop import (  # noqa: E402, F401
    add_email_note,
    complete_action_item,
    get_events_since,
    list_tags,
    set_importance,
    tag_email,
    untag_email,
)
from .mcp_tools.drafts import (  # noqa: E402, F401
    create_draft,
    delete_draft,
    list_contacts,
    list_drafts,
    scan_email_mcp,
    send_draft,
    update_contact_tier,
    update_draft,
)
from .mcp_tools.http import (  # noqa: E402, F401
    ASGIApp,
    AUTH_HEADER,
    TokenAuthMiddleware,
    build_http_app,
    run_http,
)


def main(transport: str = "stdio", host: str | None = None, port: int | None = None) -> None:
    """Run the MCP server using stdio or the guarded HTTP transport."""
    if transport == "http":
        run_http(host=host, port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
