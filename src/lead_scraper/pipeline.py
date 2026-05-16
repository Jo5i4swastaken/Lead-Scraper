from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from lead_scraper.config.settings import Settings
from lead_scraper.enrichers.base import BaseEnricher
from lead_scraper.models import Lead
from lead_scraper.scorers.base import BaseScorer
from lead_scraper.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


def _dedupe(leads: list[Lead]) -> list[Lead]:
    grouped: dict[tuple[str, str, str | None], Lead] = {}
    for lead in leads:
        key = (lead.name.strip().lower(), lead.category.strip().lower(), (lead.phone or "").strip())
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = lead
        else:
            existing.evidence.extend(lead.evidence)
    return list(grouped.values())


async def run_scrape(*, settings: Settings, scraper: BaseScraper) -> list[Lead]:
    total = len(settings.cities) * len(settings.categories)
    done = 0

    async def one(city: str, category: str) -> list[Lead]:
        nonlocal done
        leads = await scraper.scrape(city=city, category=category)
        done += 1
        logger.info("scrape %s/%s: %d leads (%d/%d)", city, category, len(leads), done, total)
        return leads

    tasks = [one(city, category) for city in settings.cities for category in settings.categories]
    chunks = await asyncio.gather(*tasks)
    flattened = [lead for chunk in chunks for lead in chunk]
    deduped = _dedupe(flattened)
    logger.info("scrape complete: %d leads (deduped)", len(deduped))
    return deduped


async def run_enrich(*, enricher: BaseEnricher, leads: list[Lead]) -> list[Lead]:
    enriched = await enricher.enrich(leads)
    logger.info("enrich complete: %d leads", len(enriched))
    return enriched


def run_score(*, scorer: BaseScorer, leads: list[Lead]) -> list[Lead]:
    scored = scorer.score(leads)
    buckets = defaultdict(int)
    for lead in scored:
        if lead.lead_score is None:
            continue
        buckets[int(lead.lead_score // 10 * 10)] += 1
    logger.info("score complete: %d leads", len(scored))
    if buckets:
        logger.info("score buckets: %s", dict(sorted(buckets.items())))
    return scored
