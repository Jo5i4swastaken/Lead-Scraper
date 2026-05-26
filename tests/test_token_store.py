"""Unit tests for :mod:`rgv_lead_scraper.auth.token_store`."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from rgv_lead_scraper.auth import token_store as ts_mod
from rgv_lead_scraper.auth.token_store import Tokens, TokenStore, TokenStoreEmpty


def _make_store(tmp_path: Path) -> TokenStore:
    return TokenStore(tmp_path / "agent.env")


def test_load_raises_when_file_missing(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    with pytest.raises(TokenStoreEmpty):
        store.load()


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    tokens = Tokens(access_token="a.b.c", refresh_token="r-1", expires_at=1_700_000_000)
    store.save_atomic(tokens)

    loaded = store.load()
    assert loaded == tokens


def test_saved_file_is_mode_0600(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.save_atomic(Tokens("a", "r", 1))
    mode = stat.S_IMODE(os.stat(store.path).st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_load_after_partial_write_does_not_corrupt(tmp_path: Path, monkeypatch) -> None:
    """Simulate a crash mid-write: ``os.replace`` raises after the tmp
    file is written. The original file (if any) must remain readable
    and unchanged.
    """
    store = _make_store(tmp_path)
    good = Tokens("orig", "orig-r", 1_700_000_000)
    store.save_atomic(good)

    real_replace = os.replace

    def boom(src, dst):  # pragma: no cover - control flow only
        raise OSError("disk on fire")

    monkeypatch.setattr(ts_mod.os, "replace", boom)

    with pytest.raises(OSError):
        store.save_atomic(Tokens("new", "new-r", 2_000_000_000))

    # Restore for the read-back.
    monkeypatch.setattr(ts_mod.os, "replace", real_replace)
    loaded = store.load()
    assert loaded == good, "original file should survive a failed replace"

    # And the tmp file must not be left behind in a half-written state
    # that some future code could mistake for the real file.
    tmp = store.path.with_suffix(store.path.suffix + ".tmp")
    # Either cleaned up or still present but never replaces the real one.
    # If present, it should NOT be the same content as the real file.
    if tmp.exists():
        assert tmp.read_text() != store.path.read_text()


def test_override_path_via_env(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "custom.env"
    monkeypatch.setenv("WORKLOGICLY_AGENT_ENV", str(target))
    store = TokenStore()
    assert store.path == target


def test_load_rejects_file_missing_required_keys(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("CRM_ACCESS_TOKEN=only-access\n")
    with pytest.raises(TokenStoreEmpty):
        store.load()


def test_save_preserves_unmanaged_keys(tmp_path: Path) -> None:
    """save_atomic must keep static config (CRM_BASE_URL, SUPABASE_ANON_KEY,
    arbitrary user-added keys) instead of clobbering the whole file. The
    refresh flow rewrites this file every ~hour; losing config on each
    refresh would break the launchd-managed agent."""
    store = _make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        "CRM_BASE_URL=https://project.supabase.co\n"
        "SUPABASE_ANON_KEY=eyJ-anon-key\n"
        "USER_CUSTOM=keep-me\n"
    )

    tokens = Tokens(access_token="new-access", refresh_token="new-refresh", expires_at=1)
    store.save_atomic(tokens)

    text = store.path.read_text()
    assert "CRM_BASE_URL=https://project.supabase.co" in text
    assert "SUPABASE_ANON_KEY=eyJ-anon-key" in text
    assert "USER_CUSTOM=keep-me" in text
    assert "CRM_ACCESS_TOKEN=new-access" in text
    # Round-trip still works.
    assert store.load() == tokens


def test_save_overwrites_old_managed_keys(tmp_path: Path) -> None:
    """A previous token pair must be fully replaced, not appended."""
    store = _make_store(tmp_path)
    store.save_atomic(Tokens("old", "old-r", 1))
    store.save_atomic(Tokens("new", "new-r", 2))
    text = store.path.read_text()
    assert text.count("CRM_ACCESS_TOKEN=") == 1
    assert "old" not in text


def test_parses_quoted_values(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        'CRM_ACCESS_TOKEN="a.b.c"\n'
        "CRM_REFRESH_TOKEN='r-1'\n"
        "CRM_ACCESS_TOKEN_EXPIRES_AT=42\n"
    )
    loaded = store.load()
    assert loaded == Tokens("a.b.c", "r-1", 42)
