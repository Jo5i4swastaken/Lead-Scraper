"""Thin HTTP wrapper around the Supabase GoTrue ``/token`` endpoint.

Only the refresh-token grant is implemented here; the password grant
lives in ``cli/login.py`` because it has different error-surface
requirements (interactive prompt vs. background daemon).
"""

from __future__ import annotations

import time

import httpx

from .token_store import Tokens


class RefreshTokenExpired(Exception):
    """The refresh token itself was rejected.

    Surfaced by :class:`LocalRefreshTokenProvider` so callers can prompt
    the user to re-run ``worklogicly-agent login``. Distinct from
    transient network errors, which propagate as ``httpx`` exceptions.
    """


async def refresh(base_url: str, anon_key: str, refresh_token: str) -> Tokens:
    """Exchange ``refresh_token`` for a fresh access/refresh pair.

    Supabase rotates the refresh token on every call; the caller MUST
    persist the new pair before using the new access token.

    Args:
        base_url: Supabase project URL, e.g. ``https://abc.supabase.co``.
            Trailing slash is tolerated.
        anon_key: Project anon (publishable) key. GoTrue requires it on
            both ``apikey`` and ``Authorization: Bearer`` headers for
            the refresh-token grant.
        refresh_token: The opaque refresh token currently on disk.

    Returns:
        A :class:`Tokens` with ``expires_at`` already converted to an
        absolute epoch (Supabase returns ``expires_in`` relative).

    Raises:
        RefreshTokenExpired: on 400 or 401 (token rotation lost, or
            user logged out). The token file should be considered
            stale and the user prompted to re-authenticate.
        httpx.HTTPError: on transport-level failures (retryable).
        RuntimeError: if the response shape is unexpected.
    """
    url = f"{base_url.rstrip('/')}/auth/v1/token?grant_type=refresh_token"
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
    }
    body = {"refresh_token": refresh_token}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=body, headers=headers)

    if resp.status_code in (400, 401):
        # Try to surface the GoTrue error message in the exception
        # without leaking the refresh token itself.
        try:
            payload = resp.json()
            detail = payload.get("error_description") or payload.get("msg") or payload.get("error") or resp.text
        except ValueError:
            detail = resp.text or f"HTTP {resp.status_code}"
        raise RefreshTokenExpired(f"refresh rejected ({resp.status_code}): {detail}")

    if resp.status_code >= 400:
        raise RuntimeError(
            f"unexpected status from supabase refresh: {resp.status_code} {resp.text[:200]}"
        )

    try:
        data = resp.json()
        access_token = data["access_token"]
        new_refresh = data["refresh_token"]
        expires_in = int(data["expires_in"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"malformed refresh response: {exc}") from exc

    return Tokens(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_at=int(time.time()) + expires_in,
    )
