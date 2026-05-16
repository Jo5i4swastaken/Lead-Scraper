from __future__ import annotations

import hashlib

from lead_scraper.models import Lead


def lead_identity(lead: Lead) -> str:
    place_id = str(lead.flags.get("google_place_id") or "").strip()
    if place_id:
        return f"place_id:{place_id}"

    maps_url = (lead.maps_url or "").strip()
    if maps_url:
        return f"maps_url:{maps_url}"

    name = lead.name.strip().lower()
    category = lead.category.strip().lower()
    phone = (lead.phone or "").strip()
    address = (lead.address or "").strip().lower()
    raw = f"{name}|{category}|{phone}|{address}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"fallback:{digest}"

