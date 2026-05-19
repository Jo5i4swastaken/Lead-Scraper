"""Contract test for the JSONL output produced by `lead_to_export_dict`.

This is the frozen Phase 1.5 contract that the Phase 2.2 Deno edge function
will port verbatim. Field set, ordering, types, nullability, and `lead_id`
stability are pinned here. Breaking changes must be reflected in
plan/findings.md "Output contract (frozen)" AND the field map in
plan/task_plan.md §2.2.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from lead_scraper.export.identity import lead_identity
from lead_scraper.export.schema import CSV_COLUMNS, lead_to_export_dict
from lead_scraper.models import Lead
from lead_scraper.scorers.lead_quality import LeadQualityScorer, LeadQualityScorerConfig


# ---------- Frozen field set ----------

FROZEN_FIELDS: tuple[str, ...] = (
    "lead_id",
    "name",
    "category",
    "address",
    "phone",
    "website",
    "review_count",
    "rating",
    "maps_url",
    "social_links_json",
    "flags_json",
    "lead_score",
    "qualified",
    "qualification_reasons",
    "evidence_json",
    "exported_at",
)


def _make_serpapi_lead(
    *,
    name: str = "All Valley Plumbing & A/C",
    place_id: str | None = "ChIJj7rfF9OgZYYRaYlfOXw-ups",
    address: str | None = "2505 Buddy Owens Blvd Suite E, McAllen, TX 78504",
    phone: str | None = "(956) 686-6656",
    website: str | None = "http://www.allvalleyplumbing.com/",
    reviews: int | None = 467,
    rating: float | None = 4.7,
    category: str = "Plumber",
    query_category: str = "plumbers",
) -> Lead:
    flags: dict[str, Any] = {"query_category": query_category}
    if place_id:
        flags["google_place_id"] = place_id
    maps_url = (
        f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        if place_id
        else None
    )
    return Lead(
        name=name,
        category=category,
        address=address,
        phone=phone,
        website=website,
        review_count=reviews,
        rating=rating,
        maps_url=maps_url,
        social_links={},
        flags=flags,
    )


def _default_quality_config() -> LeadQualityScorerConfig:
    return LeadQualityScorerConfig(
        low_reviews_threshold=10,
        inactive_social_days_threshold=90,
        min_social_links_for_presence=1,
        weights=LeadQualityScorerConfig.defaults_weights(),
        qualified_threshold=50.0,
    )


# ---------- Field set / ordering / no-drift ----------


def test_csv_columns_match_frozen_field_set() -> None:
    """Schema's CSV_COLUMNS is the canonical ordering. Lock it."""
    assert CSV_COLUMNS == FROZEN_FIELDS


def test_export_dict_has_every_frozen_field() -> None:
    lead = _make_serpapi_lead()
    LeadQualityScorer(config=_default_quality_config()).score([lead])
    row = lead_to_export_dict(lead)

    assert set(row.keys()) == set(FROZEN_FIELDS), (
        "Row keys drifted from the frozen contract — update plan/findings.md "
        "'Output contract (frozen)' and the Deno field map in §2.2 before "
        "changing this test."
    )


def test_export_dict_is_json_round_trippable() -> None:
    lead = _make_serpapi_lead()
    LeadQualityScorer(config=_default_quality_config()).score([lead])
    row = lead_to_export_dict(lead)

    text = json.dumps(row, ensure_ascii=False)
    roundtripped = json.loads(text)
    assert roundtripped == row


# ---------- Types / nullability ----------


def test_field_types_match_contract_for_full_row() -> None:
    """Every field with a value present must match the frozen type."""
    lead = _make_serpapi_lead()
    LeadQualityScorer(config=_default_quality_config()).score([lead])
    row = lead_to_export_dict(lead)

    # Required, non-null strings.
    assert isinstance(row["lead_id"], str) and row["lead_id"]
    assert isinstance(row["name"], str) and row["name"]
    assert isinstance(row["category"], str) and row["category"]
    assert isinstance(row["qualification_reasons"], str)  # may be ""
    assert isinstance(row["exported_at"], str) and row["exported_at"]

    # Required, non-null containers.
    assert isinstance(row["social_links_json"], dict)
    assert isinstance(row["flags_json"], dict)
    assert isinstance(row["evidence_json"], list)

    # Nullable scalars (present here).
    assert isinstance(row["address"], str)
    assert isinstance(row["phone"], str)
    assert isinstance(row["website"], str)
    assert isinstance(row["review_count"], int)
    assert isinstance(row["rating"], float)
    assert isinstance(row["maps_url"], str)
    assert isinstance(row["lead_score"], (int, float))
    assert isinstance(row["qualified"], bool)


def test_field_types_match_contract_for_minimal_row() -> None:
    """All nullable fields default to JSON null; required containers stay empty."""
    lead = Lead(
        name="Hugo's Plumbing Service",
        category="Plumber",
        address=None,
        phone=None,
        website=None,
        review_count=None,
        rating=None,
        maps_url=None,
        social_links={},
        flags={},
    )
    row = lead_to_export_dict(lead)

    for field in (
        "address",
        "phone",
        "website",
        "review_count",
        "rating",
        "maps_url",
        "lead_score",
        "qualified",
    ):
        assert row[field] is None, f"{field} should be null when source is missing"

    assert row["social_links_json"] == {}
    assert row["flags_json"] == {}
    assert row["evidence_json"] == []
    assert row["qualification_reasons"] == ""


def test_exported_at_is_iso8601_utc() -> None:
    row = lead_to_export_dict(_make_serpapi_lead())
    assert row["exported_at"].endswith("+00:00"), (
        "exported_at must be UTC ISO8601 — Phase 2 readers parse on the suffix."
    )


# ---------- lead_id stability ----------


def test_lead_id_uses_place_id_prefix_when_present() -> None:
    lead = _make_serpapi_lead(place_id="ChIJABC123")
    assert lead_identity(lead) == "place_id:ChIJABC123"


def test_lead_id_is_stable_across_repeated_calls() -> None:
    lead = _make_serpapi_lead()
    first = lead_identity(lead)
    second = lead_identity(lead)
    assert first == second


def test_lead_id_is_stable_across_independent_constructions() -> None:
    """Same SerpAPI item parsed twice produces the same lead_id.

    This is the property the Phase 2.2 edge function depends on for free
    dedupe (`external_id` UNIQUE constraint).
    """
    a = _make_serpapi_lead()
    b = _make_serpapi_lead()
    assert lead_identity(a) == lead_identity(b)


def test_lead_id_falls_back_when_place_id_and_maps_url_absent() -> None:
    """Documented fallback path: name|category|phone|address SHA-256 prefix."""
    lead = _make_serpapi_lead(place_id=None)
    lead.maps_url = None
    lead.flags.pop("google_place_id", None)

    lead_id = lead_identity(lead)
    assert lead_id.startswith("fallback:")
    # 24-char hex prefix.
    assert len(lead_id.split(":", 1)[1]) == 24


def test_lead_id_fallback_normalises_whitespace_and_case() -> None:
    """Same business with cosmetic differences must hash to the same fallback id."""
    base = _make_serpapi_lead(
        place_id=None,
        name="Hugo's Plumbing",
        address="123 Main St",
        phone="(956) 503-8368",
        category="Plumber",
    )
    base.maps_url = None
    base.flags.pop("google_place_id", None)

    variant = _make_serpapi_lead(
        place_id=None,
        name="  Hugo's Plumbing  ",
        address="123 MAIN ST",
        phone="(956) 503-8368",
        category="PLUMBER",
    )
    variant.maps_url = None
    variant.flags.pop("google_place_id", None)

    assert lead_identity(base) == lead_identity(variant)


# ---------- Qualified scorer wiring ----------


def test_qualified_is_boolean_after_scoring() -> None:
    """Round 5 contract: `qualified` is a real boolean, never null after scoring."""
    leads = [_make_serpapi_lead(), _make_serpapi_lead(reviews=2, website=None)]
    LeadQualityScorer(config=_default_quality_config()).score(leads)

    for lead in leads:
        row = lead_to_export_dict(lead)
        assert isinstance(row["qualified"], bool), (
            "Phase 1 D1 contract: after LeadQualityScorer runs, `qualified` "
            "must be a concrete bool. Null here means the scorer wasn't wired."
        )


def test_qualification_reasons_join_active_factors() -> None:
    """`qualification_reasons` is a comma-joined sorted set of active factors."""
    lead = _make_serpapi_lead(reviews=2, website=None)  # triggers low_reviews + no_website
    LeadQualityScorer(config=_default_quality_config()).score([lead])
    row = lead_to_export_dict(lead)

    reasons = set(filter(None, str(row["qualification_reasons"]).split(",")))
    assert "low_reviews" in reasons
    assert "no_website_listed" in reasons
