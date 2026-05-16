from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lead_scraper.config.settings import SerpApiSettings
from lead_scraper.scrapers.maps_serpapi.scraper import SerpApiGoogleMapsScraper


class TestMapsSerpApiScraper(unittest.TestCase):
    def test_parses_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["SERPAPI_API_KEY"] = "test"
            settings = SerpApiSettings(engine="google_maps", rate_limit_per_sec=1000.0, concurrency=1, timeout_sec=1)
            scraper = SerpApiGoogleMapsScraper(settings, trace_dir=Path(tmp))

            fake = {
                "local_results": [
                    {
                        "title": "Acme Dental",
                        "type": "Dentist",
                        "address": "123 Main St",
                        "phone": "+1 555-0100",
                        "website": "https://acme.example",
                        "reviews": 42,
                        "rating": 4.7,
                        "link": "https://www.google.com/maps?cid=123",
                        "place_id": "abc",
                    }
                ]
            }

            async def run() -> None:
                with patch(
                    "lead_scraper.scrapers.maps_serpapi.scraper._fetch_json",
                    autospec=True,
                    return_value=fake,
                ):
                    leads = await scraper.scrape(city="McAllen", category="dentists")
                    self.assertEqual(len(leads), 1)
                    lead = leads[0]
                    self.assertEqual(lead.name, "Acme Dental")
                    self.assertEqual(lead.category, "Dentist")
                    self.assertEqual(lead.address, "123 Main St")
                    self.assertEqual(lead.phone, "+1 555-0100")
                    self.assertEqual(lead.website, "https://acme.example")
                    self.assertEqual(lead.review_count, 42)
                    self.assertEqual(lead.rating, 4.7)
                    self.assertEqual(lead.maps_url, "https://www.google.com/maps?cid=123")
                    self.assertEqual(lead.flags.get("google_place_id"), "abc")
                    self.assertEqual(lead.flags.get("query_category"), "dentists")

                    raw_files = list((Path(tmp) / "raw").glob("*.json"))
                    self.assertEqual(len(raw_files), 1)
                    payload = json.loads(raw_files[0].read_text(encoding="utf-8"))
                    self.assertIn("response", payload)

                    norm_files = list((Path(tmp) / "normalized").glob("*.jsonl"))
                    self.assertEqual(len(norm_files), 1)

            asyncio.run(run())
