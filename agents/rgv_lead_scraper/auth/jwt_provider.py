"""Protocol shared by local and hosted JWT providers.

Step 1 only ships the ``local`` implementation (refresh-token grant
against a file on disk). Step 3 will add a ``hosted`` implementation
backed by a per-connection context. The agent's tool code depends only
on this Protocol so neither side leaks into the other.
"""

from __future__ import annotations

import os
from typing import Literal, Optional, Protocol, runtime_checkable


@runtime_checkable
class JwtProvider(Protocol):
    """A source of Supabase user JWTs for outgoing edge-function calls.

    Implementations MUST be safe to call from multiple concurrent
    coroutines (the agent can fan out tool calls).
    """

    async def get_jwt(self) -> str:
        """Return a valid access token, refreshing proactively if it
        is within the skew window of expiry."""
        ...

    async def refresh_on_401(self) -> Optional[str]:
        """Force a refresh in response to a 401 from the API.

        Returns:
            A new access token on success, or ``None`` when the
            refresh token itself is no longer accepted (the user needs
            to re-authenticate). Callers should surface the ``None``
            case to the user verbatim — do NOT retry past this point.
        """
        ...


Mode = Literal["local", "hosted"]


def build_provider(mode: Mode | str | None = None) -> JwtProvider:
    """Factory keyed off ``AGENT_MODE`` (default ``"local"``).

    The ``"hosted"`` branch is a deliberate ``NotImplementedError`` so
    misconfigured environments fail loudly instead of silently falling
    through to local-mode credentials they don't have.
    """
    resolved = (mode or os.environ.get("AGENT_MODE") or "local").lower()
    if resolved == "local":
        # Late import to avoid pulling httpx into hosted-only contexts
        # once step 3 introduces a leaner build.
        from .local_provider import LocalRefreshTokenProvider

        return LocalRefreshTokenProvider()
    if resolved == "hosted":
        # Late import: the connection provider pulls in the server
        # package (and therefore FastAPI). Local-only deployments
        # shouldn't pay that import cost just to construct a provider.
        from .connection_provider import ConnectionContextProvider

        return ConnectionContextProvider()
    raise ValueError(f"unknown AGENT_MODE={resolved!r}; expected 'local' or 'hosted'")
