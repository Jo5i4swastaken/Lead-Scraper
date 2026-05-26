"""Authentication providers for the lead-scraper agent.

Step 1 ships a ``local`` mode that refreshes a Supabase user JWT from
disk. A future ``hosted`` mode (step 3) will pull tokens from a
per-connection context. Both implement :class:`JwtProvider`.
"""

from .jwt_provider import JwtProvider, build_provider
from .local_provider import LocalRefreshTokenProvider
from .supabase_auth import RefreshTokenExpired, refresh
from .token_store import Tokens, TokenStore, TokenStoreEmpty

__all__ = [
    "JwtProvider",
    "LocalRefreshTokenProvider",
    "RefreshTokenExpired",
    "TokenStore",
    "TokenStoreEmpty",
    "Tokens",
    "build_provider",
    "refresh",
]
