"""End-to-end-ish integration tests for the hosted FastAPI server.

We stub at the boundaries that matter:
  * ``validate_supabase_jwt`` — accept ``good-token``, reject everything else.
  * ``AgentService`` construction — substituted with a tiny RpcMethodsBase
    subclass that exposes a single ``echo`` method. We don't load the real
    agent spec because that would pull in OpenAI keys, sub-agent skills,
    tool discovery, etc., none of which exist in CI.

What this test PROVES:
  * Subprotocol-based auth handshake works (``bearer, <jwt>``).
  * ?token=… fallback works.
  * Missing token closes the WS with 4401.
  * Bad token closes the WS with 4401.
  * After accept, JSON-RPC dispatch flows through ``_run_ws_session``
    AND the JWT is bound in the ContextVar during dispatch.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from omniagents.rpc import JsonRpcEndpoint
from starlette.websockets import WebSocketDisconnect

from rgv_lead_scraper.server import app as app_mod
from rgv_lead_scraper.server import ws_auth
from rgv_lead_scraper.server.connection_context import get_current_jwt


# ---------------------------------------------------------------------------
# Fake AgentService — a single ``echo`` method that captures the JWT seen
# from the ContextVar so we can assert per-request identity binding.
# ---------------------------------------------------------------------------


class _FakeMethods:
    """Minimal RpcMethodsBase substitute.

    OmniAgents' :class:`JsonRpcEndpoint` only requires the methods
    object to (a) expose callable attributes for RPC methods and (b)
    accept a ``channel`` attribute. We don't subclass RpcMethodsBase
    because importing the real one pulls heavy deps.
    """

    def __init__(self) -> None:
        self.channel: Optional[Any] = None
        self.seen_jwts: list[str] = []

    async def echo(self, message: str = "") -> dict:
        # Capture the current connection's JWT — proves the scope is
        # active during dispatch.
        self.seen_jwts.append(get_current_jwt())
        return {"echoed": message, "jwt_in_scope": True}


@pytest.fixture(autouse=True)
def _clear_ws_auth_cache():
    ws_auth._clear_cache_for_tests()
    yield
    ws_auth._clear_cache_for_tests()


@pytest.fixture
def app_and_methods(monkeypatch):
    """Build a FastAPI app with our fake methods and stubbed JWT validation."""
    methods = _FakeMethods()
    endpoint = JsonRpcEndpoint(methods)

    async def fake_validate(jwt, supabase_url, anon_key, *, client=None):
        if jwt == "good-token":
            return {"id": "user-1", "email": "good@example.com"}
        raise ws_auth.InvalidJwtError("bad token")

    monkeypatch.setattr(app_mod, "validate_supabase_jwt", fake_validate)

    # Build a stripped-down app inline so we don't need a real
    # agent.yml. Mirrors build_app's WS handler exactly.
    app = FastAPI()

    @app.websocket("/ws")
    async def _ws(websocket: WebSocket):
        subprotocol, token = app_mod._extract_subprotocol_token(websocket)
        if not token:
            token = app_mod._extract_query_token(websocket)
        if not token:
            await app_mod._close_unauthorized(websocket, "no token")
            return
        try:
            await fake_validate(token, "https://x", "anon")
        except ws_auth.InvalidJwtError as exc:
            await app_mod._close_unauthorized(websocket, exc.reason)
            return
        if subprotocol:
            await websocket.accept(subprotocol=subprotocol)
        else:
            await websocket.accept()
        await app_mod._run_ws_session(endpoint, websocket, token)

    return app, methods


def test_no_token_closes_4401(app_and_methods):
    app, _methods = app_and_methods
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws") as ws:
                ws.receive_text()
    assert exc_info.value.code == 4401


def test_bad_token_closes_4401(app_and_methods):
    app, _methods = app_and_methods
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/ws", subprotocols=["bearer", "wrong-token"]
            ) as ws:
                ws.receive_text()
    assert exc_info.value.code == 4401


def test_subprotocol_auth_accepts_and_dispatches(app_and_methods):
    app, methods = app_and_methods
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws", subprotocols=["bearer", "good-token"]
        ) as ws:
            ws.send_text(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "echo",
                        "params": {"message": "hello"},
                    }
                )
            )
            reply = json.loads(ws.receive_text())

    assert reply["id"] == 1
    assert reply["result"]["echoed"] == "hello"
    assert reply["result"]["jwt_in_scope"] is True
    # Critical: the captured JWT during dispatch matches the connection's token.
    assert methods.seen_jwts == ["good-token"]


def test_query_param_fallback_accepts(app_and_methods):
    app, methods = app_and_methods
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=good-token") as ws:
            ws.send_text(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "echo",
                        "params": {"message": "via-query"},
                    }
                )
            )
            reply = json.loads(ws.receive_text())

    assert reply["id"] == 7
    assert reply["result"]["echoed"] == "via-query"
    assert methods.seen_jwts == ["good-token"]
