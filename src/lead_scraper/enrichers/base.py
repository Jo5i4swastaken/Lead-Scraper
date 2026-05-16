from __future__ import annotations

from abc import ABC, abstractmethod

from lead_scraper.models import Lead


class BaseEnricher(ABC):
    @abstractmethod
    async def enrich(self, leads: list[Lead]) -> list[Lead]:
        raise NotImplementedError
