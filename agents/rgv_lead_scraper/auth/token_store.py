"""Atomic on-disk store for the Supabase refresh-token pair.

Layout of the env file (``~/.worklogicly/agent.env`` by default)::

    CRM_ACCESS_TOKEN=eyJhbGciOi...
    CRM_REFRESH_TOKEN=opaque-string
    CRM_ACCESS_TOKEN_EXPIRES_AT=1715619200

Writes go via ``<path>.tmp`` + ``os.replace`` so a crash mid-write
cannot leave a half-written file that bricks the agent. Permissions are
forced to 0600 because the refresh token is a long-lived credential.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path.home() / ".worklogicly" / "agent.env"
_ENV_PATH_OVERRIDE = "WORKLOGICLY_AGENT_ENV"

_ACCESS_KEY = "CRM_ACCESS_TOKEN"
_REFRESH_KEY = "CRM_REFRESH_TOKEN"
_EXPIRES_KEY = "CRM_ACCESS_TOKEN_EXPIRES_AT"
_MANAGED_KEYS = frozenset({_ACCESS_KEY, _REFRESH_KEY, _EXPIRES_KEY})


class TokenStoreEmpty(Exception):
    """Raised by :meth:`TokenStore.load` when no tokens are on disk yet.

    The CLI surfaces this as "run ``worklogicly-agent login``".
    """


@dataclass(frozen=True)
class Tokens:
    """A Supabase access/refresh pair plus the absolute expiry."""

    access_token: str
    refresh_token: str
    expires_at: int  # epoch seconds


def _parse_env(text: str) -> dict[str, str]:
    """Tiny ``KEY=value`` parser. Strips surrounding quotes and ignores
    comments / blank lines. Deliberately not python-dotenv to keep the
    dependency surface small for the agent runtime."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def _serialise(tokens: Tokens, extra: dict[str, str] | None = None) -> str:
    lines = [
        f"{_ACCESS_KEY}={tokens.access_token}",
        f"{_REFRESH_KEY}={tokens.refresh_token}",
        f"{_EXPIRES_KEY}={tokens.expires_at}",
    ]
    if extra:
        for key, value in extra.items():
            if key in _MANAGED_KEYS:
                continue
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


class TokenStore:
    """File-backed store. Cheap to instantiate; safe to share."""

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            override = os.environ.get(_ENV_PATH_OVERRIDE)
            path = override if override else DEFAULT_PATH
        self._path = Path(path).expanduser()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Tokens:
        """Return tokens from disk.

        Raises:
            TokenStoreEmpty: if the file is missing, empty, or missing
                any of the required keys.
        """
        if not self._path.exists():
            raise TokenStoreEmpty(f"no token file at {self._path}")
        text = self._path.read_text(encoding="utf-8")
        if not text.strip():
            raise TokenStoreEmpty(f"token file {self._path} is empty")
        parsed = _parse_env(text)
        try:
            access = parsed[_ACCESS_KEY]
            refresh_tok = parsed[_REFRESH_KEY]
            expires_at = int(parsed[_EXPIRES_KEY])
        except (KeyError, ValueError) as exc:
            raise TokenStoreEmpty(
                f"token file {self._path} is missing required keys: {exc}"
            ) from exc
        return Tokens(
            access_token=access,
            refresh_token=refresh_tok,
            expires_at=expires_at,
        )

    def save_atomic(self, tokens: Tokens) -> None:
        """Write ``tokens`` atomically and force mode 0600.

        Strategy: create ``<path>.tmp``, chmod 0600 BEFORE writing
        secrets to it (so the secret never lands on a world-readable
        file even briefly), write, fsync, ``os.replace`` over the
        target, then re-chmod the final path. macOS will sometimes
        widen the mode through replace, so we re-stat and re-chmod
        until it sticks.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # The parent dir holds the secret too; keep it tight.
        try:
            os.chmod(self._path.parent, 0o700)
        except OSError:
            pass

        # Preserve unmanaged keys (e.g. CRM_BASE_URL, SUPABASE_ANON_KEY) so
        # the env file can be a single source of truth for both static config
        # and rotating tokens.
        existing: dict[str, str] = {}
        if self._path.exists():
            try:
                existing = _parse_env(self._path.read_text(encoding="utf-8"))
            except OSError:
                existing = {}

        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        # Open with O_EXCL-style safety: remove any stale tmp first.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

        # Open with mode 0600 from the start. Some umasks would widen
        # the mode otherwise.
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(_serialise(tokens, existing))
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            # Best-effort cleanup; never leak a half-written tmp.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        # Belt-and-braces: chmod tmp again in case the open mode lost
        # to a noisy umask.
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)
        # Verify the final path is 0600. APFS preserves the source's
        # mode through replace, but be paranoid.
        os.chmod(self._path, 0o600)
        st = os.stat(self._path)
        mode = stat.S_IMODE(st.st_mode)
        if mode != 0o600:
            # One more attempt; if this fails we surface the problem
            # rather than silently leaving a world-readable secret.
            os.chmod(self._path, 0o600)
            st = os.stat(self._path)
            if stat.S_IMODE(st.st_mode) != 0o600:
                raise RuntimeError(
                    f"refused to leave {self._path} with mode {oct(mode)}; "
                    "filesystem appears to be rejecting chmod"
                )
