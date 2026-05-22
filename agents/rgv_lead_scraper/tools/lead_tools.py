from __future__ import annotations

import json
import os
from typing import Any

import httpx
from omniagents import function_tool


# ---------------------------------------------------------------------------
# Read-only helper — still exposed for the agent so it can show its config
# and the user can see which CRM endpoint it's pointed at.
# ---------------------------------------------------------------------------


@function_tool
def get_settings_summary() -> dict[str, Any]:
    """Return a safe summary of which CRM the agent will write to.

    No secrets. The JWT is read from env at call time, never returned here.
    """
    base_url = os.environ.get("CRM_BASE_URL", "")
    jwt_present = bool(os.environ.get("CRM_USER_JWT"))
    return {
        "crm_base_url": base_url or "<unset>",
        "crm_jwt_configured": jwt_present,
        "lead_generation_endpoint": (
            f"{base_url.rstrip('/')}/functions/v1/generate-leads" if base_url else "<unset>"
        ),
    }


# ---------------------------------------------------------------------------
# Sole mutating tool — gated by the OmniAgents host (NOT in safe_tool_names).
# ---------------------------------------------------------------------------


@function_tool
async def request_lead_generation(
    city: str,
    category: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Search Google Maps for businesses in `city` matching `category` and
    write the top `limit` results into the CRM leads table.

    This is the **only** way the agent can change CRM data. It calls the CRM's
    `generate-leads` edge function with the admin's JWT (env: CRM_USER_JWT).
    The edge function enforces:
      - admin gate (3 layers: UI, function, RLS)
      - per-user rate limit (default 3/min)
      - monthly SerpAPI budget (250)
      - 14-day search cache (cache hits are free)
      - two-stage write: candidates -> top-N promoted to leads
      - upsert-with-ignore-on-conflict (no UPDATE, no DELETE — insert-only)

    Returns the edge function envelope:
        {requested, candidates_scraped, candidates_total, leads_promoted,
         duplicates, source: 'serpapi'|'cache', monthly_usage: {used, total}}
    """
    base_url = os.environ.get("CRM_BASE_URL", "").rstrip("/")
    jwt = os.environ.get("CRM_USER_JWT", "")
    if not base_url:
        raise RuntimeError("CRM_BASE_URL is not set. The agent needs the Supabase project URL.")
    if not jwt:
        raise RuntimeError(
            "CRM_USER_JWT is not set. Log into the CRM and copy your access token into the environment."
        )

    limit = max(1, min(int(limit), 20))
    url = f"{base_url}/functions/v1/generate-leads"
    payload = {"city": city, "category": category, "limit": limit}
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code >= 400:
        try:
            err = resp.json()
            message = err.get("error") or err.get("message") or resp.text
        except (ValueError, json.JSONDecodeError):
            message = resp.text or f"HTTP {resp.status_code}"
        raise RuntimeError(f"generate-leads failed ({resp.status_code}): {message}")

    return resp.json()
