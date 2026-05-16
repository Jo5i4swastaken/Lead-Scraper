import json

from lead_scraper.export.identity import lead_identity
from lead_scraper.export.jsonl import JsonlExporter
from lead_scraper.export.schema import CSV_COLUMNS, lead_to_export_dict
from lead_scraper.models import Lead
from lead_scraper.scorers.lead_quality import LeadQualityScorer, LeadQualityScorerConfig


def test_export_schema_has_stable_columns() -> None:
    assert CSV_COLUMNS[0] == "lead_id"
    assert CSV_COLUMNS[-1] == "exported_at"
    assert len(set(CSV_COLUMNS)) == len(CSV_COLUMNS)


def test_qualification_reasons_from_evidence() -> None:
    lead = Lead(
        name="Test Biz",
        category="plumber",
        address=None,
        phone=None,
        website=None,
        review_count=0,
        rating=3.2,
        maps_url="https://maps.google.com/?q=123",
        social_links={},
        flags={},
    )
    config = LeadQualityScorerConfig(
        low_reviews_threshold=10,
        inactive_social_days_threshold=90,
        min_social_links_for_presence=1,
        weights=LeadQualityScorerConfig.defaults_weights(),
        qualified_threshold=50.0,
    )
    LeadQualityScorer(config=config).score([lead])
    row = lead_to_export_dict(lead)
    reasons = set(str(row["qualification_reasons"]).split(","))
    assert "no_website_listed" in reasons
    assert "low_reviews" in reasons


def test_jsonl_incremental_dedup(tmp_path) -> None:
    lead = Lead(
        name="A",
        category="cat",
        address="1",
        phone="2",
        website=None,
        review_count=None,
        rating=None,
        maps_url=None,
        social_links={},
        flags={},
    )
    out = tmp_path / "leads.jsonl"
    exporter = JsonlExporter(str(out), incremental=True)
    exporter.export([lead])
    exporter.export([lead])

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["lead_id"] == lead_identity(lead)

