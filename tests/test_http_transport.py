"""HTTP transport: config defaults, token middleware, and app wiring."""

from __future__ import annotations

import json

import anyio

from mailintel import mcp_server
from mailintel.config import Config, HttpConfig
from mailintel.mcp_server import TokenAuthMiddleware, build_http_app


async def _ok_app(scope, receive, send):
    if scope["type"] == "http":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"inner-ok"})


def _request(app, scope):
    """Run one ASGI call and collect the response messages."""

    async def run():
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app(scope, receive, send)
        return messages

    return anyio.run(run)


def _http_scope(headers=()):
    return {"type": "http", "method": "POST", "path": "/mcp", "headers": list(headers)}


def test_http_config_defaults(monkeypatch):
    monkeypatch.delenv("MAILINTEL_MCP_TOKEN", raising=False)
    cfg = HttpConfig()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.auth_token is None
    monkeypatch.setenv("MAILINTEL_MCP_TOKEN", "s3cret")
    assert cfg.auth_token == "s3cret"


def test_middleware_rejects_missing_and_wrong_token():
    app = TokenAuthMiddleware(_ok_app, "s3cret")
    for headers in ((), ((b"x-mailintel-token", b"wrong"),)):
        messages = _request(app, _http_scope(headers))
        start, body = messages
        assert start["status"] == 200
        assert (b"content-type", b"application/json") in start["headers"]
        payload = json.loads(body["body"])
        assert payload["error"]["code"] == -32001
        assert payload["error"]["message"] == "unauthorized"


def test_middleware_accepts_correct_token():
    app = TokenAuthMiddleware(_ok_app, "s3cret")
    messages = _request(app, _http_scope(((b"x-mailintel-token", b"s3cret"),)))
    assert messages[-1]["body"] == b"inner-ok"


def test_middleware_passes_non_http_scopes_through():
    seen = []

    async def probe(scope, receive, send):
        seen.append(scope["type"])

    app = TokenAuthMiddleware(probe, "s3cret")
    _request(app, {"type": "lifespan"})
    assert seen == ["lifespan"]


def test_build_http_app_wraps_only_when_token_set(cfg, monkeypatch):
    monkeypatch.delenv("MAILINTEL_MCP_TOKEN", raising=False)
    assert not isinstance(build_http_app(cfg), TokenAuthMiddleware)
    monkeypatch.setenv("MAILINTEL_MCP_TOKEN", "s3cret")
    assert isinstance(build_http_app(cfg), TokenAuthMiddleware)


def test_main_dispatches_by_transport(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: calls.append("stdio"))
    monkeypatch.setattr(
        mcp_server, "run_http", lambda host=None, port=None: calls.append(("http", host, port))
    )
    mcp_server.main()
    mcp_server.main(transport="http", host="0.0.0.0", port=9000)
    assert calls == ["stdio", ("http", "0.0.0.0", 9000)]


def test_config_accepts_http_section():
    cfg = Config.model_validate({"http": {"host": "0.0.0.0", "port": 9000}})
    assert cfg.http.host == "0.0.0.0"
    assert cfg.http.port == 9000
