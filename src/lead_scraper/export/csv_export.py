from __future__ import annotations

import csv
from pathlib import Path

from lead_scraper.models import Lead


class CsvExporter:
    def __init__(self, out_path: str):
        self._out_path = Path(out_path)

    def export(self, leads: list[Lead]) -> str:
        self._out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "name",
                    "category",
                    "address",
                    "phone",
                    "website",
                    "review_count",
                    "rating",
                    "maps_url",
                    "social_links",
                    "flags",
                    "lead_score",
                ],
            )
            writer.writeheader()
            for lead in leads:
                writer.writerow(
                    {
                        "name": lead.name,
                        "category": lead.category,
                        "address": lead.address,
                        "phone": lead.phone,
                        "website": lead.website,
                        "review_count": lead.review_count,
                        "rating": lead.rating,
                        "maps_url": lead.maps_url,
                        "social_links": dict(lead.social_links),
                        "flags": dict(lead.flags),
                        "lead_score": lead.lead_score,
                    }
                )
        return str(self._out_path)
