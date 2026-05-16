from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from lead_scraper.export.identity import lead_identity
from lead_scraper.models import Lead


CSV_COLUMNS: tuple[str, ...] = (
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


def lead_to_export_dict(lead: Lead) -> dict[str, Any]:
    exported_at = datetime.now(timezone.utc).isoformat()
    reasons = _qualification_reasons(lead)
    return {
        "lead_id": lead_identity(lead),
        "name": lead.name,
        "category": lead.category,
        "address": lead.address,
        "phone": lead.phone,
        "website": lead.website,
        "review_count": lead.review_count,
        "rating": lead.rating,
        "maps_url": lead.maps_url,
        "social_links_json": dict(lead.social_links),
        "flags_json": dict(lead.flags),
        "lead_score": lead.lead_score,
        "qualified": lead.qualified,
        "qualification_reasons": ",".join(reasons),
        "evidence_json": list(lead.evidence),
        "exported_at": exported_at,
    }


def _qualification_reasons(lead: Lead) -> list[str]:
    factors: set[str] = set()
    for item in lead.evidence or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "lead_quality_factor":
            continue
        if item.get("active") is not True:
            continue
        factor = item.get("factor")
        if isinstance(factor, str) and factor.strip():
            factors.add(factor.strip())
    if not factors:
        flags_reasons = lead.flags.get("qualification_reasons")
        if isinstance(flags_reasons, list):
            for x in flags_reasons:
                if isinstance(x, str) and x.strip():
                    factors.add(x.strip())
        elif isinstance(flags_reasons, str) and flags_reasons.strip():
            try:
                parsed = json.loads(flags_reasons)
                if isinstance(parsed, list):
                    for x in parsed:
                        if isinstance(x, str) and x.strip():
                            factors.add(x.strip())
            except Exception:
                pass
    return sorted(factors)

