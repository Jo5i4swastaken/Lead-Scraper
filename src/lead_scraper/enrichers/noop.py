from __future__ import annotations

from lead_scraper.enrichers.base import BaseEnricher
from lead_scraper.models import Lead


class NoopEnricher(BaseEnricher):
    async def enrich(self, leads: list[Lead]) -> list[Lead]:
        return leads
