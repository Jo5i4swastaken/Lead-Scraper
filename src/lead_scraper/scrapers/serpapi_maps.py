from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from lead_scraper.config.settings import SerpApiSettings, require_serpapi_api_key
from lead_scraper.models import Lead
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
    def __init__(self, settings: SerpApiSettings):
        self._settings = settings
        self._api_key = require_serpapi_api_key()
        self._sem = asyncio.Semaphore(settings.concurrency)
        min_interval = 1.0 / max(settings.rate_limit_per_sec, 0.001)
        self._rate_limiter = _RateLimiter(min_interval_sec=min_interval)

    async def scrape(self, *, city: str, category: str) -> list[Lead]:
        query = f"{category} in {city}, TX"
        raw = await self._serpapi_request(
            {
                "engine": self._settings.engine,
                "q": query,
                "api_key": self._api_key,
            }
        )

        results: list[Lead] = []
        for item in raw.get("local_results", []) or []:
            lead = _lead_from_serpapi_item(item=item, category=category)
            if lead:
                lead.evidence.append({"source": "serpapi", "query": query, "raw": item})
                results.append(lead)
        return results

    async def _serpapi_request(self, params: dict[str, str]) -> dict[str, Any]:
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)

        async with self._sem:
            await self._rate_limiter.wait()
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: _fetch_json(url, timeout_sec=self._settings.timeout_sec))


def _fetch_json(url: str, *, timeout_sec: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "lead-scraper/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def _lead_from_serpapi_item(*, item: dict[str, Any], category: str) -> Lead | None:
    name = item.get("title")
    if not name:
        return None

    return Lead(
        name=str(name),
        category=str(category),
        address=_opt_str(item.get("address")),
        phone=_opt_str(item.get("phone")),
        website=_opt_str(item.get("website")),
        review_count=_opt_int(item.get("reviews")),
        rating=_opt_float(item.get("rating")),
        maps_url=_opt_str(item.get("link")),
        social_links={},
        flags={},
        lead_score=None,
        evidence=[],
    )


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
