"""Unit tests for :class:`LocalRefreshTokenProvider`.

All HTTP is mocked at the ``supabase_auth.refresh`` boundary so the
tests never touch the network. ``asyncio.run`` is used directly rather
than ``pytest-asyncio`` to avoid adding a dev dependency for a handful
of test cases.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, List

import pytest

from rgv_lead_scraper.auth import local_provider as lp_mod
from rgv_lead_scraper.auth.local_provider import LocalRefreshTokenProvider
from rgv_lead_scraper.auth.supabase_auth import RefreshTokenExpired
from rgv_lead_scraper.auth.token_store import Tokens, TokenStore


def _run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


def _store_with(tmp_path: Path, tokens: Tokens) -> TokenStore:
    store = TokenStore(tmp_path / "agent.env")
    store.save_atomic(tokens)
    return store


def _provider(store: TokenStore) -> LocalRefreshTokenProvider:
    return LocalRefreshTokenProvider(
        store=store, base_url="https://test.supabase.co", anon_key="anon"
    )


def test_returns_cached_token_when_not_near_expiry(tmp_path, monkeypatch):
    future = int(time.time()) + 3600
    store = _store_with(tmp_path, Tokens("cached.jwt", "r-1", future))
    provider = _provider(store)

    async def fake_refresh(*args, **kwargs):  # pragma: no cover
        raise AssertionError("should not refresh when not near expiry")

    monkeypatch.setattr(lp_mod, "refresh", fake_refresh)

    jwt = _run(provider.get_jwt())
    assert jwt == "cached.jwt"


def test_refreshes_proactively_when_within_skew(tmp_path, monkeypatch):
    soon = int(time.time()) + 10  # within the 60s skew window
    store = _store_with(tmp_path, Tokens("old.jwt", "r-old", soon))
    provider = _provider(store)

    new = Tokens("new.jwt", "r-new", int(time.time()) + 3600)

    async def fake_refresh(base_url, anon_key, refresh_token):
        assert base_url == "https://test.supabase.co"
        assert anon_key == "anon"
        assert refresh_token == "r-old"
        return new

    monkeypatch.setattr(lp_mod, "refresh", fake_refresh)

    jwt = _run(provider.get_jwt())
    assert jwt == "new.jwt"
    # Rotated tokens were persisted before being handed out.
    assert store.load() == new


def test_refresh_on_401_forces_refresh(tmp_path, monkeypatch):
    future = int(time.time()) + 3600  # NOT near expiry
    store = _store_with(tmp_path, Tokens("old.jwt", "r-old", future))
    provider = _provider(store)

    new = Tokens("post-401.jwt", "r-new", int(time.time()) + 3600)
    calls: List[str] = []

    async def fake_refresh(base_url, anon_key, refresh_token):
        calls.append(refresh_token)
        return new

    monkeypatch.setattr(lp_mod, "refresh", fake_refresh)

    out = _run(provider.refresh_on_401())
    assert out == "post-401.jwt"
    assert calls == ["r-old"]
    assert store.load() == new


def test_refresh_on_401_returns_none_when_refresh_token_expired(tmp_path, monkeypatch):
    future = int(time.time()) + 3600
    store = _store_with(tmp_path, Tokens("old.jwt", "r-dead", future))
    provider = _provider(store)

    async def fake_refresh(*args, **kwargs):
        raise RefreshTokenExpired("token revoked")

    monkeypatch.setattr(lp_mod, "refresh", fake_refresh)

    assert _run(provider.refresh_on_401()) is None


def test_get_jwt_raises_when_no_tokens_on_disk(tmp_path):
    store = TokenStore(tmp_path / "agent.env")
    provider = _provider(store)
    with pytest.raises(RefreshTokenExpired):
        _run(provider.get_jwt())


def test_concurrent_get_jwt_serialises_through_lock(tmp_path, monkeypatch):
    """Two concurrent ``get_jwt`` calls during a needed refresh must
    result in exactly one refresh call, not a race.
    """
    soon = int(time.time()) + 10
    store = _store_with(tmp_path, Tokens("old.jwt", "r-old", soon))
    provider = _provider(store)

    new = Tokens("new.jwt", "r-new", int(time.time()) + 3600)

    state = {"count": 0}

    async def run_both():
        started = asyncio.Event()
        release = asyncio.Event()

        async def fake_refresh(*args, **kwargs):
            state["count"] += 1
            started.set()
            await release.wait()
            return new

        monkeypatch.setattr(lp_mod, "refresh", fake_refresh)

        task_a = asyncio.create_task(provider.get_jwt())
        await started.wait()
        task_b = asyncio.create_task(provider.get_jwt())
        # Let task_b reach the lock.
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(task_a, task_b)

    jwt_a, jwt_b = _run(run_both())
    assert jwt_a == jwt_b == "new.jwt"
    assert state["count"] == 1, "lock should serialise concurrent refreshes"
