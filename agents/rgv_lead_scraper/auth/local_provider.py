"""Local-mode :class:`JwtProvider` backed by a refresh token on disk.

Two refresh paths exist and BOTH are required:

* **Proactive** (``get_jwt``): if the cached access token is within
  ``_SKEW_SECONDS`` of expiry we refresh before making the call. Cheap
  insurance against clock skew and slow-network refresh races.
* **Reactive** (``refresh_on_401``): if the edge function still returns
  401 (e.g. JWT was revoked server-side), we refresh once and retry. A
  second 401 is treated as terminal — the caller surfaces it.

All refresh attempts serialise through an ``asyncio.Lock`` so concurrent
tool calls cannot stampede the GoTrue endpoint or race on the file
write. The rotated refresh token is persisted via ``save_atomic``
BEFORE the new access token is handed out, so a crash between the
refresh response and the next call cannot leave the file pointing at a
revoked token.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

from .supabase_auth import RefreshTokenExpired, refresh
from .token_store import Tokens, TokenStore, TokenStoreEmpty

_SKEW_SECONDS = 60


class LocalRefreshTokenProvider:
    """Implements :class:`JwtProvider` against an on-disk token file."""

    def __init__(
        self,
        store: Optional[TokenStore] = None,
        base_url: Optional[str] = None,
        anon_key: Optional[str] = None,
    ) -> None:
        self._store = store or TokenStore()
        # These can be lazily read on first use so test setups can
        # patch the env after construction.
        self._base_url = base_url
        self._anon_key = anon_key
        self._lock = asyncio.Lock()
        self._cached: Optional[Tokens] = None

    # ------------------------------------------------------------------
    # JwtProvider Protocol
    # ------------------------------------------------------------------

    async def get_jwt(self) -> str:
        tokens = self._load_cached()
        if self._needs_refresh(tokens):
            tokens = await self._refresh_locked(tokens)
        return tokens.access_token

    async def refresh_on_401(self) -> Optional[str]:
        tokens = self._load_cached()
        try:
            tokens = await self._refresh_locked(tokens, force=True)
        except RefreshTokenExpired:
            return None
        return tokens.access_token

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _load_cached(self) -> Tokens:
        if self._cached is None:
            try:
                self._cached = self._store.load()
            except TokenStoreEmpty as exc:
                # No tokens at all = same terminal state as a rejected
                # refresh; surface via the same exception so callers
                # have one branch to handle.
                raise RefreshTokenExpired(str(exc)) from exc
        return self._cached

    def _needs_refresh(self, tokens: Tokens) -> bool:
        return int(time.time()) >= tokens.expires_at - _SKEW_SECONDS

    async def _refresh_locked(self, tokens: Tokens, *, force: bool = False) -> Tokens:
        async with self._lock:
            # Re-check inside the lock — a concurrent caller may have
            # already refreshed while we were waiting.
            current = self._cached or tokens
            if not force and not self._needs_refresh(current):
                return current

            base_url = self._resolve_base_url()
            anon_key = self._resolve_anon_key()
            new_tokens = await refresh(base_url, anon_key, current.refresh_token)
            # Persist BEFORE we hand the new access token to the caller.
            # If we crash here, the on-disk refresh token still matches
            # what we just exchanged for — the next start will refresh
            # cleanly. If we persisted AFTER use, a crash could leave
            # the file pointing at a revoked refresh token.
            self._store.save_atomic(new_tokens)
            self._cached = new_tokens
            return new_tokens

    def _resolve_base_url(self) -> str:
        url = self._base_url or os.environ.get("CRM_BASE_URL", "")
        if not url:
            raise RuntimeError(
                "CRM_BASE_URL is not set; the agent cannot refresh its JWT"
            )
        return url

    def _resolve_anon_key(self) -> str:
        key = self._anon_key or os.environ.get("SUPABASE_ANON_KEY", "")
        if not key:
            raise RuntimeError(
                "SUPABASE_ANON_KEY is not set; required for the Supabase "
                "refresh-token grant"
            )
        return key

    # Test/debug introspection — never log the tokens themselves.
    def expires_in_seconds(self) -> Optional[int]:
        try:
            tokens = self._load_cached()
        except RefreshTokenExpired:
            return None
        return max(0, tokens.expires_at - int(time.time()))

    def has_refresh_token(self) -> bool:
        try:
            tokens = self._load_cached()
        except RefreshTokenExpired:
            return False
        return bool(tokens.refresh_token)
