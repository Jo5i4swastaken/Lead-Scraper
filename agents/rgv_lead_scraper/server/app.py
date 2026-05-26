"""FastAPI entrypoint for hosted-mode lead-scraper agent.

Single ``/ws`` route. Each connection:

1. Authenticates via Supabase JWT presented as a WebSocket subprotocol
   (preferred) or ``?token=`` query param (fallback for tooling).
2. Binds that JWT to a :class:`contextvars.ContextVar` via
   :func:`jwt_scope` so :class:`ConnectionContextProvider` returns it
   when the ``request_lead_generation`` tool fires.
3. Delegates JSON-RPC message dispatch to OmniAgents'
   :class:`JsonRpcEndpoint`.

KNOWN CONSTRAINT — OmniAgents 0.6.53 single-tenancy
====================================================
The framework's :class:`AgentService` stores the "current connection"
on a single instance attribute (``self.channel``). Two concurrent
WebSockets would race on that attribute and emit each other's events
to the wrong client. We mitigate by serialising message dispatch
through ``_DISPATCH_LOCK`` — one in-flight message at a time across
the whole server.

This is fine for the current scale (single-digit admins per CRM, each
doing a request every few seconds) but is genuinely a "we should fix
this upstream" thing. The right long-term fix is either:
  (a) OmniAgents adds per-connection state (an explicit ``Channel``
      arg threaded through tool dispatch instead of ``self.channel``), or
  (b) we instantiate a fresh ``AgentService`` per connection. (b) is
      heavy — the service owns sessions, model state, retry policy, etc.

Until then, the lock keeps correctness at the cost of throughput we
don't yet need.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional, Tuple

from fastapi import FastAPI, WebSocket
from fastapi import WebSocketDisconnect

from omniagents.core.agents.service import AgentService
from omniagents.core.config.loader import load_agent_spec_from_yaml
from omniagents.rpc import JsonRpcEndpoint
from omniagents.rpc.server import JsonRpcChannel
from omniagents.rpc.transport.websocket import ServerWebSocketTransport
from omniagents.rpc.transport import (
    TransportClosedError,
    TransportDecodeError,
    TransportError,
)

from .connection_context import jwt_scope
from .ws_auth import InvalidJwtError, validate_supabase_jwt


logger = logging.getLogger("rgv_lead_scraper.server")

# Serialises JsonRpcEndpoint._process_message across ALL connections.
# See "KNOWN CONSTRAINT" in the module docstring.
_DISPATCH_LOCK = asyncio.Lock()


# WebSocket close codes (4xxx is the app-defined range per RFC 6455).
_CLOSE_UNAUTHORIZED = 4401
_CLOSE_INTERNAL = 1011


def _extract_subprotocol_token(websocket: WebSocket) -> Tuple[Optional[str], Optional[str]]:
    """Parse ``Sec-WebSocket-Protocol: bearer, <jwt>``.

    Returns ``(chosen_subprotocol, token)`` where ``chosen_subprotocol``
    is what we MUST echo back in ``websocket.accept(subprotocol=…)``
    so the browser's handshake succeeds. Returns ``(None, None)`` if
    the header is absent or malformed.

    Browsers reject the handshake if the server selects a subprotocol
    the client didn't offer. Per the CRM-side architect spec, the
    client offers exactly: ``bearer, <jwt>``. We respond with
    ``bearer`` (the first offered token) — never the JWT itself,
    which must not appear in response headers.
    """
    raw = websocket.headers.get("sec-websocket-protocol")
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) >= 2 and parts[0].lower() == "bearer":
        return parts[0], parts[1]
    return None, None


def _extract_query_token(websocket: WebSocket) -> Optional[str]:
    """Fallback: ``?token=…``. Convenient for ``wscat``/curl-style tests."""
    token = websocket.query_params.get("token")
    return token or None


async def _close_unauthorized(websocket: WebSocket, reason: str) -> None:
    """Reject before ``accept()``; logs the reason without leaking the token."""
    logger.info("rejecting WS connection: %s", reason)
    try:
        await websocket.close(code=_CLOSE_UNAUTHORIZED)
    except Exception:
        # Already closed / never opened — nothing useful we can do.
        pass


async def _process_message_locked(
    endpoint: JsonRpcEndpoint, channel: JsonRpcChannel, data: Any
) -> None:
    """Pin ``self.channel`` and dispatch one message under the lock.

    Re-setting ``self.methods.channel`` immediately before each call is
    redundant with ``_process_message`` (it does it again internally),
    but explicit here so the lock invariant is obvious and the
    cross-connection race is impossible: under the lock, no other
    coroutine can mutate ``self.methods.channel`` between this
    assignment and the dispatch.
    """
    async with _DISPATCH_LOCK:
        endpoint.methods.channel = channel
        await endpoint._process_message(channel, data)


async def _run_ws_session(
    endpoint: JsonRpcEndpoint, websocket: WebSocket, jwt: str
) -> None:
    """Per-connection message loop.

    Mirrors :meth:`JsonRpcEndpoint.register_route`'s inner ``handler``
    but adds the :func:`jwt_scope` wrapper around every dispatch so
    the tool layer can read ``CURRENT_JWT``.
    """
    transport = ServerWebSocketTransport(websocket)
    # transport.connect() does ``await websocket.accept()`` — we've
    # already accepted (so we could echo the subprotocol), so flip
    # the flag manually instead of double-accepting.
    transport._connected = True
    channel = JsonRpcChannel(transport)

    try:
        while transport.is_connected():
            try:
                data = await transport.receive_json()
            except (TransportClosedError, WebSocketDisconnect):
                break
            except TransportDecodeError as exc:
                await channel.send_error(
                    None, -32700, "Parse error", {"message": str(exc)}
                )
                continue
            except TransportError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("unexpected receive failure: %s", exc)
                break

            try:
                async with jwt_scope(jwt):
                    await _process_message_locked(endpoint, channel, data)
            except Exception as exc:  # pragma: no cover - dispatch errors land in send_error
                logger.exception("unexpected dispatch failure: %s", exc)
                break
    finally:
        try:
            if getattr(endpoint.methods, "channel", None) is channel:
                endpoint.methods.channel = None
        except AttributeError:
            pass
        try:
            await transport.disconnect()
        except Exception:
            pass


def build_app(
    *,
    agent_yml: Optional[str] = None,
    supabase_url: Optional[str] = None,
    supabase_anon_key: Optional[str] = None,
    default_workspace_root: Optional[str] = None,
) -> FastAPI:
    """Construct the FastAPI app. All args fall back to env vars.

    ``default_workspace_root`` is passed to ``AgentService`` so connecting
    clients don't have to include ``workspace_root`` in every ``start_run``
    payload (per the gotcha logged in Brain on 2026-05-22). The default
    points at a process-local tmp dir — the agent doesn't actually write
    much to disk; it just needs *a* valid path so the framework's
    resolution step doesn't raise.
    """
    yml_path = agent_yml or os.environ.get(
        "AGENT_YML",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "agent.yml",
        ),
    )
    supabase_url = supabase_url or os.environ.get("SUPABASE_URL") or os.environ.get(
        "CRM_BASE_URL"
    )
    supabase_anon_key = supabase_anon_key or os.environ.get("SUPABASE_ANON_KEY")
    workspace_root = default_workspace_root or os.environ.get(
        "WORKSPACE_ROOT", "/tmp/worklogicly-lead-agent"
    )

    if not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL (or CRM_BASE_URL) must be set for hosted mode"
        )
    if not supabase_anon_key:
        raise RuntimeError("SUPABASE_ANON_KEY must be set for hosted mode")

    # Make sure the workspace dir exists. AgentService doesn't create it.
    os.makedirs(workspace_root, exist_ok=True)

    spec = load_agent_spec_from_yaml(yml_path)
    service = AgentService(spec, default_workspace_root=workspace_root)
    endpoint = JsonRpcEndpoint(service)

    app = FastAPI(title="WorkLogicly Lead-Scraper Agent (hosted)")
    # Stash for tests / debug introspection.
    app.state.agent_service = service
    app.state.supabase_url = supabase_url
    app.state.supabase_anon_key = supabase_anon_key

    @app.get("/healthz")
    async def _healthz() -> dict:
        return {"ok": True, "mode": "hosted"}

    @app.websocket("/ws")
    async def _ws_endpoint(websocket: WebSocket) -> None:
        # Token extraction — subprotocol first, query param fallback.
        subprotocol, token = _extract_subprotocol_token(websocket)
        if not token:
            token = _extract_query_token(websocket)

        if not token:
            await _close_unauthorized(websocket, "no auth token presented")
            return

        try:
            user = await validate_supabase_jwt(token, supabase_url, supabase_anon_key)
        except InvalidJwtError as exc:
            await _close_unauthorized(websocket, f"jwt rejected: {exc.reason}")
            return

        # Accept with the chosen subprotocol echoed back (or no
        # subprotocol if we fell through to ?token=).
        try:
            if subprotocol:
                await websocket.accept(subprotocol=subprotocol)
            else:
                await websocket.accept()
        except Exception as exc:
            logger.exception("WS accept failed: %s", exc)
            return

        logger.info(
            "WS accepted for user %s (mode=subprotocol=%s)",
            user.get("id"),
            bool(subprotocol),
        )
        try:
            await _run_ws_session(endpoint, websocket, token)
        except Exception:
            logger.exception("WS session crashed")
            try:
                await websocket.close(code=_CLOSE_INTERNAL)
            except Exception:
                pass

    return app


def main() -> int:
    """Console-script entrypoint: ``worklogicly-agent-server``.

    Reads ``PORT`` (default 9494), ``HOST`` (default 0.0.0.0 because
    we run inside a container in production), and the env vars
    consumed by :func:`build_app`. Logging level honours
    ``LOG_LEVEL``.
    """
    import uvicorn

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = build_app()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "9494"))
    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info").lower())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
