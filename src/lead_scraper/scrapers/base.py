from __future__ import annotations

from abc import ABC, abstractmethod

from lead_scraper.models import Lead


class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, *, city: str, category: str) -> list[Lead]:
        raise NotImplementedError
