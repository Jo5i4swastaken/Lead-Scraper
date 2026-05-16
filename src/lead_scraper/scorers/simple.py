from __future__ import annotations

from lead_scraper.models import Lead
from lead_scraper.scorers.base import BaseScorer


class SimpleHeuristicScorer(BaseScorer):
    def score(self, leads: list[Lead]) -> list[Lead]:
        for lead in leads:
            rating = lead.rating or 0.0
            reviews = float(lead.review_count or 0)
            lead.lead_score = round((rating * 20.0) + (min(reviews, 500.0) / 10.0), 3)
        return leads
