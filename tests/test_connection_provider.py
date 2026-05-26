"""Tests for :class:`ConnectionContextProvider` + ContextVar isolation.

Critical invariant: two concurrent asyncio tasks each in their own
``jwt_scope`` MUST see their own JWT. Anything else is a per-tenant
data leak in hosted mode.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable

import pytest

from rgv_lead_scraper.auth.connection_provider import ConnectionContextProvider
from rgv_lead_scraper.auth.jwt_provider import build_provider
from rgv_lead_scraper.server.connection_context import (
    NoJwtInScopeError,
    get_current_jwt,
    jwt_scope,
)


def _run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


def test_get_jwt_inside_scope_returns_value():
    async def _go():
        async with jwt_scope("inside-token"):
            assert get_current_jwt() == "inside-token"
            return await ConnectionContextProvider().get_jwt()

    assert _run(_go()) == "inside-token"


def test_get_jwt_outside_scope_raises():
    async def _go():
        await ConnectionContextProvider().get_jwt()

    with pytest.raises(NoJwtInScopeError):
        _run(_go())


def test_concurrent_tasks_see_isolated_jwts():
    """ContextVar must not leak across asyncio tasks."""
    provider = ConnectionContextProvider()
    started_a = asyncio.Event()
    started_b = asyncio.Event()
    proceed = asyncio.Event()

    async def worker(jwt: str, started: asyncio.Event) -> str:
        async with jwt_scope(jwt):
            started.set()
            # Yield long enough for BOTH workers to be inside their
            # scopes simultaneously — proves ContextVar is per-task.
            await proceed.wait()
            return await provider.get_jwt()

    async def driver():
        task_a = asyncio.create_task(worker("token-A", started_a))
        task_b = asyncio.create_task(worker("token-B", started_b))
        await started_a.wait()
        await started_b.wait()
        proceed.set()
        return await asyncio.gather(task_a, task_b)

    a, b = _run(driver())
    assert a == "token-A"
    assert b == "token-B"


def test_nested_scope_restores_outer_on_exit():
    async def _go():
        async with jwt_scope("outer"):
            async with jwt_scope("inner"):
                assert get_current_jwt() == "inner"
            assert get_current_jwt() == "outer"

    _run(_go())


def test_refresh_on_401_returns_none():
    """Hosted mode delegates refresh to the browser; provider says 'reconnect'."""

    async def _go():
        return await ConnectionContextProvider().refresh_on_401()

    assert _run(_go()) is None


def test_build_provider_hosted_returns_connection_context_provider():
    provider = build_provider("hosted")
    assert type(provider).__name__ == "ConnectionContextProvider"
