"""Hosted-mode :class:`JwtProvider` backed by per-connection ContextVar.

Reads :data:`rgv_lead_scraper.server.connection_context.CURRENT_JWT`
which the WS dispatch path binds inside :func:`jwt_scope` before
delegating to OmniAgents. The tool layer doesn't need to know whether
it's running local or hosted — both providers satisfy the same
:class:`JwtProvider` Protocol.

Refresh semantics differ from local mode. The hosted agent does NOT
hold a refresh token; the browser owns it (and rotates it via
``supabase-js``). On a 401 we ask the user to reconnect rather than
silently rotating — they'll come back in with a fresh JWT.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..server.connection_context import get_current_jwt


logger = logging.getLogger(__name__)


class ConnectionContextProvider:
    """Implements :class:`JwtProvider` against the WS-scoped ContextVar."""

    async def get_jwt(self) -> str:
        # Raises NoJwtInScopeError if called outside a jwt_scope —
        # surfaced upward; the agent's RPC layer turns it into an error
        # event the client will display.
        return get_current_jwt()

    async def refresh_on_401(self) -> Optional[str]:
        # The hosted agent can't refresh — the browser holds the refresh
        # token. Returning None makes ``request_lead_generation`` surface
        # the structured "auth_required" message, which the CRM client
        # handles by tearing down the WebSocket and reconnecting with a
        # freshly minted access token from supabase-js.
        logger.warning(
            "refresh_on_401 called in hosted mode — instructing client to reconnect"
        )
        return None
