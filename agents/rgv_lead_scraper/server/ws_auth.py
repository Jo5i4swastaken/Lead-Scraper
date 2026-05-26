"""Validate Supabase user JWTs presented by WebSocket clients.

We deliberately do NOT verify the JWT signature locally with the
project's JWT secret. Two reasons:

1. The signing secret is a project-level secret and should not live
   on the agent host (rotating it would require a redeploy of the
   agent in addition to Supabase). The anon key + ``/auth/v1/user``
   already gives us authoritative validation.
2. ``GET {url}/auth/v1/user`` checks revocation too — a JWT that has
   been invalidated server-side (logout, password rotation) fails,
   which a local-only signature check would miss.

A small TTL cache softens the network cost: multiple rapid messages
on the same connection don't re-hit Supabase. The cache key is a
SHA-256 of the JWT, not the JWT itself, so it never leaks into a
debugger / repr.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional, Tuple

import httpx


_CACHE_TTL_SECONDS = 60
_CACHE_MAX_ENTRIES = 256


class InvalidJwtError(Exception):
    """Raised when Supabase rejects the JWT or returns an unexpected shape."""

    def __init__(self, reason: str = "invalid token") -> None:
        super().__init__(reason)
        self.reason = reason


# Tiny hand-rolled LRU-with-TTL. cachetools would add a dep for one
# 30-line need; this keeps the wheel small. Key = sha256(jwt) hex.
# Value = (expires_at, user_dict).
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _hash_jwt(jwt: str) -> str:
    return hashlib.sha256(jwt.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    entry = _cache.get(key)
    if entry is None:
        return None
    expires_at, user = entry
    if time.monotonic() >= expires_at:
        # Lazy expiry — drop and miss.
        _cache.pop(key, None)
        return None
    return user


def _cache_put(key: str, user: Dict[str, Any]) -> None:
    # Crude bounded-size eviction: drop the oldest entry once we're
    # over the cap. Fine for our scale (single-digit concurrent users).
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        try:
            oldest_key = min(_cache, key=lambda k: _cache[k][0])
            _cache.pop(oldest_key, None)
        except ValueError:
            pass
    _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, user)


def _clear_cache_for_tests() -> None:
    """Reset cache state — only used by tests."""
    _cache.clear()


async def validate_supabase_jwt(
    jwt: str,
    supabase_url: str,
    anon_key: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Resolve ``jwt`` to the authoritative Supabase user object.

    Returns the parsed user dict on success. Raises
    :class:`InvalidJwtError` for missing tokens, network failures, or
    non-2xx responses from Supabase. The caller turns the exception
    into a WebSocket close code (4401).
    """
    if not jwt:
        raise InvalidJwtError("missing token")

    cache_key = _hash_jwt(jwt)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "apikey": anon_key,
    }

    # Allow tests to inject a client; in production we create one per
    # call — connections to the GoTrue endpoint are cheap and we
    # avoid leaking a long-lived client into module state.
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        try:
            resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise InvalidJwtError(f"network error contacting Supabase: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if resp.status_code != 200:
        # Don't include the body — it can echo the bearer for debug
        # purposes on some GoTrue versions.
        raise InvalidJwtError(f"Supabase rejected token (HTTP {resp.status_code})")

    try:
        user = resp.json()
    except ValueError as exc:
        raise InvalidJwtError("Supabase returned non-JSON user payload") from exc

    if not isinstance(user, dict) or not user.get("id"):
        raise InvalidJwtError("Supabase user payload missing id")

    _cache_put(cache_key, user)
    return user
