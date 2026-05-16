from __future__ import annotations

from abc import ABC, abstractmethod

from lead_scraper.models import Lead


class BaseScorer(ABC):
    @abstractmethod
    def score(self, leads: list[Lead]) -> list[Lead]:
        raise NotImplementedError
