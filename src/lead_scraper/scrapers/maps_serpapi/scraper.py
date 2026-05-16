from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lead_scraper.config.settings import SerpApiSettings, require_serpapi_api_key
from lead_scraper.models import Lead, lead_to_dict
from lead_scraper.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _RateLimiter:
    min_interval_sec: float
    _next_allowed_ts: float = 0.0
    _lock: asyncio.Lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait_for = max(0.0, self._next_allowed_ts - now)
            self._next_allowed_ts = max(self._next_allowed_ts, now) + self.min_interval_sec
        if wait_for > 0:
            await asyncio.sleep(wait_for)


class SerpApiGoogleMapsScraper(BaseScraper):
    def __init__(self, settings: SerpApiSettings, *, trace_dir: Path | None = None):
        self._settings = settings
        self._api_key = require_serpapi_api_key()
        self._sem = asyncio.Semaphore(settings.concurrency)
        min_interval = 1.0 / max(settings.rate_limit_per_sec, 0.001)
        self._rate_limiter = _RateLimiter(min_interval_sec=min_interval)
        self._trace_dir = trace_dir

    async def scrape(self, *, city: str, category: str) -> list[Lead]:
        query = f"{category} in {city}, TX"
        params = {
            "engine": self._settings.engine,
            "q": query,
            "api_key": self._api_key,
        }

        raw = await self._serpapi_request(params)
        self._persist_raw(query=query, params=params, raw=raw)

        results: list[Lead] = []
        for item in raw.get("local_results", []) or []:
            lead = _lead_from_serpapi_item(item=item, query_category=category)
            if lead:
                lead.evidence.append({"source": "serpapi", "query": query, "raw": item})
                results.append(lead)

        self._persist_normalized(query=query, leads=results)
        return results

    async def _serpapi_request(self, params: dict[str, str]) -> dict[str, Any]:
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)

        async with self._sem:
            attempt = 0
            while True:
                attempt += 1
                await self._rate_limiter.wait()
                loop = asyncio.get_running_loop()
                try:
                    return await loop.run_in_executor(
                        None,
                        lambda: _fetch_json(url, timeout_sec=self._settings.timeout_sec),
                    )
                except urllib.error.HTTPError as e:
                    if attempt >= 5 or e.code not in (408, 425, 429, 500, 502, 503, 504):
                        raise
                    await _sleep_backoff(attempt, hint=f"http_{e.code}")
                except (urllib.error.URLError, TimeoutError) as e:
                    if attempt >= 5:
                        raise
                    await _sleep_backoff(attempt, hint=type(e).__name__)

    def _persist_raw(self, *, query: str, params: dict[str, str], raw: dict[str, Any]) -> None:
        if self._trace_dir is None:
            return
        raw_dir = self._trace_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / f"{_safe_slug(query)}.json"
        path.write_text(
            json.dumps({"query": query, "params": dict(params), "response": raw}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _persist_normalized(self, *, query: str, leads: list[Lead]) -> None:
        if self._trace_dir is None:
            return
        norm_dir = self._trace_dir / "normalized"
        norm_dir.mkdir(parents=True, exist_ok=True)
        path = norm_dir / f"{_safe_slug(query)}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for lead in leads:
                f.write(json.dumps(lead_to_dict(lead), ensure_ascii=False) + "\n")


async def _sleep_backoff(attempt: int, *, hint: str) -> None:
    base = 0.8
    cap = 20.0
    delay = min(cap, base * (2 ** (attempt - 1)))
    delay = delay * (0.85 + random.random() * 0.3)
    logger.warning("serpapi retry in %.2fs (%s, attempt %d)", delay, hint, attempt)
    await asyncio.sleep(delay)


def _fetch_json(url: str, *, timeout_sec: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "lead-scraper/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def _lead_from_serpapi_item(*, item: dict[str, Any], query_category: str) -> Lead | None:
    name = item.get("title")
    if not name:
        return None

    primary_category = _opt_str(item.get("type")) or query_category
    place_id = _opt_str(item.get("place_id"))

    flags: dict[str, Any] = {}
    if place_id:
        flags["google_place_id"] = place_id
    if query_category:
        flags["query_category"] = query_category

    return Lead(
        name=str(name),
        category=primary_category,
        address=_opt_str(item.get("address")),
        phone=_opt_str(item.get("phone")),
        website=_opt_str(item.get("website")),
        review_count=_opt_int(item.get("reviews")),
        rating=_opt_float(item.get("rating")),
        maps_url=_opt_str(item.get("link")),
        social_links={},
        flags=flags,
        lead_score=None,
        evidence=[],
    )


def _safe_slug(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower())
    normalized = "_".join([part for part in normalized.split("_") if part])
    return normalized[:180] or "query"


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _opt_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        logger.debug("Failed int cast: %r", value)
        return None


def _opt_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        logger.debug("Failed float cast: %r", value)
        return None

