from lead_scraper.models import Lead
from lead_scraper.scorers.lead_quality import LeadQualityScorer, LeadQualityScorerConfig


def test_lead_quality_flags_and_score() -> None:
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
    scorer = LeadQualityScorer(config=config)
    scorer.score([lead])

    assert lead.flags["no_website_listed"] is True
    assert lead.flags["low_reviews"] is True
    assert lead.flags["incomplete_profile"] is True
    assert lead.lead_score is not None
    assert lead.qualified is True
    assert any(ev.get("type") == "lead_quality_factor" for ev in lead.evidence)


def test_inactive_social_uses_last_post_days() -> None:
    lead = Lead(
        name="Social Biz",
        category="restaurant",
        address="123 Main",
        phone="555",
        website="https://example.com",
        review_count=100,
        rating=4.7,
        maps_url=None,
        social_links={"instagram": "https://instagram.com/x"},
        flags={"social_last_post_days": 200},
    )
    config = LeadQualityScorerConfig(
        low_reviews_threshold=20,
        inactive_social_days_threshold=90,
        min_social_links_for_presence=1,
        weights=LeadQualityScorerConfig.defaults_weights(),
        qualified_threshold=1.0,
    )
    LeadQualityScorer(config=config).score([lead])
    assert lead.flags["inactive_social"] is True

