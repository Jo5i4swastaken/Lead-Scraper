from __future__ import annotations

from abc import ABC, abstractmethod

from lead_scraper.models import Lead


class BaseExporter(ABC):
    @abstractmethod
    def export(self, leads: list[Lead]) -> str:
        raise NotImplementedError
