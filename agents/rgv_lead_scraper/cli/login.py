"""``worklogicly-agent login`` — interactive Supabase password grant.

Reads ``CRM_BASE_URL`` and ``SUPABASE_ANON_KEY`` from the environment
(or from ``~/.worklogicly/agent.env`` if pre-populated), prompts for
email + password, and writes the resulting access/refresh pair to disk
via :class:`TokenStore.save_atomic`.
"""

from __future__ import annotations

import getpass
import os
import sys
import time
from typing import Optional

import httpx

from ..auth.token_store import Tokens, TokenStore


_ENV_HINT = (
    "Set CRM_BASE_URL and SUPABASE_ANON_KEY in your shell, or pre-create\n"
    "~/.worklogicly/agent.env with:\n"
    "    CRM_BASE_URL=https://<project>.supabase.co\n"
    "    SUPABASE_ANON_KEY=<anon key>\n"
)


def _bootstrap_env_from_file() -> None:
    """Best-effort: if the user already wrote ``CRM_BASE_URL`` /
    ``SUPABASE_ANON_KEY`` into the token file, surface them as env
    vars for this process. We never overwrite existing env values.
    """
    store = TokenStore()
    path = store.path
    if not path.exists():
        return
    try:
        from ..auth.token_store import _parse_env  # type: ignore[attr-defined]

        parsed = _parse_env(path.read_text(encoding="utf-8"))
    except Exception:
        return
    for key in ("CRM_BASE_URL", "SUPABASE_ANON_KEY"):
        if key in parsed and not os.environ.get(key):
            os.environ[key] = parsed[key]


def run_login(email: Optional[str] = None) -> int:
    _bootstrap_env_from_file()

    base_url = os.environ.get("CRM_BASE_URL", "").strip()
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not base_url or not anon_key:
        sys.stderr.write(
            "ERROR: CRM_BASE_URL and SUPABASE_ANON_KEY are required.\n\n"
            + _ENV_HINT
        )
        return 2

    if not email:
        try:
            email = input("CRM email: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.stderr.write("\nlogin cancelled\n")
            return 130
    if not email:
        sys.stderr.write("ERROR: email is required\n")
        return 2

    try:
        password = getpass.getpass("CRM password: ")
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\nlogin cancelled\n")
        return 130
    if not password:
        sys.stderr.write("ERROR: password is required\n")
        return 2

    url = f"{base_url.rstrip('/')}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
    }
    body = {"email": email, "password": password}

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        sys.stderr.write(f"ERROR: network failure talking to Supabase: {exc}\n")
        return 1

    if resp.status_code >= 400:
        try:
            payload = resp.json()
            detail = (
                payload.get("error_description")
                or payload.get("msg")
                or payload.get("error")
                or resp.text
            )
        except ValueError:
            detail = resp.text or f"HTTP {resp.status_code}"
        sys.stderr.write(f"ERROR: login failed ({resp.status_code}): {detail}\n")
        return 1

    try:
        data = resp.json()
        tokens = Tokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=int(time.time()) + int(data["expires_in"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f"ERROR: unexpected response from Supabase: {exc}\n")
        return 1

    store = TokenStore()
    try:
        store.save_atomic(tokens)
    except Exception as exc:
        sys.stderr.write(f"ERROR: could not write tokens to {store.path}: {exc}\n")
        return 1

    sys.stdout.write(f"Logged in. Tokens written to {store.path} (mode 0600).\n")
    return 0
