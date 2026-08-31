"""Streamable HTTP transport and shared-token middleware."""

from __future__ import annotations

import json
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from ..config import Config
from .runtime import get_config, mcp

ASGIApp = Callable[[dict, Callable, Callable], Awaitable[None]]
AUTH_HEADER = b"x-mailintel-token"
_UNAUTHORIZED_BODY = json.dumps(
    {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "unauthorized"}}
).encode()


class TokenAuthMiddleware:
    """Pure-ASGI shared-token guard for the HTTP transport."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        got = headers.get(AUTH_HEADER, b"").decode("utf-8", "replace")
        if got != self.token:
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})
            return
        await self.app(scope, receive, send)


def build_http_app(cfg: Config) -> ASGIApp:
    """Build the FastMCP HTTP app and wrap it when a token is configured."""
    app: ASGIApp = mcp.streamable_http_app()
    token = cfg.http.auth_token
    if token:
        app = TokenAuthMiddleware(app, token)
    return app


def run_http(host: str | None = None, port: int | None = None) -> None:
    """Run the configured Streamable HTTP MCP server."""
    import uvicorn

    cfg = get_config()
    bind_host = host or cfg.http.host
    bind_port = port or cfg.http.port
    if not cfg.http.auth_token:
        if bind_host not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError(
                "Refusing unauthenticated MCP HTTP binding outside localhost; "
                "set MAILINTEL_MCP_TOKEN before using a public bind host"
            )
        print("mailintel MCP HTTP: no auth token configured (trusted localhost only)", file=sys.stderr)
    app: Any = build_http_app(cfg)
    uvicorn.run(app, host=bind_host, port=bind_port, timeout_keep_alive=60)
