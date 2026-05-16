from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Lead:
    name: str
    category: str
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    review_count: int | None = None
    rating: float | None = None
    maps_url: str | None = None
    social_links: dict[str, str] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    lead_score: float | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)


def lead_to_dict(lead: Lead) -> dict[str, Any]:
    return {
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
        "evidence": list(lead.evidence),
    }
