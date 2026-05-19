"""Failure-mode test matrix for Phase 1.3 (see plan/task_plan.md §1.3).

Each test corresponds to one row in the failure-mode matrix. Waivers (if any)
live in plan/findings.md under "failure-mode matrix status".
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lead_scraper.config.settings import (
    SerpApiSettings,
    require_serpapi_api_key,
)
from lead_scraper.export.jsonl import JsonlExporter
from lead_scraper.models import Lead
from lead_scraper.pipeline import _dedupe
from lead_scraper.scrapers.maps_serpapi.scraper import SerpApiGoogleMapsScraper


# --- helpers ---------------------------------------------------------------

def _settings() -> SerpApiSettings:
    return SerpApiSettings(
        engine="google_maps",
        rate_limit_per_sec=1000.0,
        concurrency=1,
        timeout_sec=1,
    )


def _scraper(tmp_path: Path) -> SerpApiGoogleMapsScraper:
    os.environ["SERPAPI_API_KEY"] = "test"
    return SerpApiGoogleMapsScraper(_settings(), trace_dir=tmp_path)


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """Make backoff sleeps a no-op so retry tests don't take 20s."""
    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(
        "lead_scraper.scrapers.maps_serpapi.scraper._sleep_backoff",
        _noop,
    )
    # Also short-circuit any direct asyncio.sleep calls.
    real_sleep = asyncio.sleep

    async def _fast_sleep(delay, *a, **kw):
        return await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)


# --- row 1: missing SERPAPI_API_KEY ----------------------------------------

def test_missing_serpapi_api_key_raises_clean_error(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        require_serpapi_api_key()
    assert "SERPAPI_API_KEY" in str(exc.value)


def test_scraper_construction_requires_api_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        SerpApiGoogleMapsScraper(_settings())


# --- row 2: SerpAPI 429/500 → backoff fires, max 5 attempts -----------------

def test_serpapi_http_429_retries_up_to_five_attempts(tmp_path):
    scraper = _scraper(tmp_path)
    err = urllib.error.HTTPError(
        url="https://serpapi.com/search.json", code=429,
        msg="Too Many Requests", hdrs=None, fp=None,
    )
    calls = {"n": 0}

    def fail_429(*_a, **_kw):
        calls["n"] += 1
        raise err

    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        side_effect=fail_429,
    ):
        with pytest.raises(urllib.error.HTTPError):
            asyncio.run(scraper.scrape(city="McAllen", category="plumbers"))

    assert calls["n"] == 5, f"expected exactly 5 attempts, got {calls['n']}"


def test_serpapi_http_500_retries_then_succeeds(tmp_path):
    scraper = _scraper(tmp_path)
    err = urllib.error.HTTPError(
        url="x", code=500, msg="server error", hdrs=None, fp=None,
    )
    payload = {"local_results": [{"title": "OK Biz", "place_id": "p1"}]}
    seq = [err, err, payload]

    def step(*_a, **_kw):
        nxt = seq.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        side_effect=step,
    ):
        leads = asyncio.run(scraper.scrape(city="McAllen", category="plumbers"))
    assert len(leads) == 1
    assert leads[0].name == "OK Biz"


def test_serpapi_non_retryable_4xx_raises_immediately(tmp_path):
    scraper = _scraper(tmp_path)
    err = urllib.error.HTTPError(
        url="x", code=401, msg="unauth", hdrs=None, fp=None,
    )
    calls = {"n": 0}

    def step(*_a, **_kw):
        calls["n"] += 1
        raise err

    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        side_effect=step,
    ):
        with pytest.raises(urllib.error.HTTPError):
            asyncio.run(scraper.scrape(city="x", category="y"))
    assert calls["n"] == 1, "401 should not retry"


# --- row 3: empty local_results -------------------------------------------

def test_empty_local_results_returns_empty_list(tmp_path):
    scraper = _scraper(tmp_path)
    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        return_value={"local_results": []},
    ):
        leads = asyncio.run(scraper.scrape(city="McAllen", category="ice_sculptors"))
    assert leads == []


def test_missing_local_results_key_returns_empty_list(tmp_path):
    scraper = _scraper(tmp_path)
    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        return_value={},
    ):
        leads = asyncio.run(scraper.scrape(city="McAllen", category="ice_sculptors"))
    assert leads == []


# --- row 4: malformed items ------------------------------------------------

def test_malformed_item_missing_title_is_dropped(tmp_path):
    scraper = _scraper(tmp_path)
    payload = {
        "local_results": [
            {"title": None, "place_id": "skip-me"},
            {"place_id": "no-title-key"},
            {"title": "Keeper", "place_id": "ok"},
        ]
    }
    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        return_value=payload,
    ):
        leads = asyncio.run(scraper.scrape(city="McAllen", category="x"))
    assert [l.name for l in leads] == ["Keeper"]


def test_malformed_item_non_numeric_reviews_normalizes_to_none(tmp_path):
    scraper = _scraper(tmp_path)
    payload = {
        "local_results": [
            {
                "title": "Garbage Reviews",
                "reviews": "many",
                "rating": "five-stars",
                "place_id": "p1",
            },
            {
                "title": "Good Reviews",
                "reviews": 17,
                "rating": 4.5,
                "place_id": "p2",
            },
        ]
    }
    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        return_value=payload,
    ):
        leads = asyncio.run(scraper.scrape(city="McAllen", category="x"))
    by_name = {l.name: l for l in leads}
    assert by_name["Garbage Reviews"].review_count is None
    assert by_name["Garbage Reviews"].rating is None
    assert by_name["Good Reviews"].review_count == 17
    assert by_name["Good Reviews"].rating == 4.5


# --- row 5: non-ASCII / special chars in city + category --------------------

def test_non_ascii_city_and_category_round_trip(tmp_path):
    scraper = _scraper(tmp_path)
    payload = {"local_results": [{"title": "Café del Sol", "place_id": "p1"}]}
    captured = {}

    def fake_fetch(url, *, timeout_sec):
        captured["url"] = url
        return payload

    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        side_effect=fake_fetch,
    ):
        leads = asyncio.run(scraper.scrape(city="México D.F.", category="café/HVAC"))

    assert len(leads) == 1
    # URL must encode the unicode; raw bytes should not appear unescaped.
    assert "M%C3%A9xico" in captured["url"] or "México" not in captured["url"]
    # Trace persistence must not crash on the unicode query slug.
    raw_files = list((tmp_path / "raw").glob("*.json"))
    assert len(raw_files) == 1
    payload_on_disk = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert "México" in payload_on_disk["query"]


# --- row 6: network timeout -------------------------------------------------

def test_network_timeout_retries_then_raises(tmp_path):
    scraper = _scraper(tmp_path)
    calls = {"n": 0}

    def hang(*_a, **_kw):
        calls["n"] += 1
        raise TimeoutError("simulated hang")

    with patch(
        "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
        side_effect=hang,
    ):
        with pytest.raises(TimeoutError):
            asyncio.run(scraper.scrape(city="x", category="y"))
    assert calls["n"] == 5


# --- row 7: concurrent runs / trace collision ------------------------------

def test_concurrent_scrapes_share_trace_dir_last_writer_wins(tmp_path):
    """Two concurrent scrapes with the same (city, category) write to the
    same trace filename. The slug derives from query alone, so the second
    write overwrites the first. This documents the current behaviour.

    Phase 2 ports this to an edge function with audit rows keyed on
    (user_id, created_at); the per-call collision risk does not carry over.
    """
    os.environ["SERPAPI_API_KEY"] = "test"
    s1 = SerpApiGoogleMapsScraper(_settings(), trace_dir=tmp_path)
    s2 = SerpApiGoogleMapsScraper(_settings(), trace_dir=tmp_path)
    payload_a = {"local_results": [{"title": "A", "place_id": "a"}]}
    payload_b = {"local_results": [{"title": "B", "place_id": "b"}]}

    seq = [payload_a, payload_b]

    def step(*_a, **_kw):
        return seq.pop(0)

    async def run_both():
        with patch(
            "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
            side_effect=step,
        ):
            return await asyncio.gather(
                s1.scrape(city="McAllen", category="plumbers"),
                s2.scrape(city="McAllen", category="plumbers"),
            )

    leads_a, leads_b = asyncio.run(run_both())
    assert {leads_a[0].name, leads_b[0].name} == {"A", "B"}

    raw_files = list((tmp_path / "raw").glob("*.json"))
    assert len(raw_files) == 1, (
        "two concurrent scrapes with same query write to the same trace file; "
        "last writer wins. If you need per-run isolation, scope trace_dir per run."
    )


# --- row 8: dedupe across categories ---------------------------------------

def test_dedupe_collapses_same_place_id_across_categories():
    a = Lead(
        name="Joe's Plumbing",
        category="plumber",
        flags={"google_place_id": "PID-1"},
        evidence=[{"q": "plumbers in McAllen"}],
    )
    b = Lead(
        name="Joe's Plumbing",
        category="contractor",
        flags={"google_place_id": "PID-1"},
        evidence=[{"q": "contractors in McAllen"}],
    )
    deduped = _dedupe([a, b])
    assert len(deduped) == 1
    # Evidence from the dropped duplicate is merged into the survivor.
    assert len(deduped[0].evidence) == 2


# --- row 9: output dir missing / not writable -----------------------------

def test_jsonl_exporter_creates_missing_output_dir(tmp_path):
    out = tmp_path / "does" / "not" / "exist" / "leads.jsonl"
    exporter = JsonlExporter(str(out), incremental=True)
    lead = Lead(name="A", category="x", phone="555", flags={"google_place_id": "p1"})
    exporter.export([lead])
    assert out.exists()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


@pytest.mark.skipif(
    os.geteuid() == 0 if hasattr(os, "geteuid") else False,
    reason="chmod-based unwritable test is meaningless as root",
)
def test_jsonl_exporter_unwritable_directory_raises(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    out = locked / "leads.jsonl"
    os.chmod(locked, 0o500)  # r-x ------ : cannot write
    try:
        exporter = JsonlExporter(str(out), incremental=True)
        lead = Lead(name="A", category="x", flags={"google_place_id": "p1"})
        with pytest.raises(PermissionError):
            exporter.export([lead])
    finally:
        os.chmod(locked, 0o700)  # so pytest can clean up


# --- row 10: incremental export merges existing JSONL ----------------------

def test_jsonl_incremental_merges_new_leads_into_existing_file(tmp_path):
    out = tmp_path / "leads.jsonl"
    seed = Lead(
        name="Seed",
        category="plumber",
        flags={"google_place_id": "PID-SEED"},
    )
    JsonlExporter(str(out), incremental=True).export([seed])

    addition = Lead(
        name="New Biz",
        category="plumber",
        flags={"google_place_id": "PID-NEW"},
    )
    duplicate_of_seed = Lead(
        name="Seed",
        category="plumber",
        flags={"google_place_id": "PID-SEED"},
    )
    JsonlExporter(str(out), incremental=True).export([addition, duplicate_of_seed])

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, "existing seed must remain; new lead appended; duplicate dropped"
    ids = [json.loads(l)["lead_id"] for l in lines]
    assert ids == ["place_id:PID-SEED", "place_id:PID-NEW"]
