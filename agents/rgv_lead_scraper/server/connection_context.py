"""Per-WebSocket-connection JWT isolation via :class:`contextvars.ContextVar`.

Why a ContextVar instead of an attribute on a per-request provider:
the tool functions in :mod:`rgv_lead_scraper.tools.lead_tools` are
discovered by OmniAgents at module load and bind the module-level
``_provider`` singleton. Rebuilding that wiring per request would
mean editing the tool layer just so hosted-mode can plumb identity
through. Instead, the singleton provider becomes a thin reader of
this ContextVar, set by the WS dispatch path before each message.

ContextVars are propagated correctly across ``await`` boundaries and
``asyncio.Task`` creation when ``Task.copy_current_context`` is used
(which asyncio does by default for tasks created from within a
coroutine), so concurrent connections see their own value as long as
the dispatch handler enters :func:`jwt_scope` before awaiting any
agent work.
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import AsyncIterator, Optional


# Default ``None`` (not unset) so reading from a thread that never
# entered a scope returns ``None`` rather than raising LookupError.
# :func:`get_current_jwt` enforces the "must be inside a scope"
# invariant explicitly so the failure message names the bug.
CURRENT_JWT: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "rgv_lead_scraper_current_jwt", default=None
)


class NoJwtInScopeError(RuntimeError):
    """Raised when a tool reads the current JWT outside a :func:`jwt_scope`.

    This is *always* a bug in the host wiring — every code path that
    can reach a tool must have entered a scope first. We raise loudly
    instead of silently returning an empty string so the failure
    shows up in the agent's error event rather than as a 401 from the
    edge function (which would be misleading).
    """


@contextlib.asynccontextmanager
async def jwt_scope(jwt: str) -> AsyncIterator[None]:
    """Bind ``jwt`` as the current connection's identity for the duration
    of the ``async with`` block.

    Restores the previous value on exit (correct in the rare case of
    nested scopes — e.g. a sub-task that also enters one).
    """
    token = CURRENT_JWT.set(jwt)
    try:
        yield
    finally:
        CURRENT_JWT.reset(token)


def get_current_jwt() -> str:
    """Return the JWT bound by the enclosing :func:`jwt_scope`.

    Raises :class:`NoJwtInScopeError` if called outside any scope —
    that case indicates a wiring bug, not a credential problem.
    """
    value = CURRENT_JWT.get()
    if not value:
        raise NoJwtInScopeError(
            "no JWT in scope; tool was invoked outside an active "
            "WebSocket request — check the server dispatch wiring"
        )
    return value
