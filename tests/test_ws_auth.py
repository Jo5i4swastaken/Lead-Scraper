"""Tests for :mod:`rgv_lead_scraper.server.ws_auth`.

Network is mocked at the httpx layer — we never hit Supabase.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable

import httpx
import pytest

from rgv_lead_scraper.server import ws_auth


def _run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    ws_auth._clear_cache_for_tests()
    yield
    ws_auth._clear_cache_for_tests()


def _mock_client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def test_returns_user_on_200(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "user-1", "email": "a@b"})

    client = _mock_client(handler)
    try:
        user = _run(
            ws_auth.validate_supabase_jwt(
                "good-token",
                "https://test.supabase.co",
                "anon-key",
                client=client,
            )
        )
    finally:
        _run(client.aclose())

    assert user == {"id": "user-1", "email": "a@b"}
    assert len(calls) == 1
    req = calls[0]
    assert req.url.path == "/auth/v1/user"
    assert req.headers["authorization"] == "Bearer good-token"
    assert req.headers["apikey"] == "anon-key"


def test_raises_on_401(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad token"})

    client = _mock_client(handler)
    try:
        with pytest.raises(ws_auth.InvalidJwtError) as exc_info:
            _run(
                ws_auth.validate_supabase_jwt(
                    "bad-token", "https://test.supabase.co", "anon-key", client=client
                )
            )
    finally:
        _run(client.aclose())
    assert "401" in str(exc_info.value)


def test_raises_on_missing_token():
    with pytest.raises(ws_auth.InvalidJwtError) as exc_info:
        _run(
            ws_auth.validate_supabase_jwt(
                "", "https://test.supabase.co", "anon-key"
            )
        )
    assert "missing" in str(exc_info.value).lower()


def test_raises_when_payload_lacks_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"email": "no-id@example.com"})

    client = _mock_client(handler)
    try:
        with pytest.raises(ws_auth.InvalidJwtError) as exc_info:
            _run(
                ws_auth.validate_supabase_jwt(
                    "weird-token",
                    "https://test.supabase.co",
                    "anon-key",
                    client=client,
                )
            )
    finally:
        _run(client.aclose())
    assert "id" in str(exc_info.value).lower()


def test_cache_hits_second_call(monkeypatch):
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"id": "user-cached"})

    client = _mock_client(handler)
    try:
        u1 = _run(
            ws_auth.validate_supabase_jwt(
                "cache-me", "https://test.supabase.co", "anon", client=client
            )
        )
        u2 = _run(
            ws_auth.validate_supabase_jwt(
                "cache-me", "https://test.supabase.co", "anon", client=client
            )
        )
    finally:
        _run(client.aclose())

    assert u1 == u2 == {"id": "user-cached"}
    # Cache short-circuited — only one network call.
    assert call_count["n"] == 1


def test_different_tokens_dont_share_cache():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        token = request.headers["authorization"].split(" ", 1)[1]
        return httpx.Response(200, json={"id": f"u-{token}"})

    client = _mock_client(handler)
    try:
        u_a = _run(
            ws_auth.validate_supabase_jwt(
                "tok-a", "https://test.supabase.co", "anon", client=client
            )
        )
        u_b = _run(
            ws_auth.validate_supabase_jwt(
                "tok-b", "https://test.supabase.co", "anon", client=client
            )
        )
    finally:
        _run(client.aclose())

    assert u_a == {"id": "u-tok-a"}
    assert u_b == {"id": "u-tok-b"}
    assert call_count["n"] == 2
