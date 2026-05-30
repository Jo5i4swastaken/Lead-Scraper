from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from omniagents import function_tool

# OmniAgents discovers this file by ``rglob``-ing ``tools/``; sys.path
# during discovery includes the agent dir, but post-discovery it does
# not. Add the agent dir explicitly so ``from rgv_lead_scraper.auth import …``
# works at tool-call time too. The path is idempotent — multiple agent
# instances in one process won't keep stacking entries.
_AGENT_DIR = Path(__file__).resolve().parent.parent
_AGENTS_ROOT = _AGENT_DIR.parent
for _p in (str(_AGENTS_ROOT), str(_AGENT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    # Preferred path: package was installed via ``pip install -e .``.
    from rgv_lead_scraper.auth.jwt_provider import build_provider
    from rgv_lead_scraper.auth.supabase_auth import RefreshTokenExpired
except ImportError:
    # Fallback for discovery runs where the package wasn't installed
    # (uses the agent dir we just put on sys.path).
    from auth.jwt_provider import build_provider  # type: ignore[no-redef]
    from auth.supabase_auth import RefreshTokenExpired  # type: ignore[no-redef]


# Built lazily so importing the module never fails because of env vars
# the user hasn't set yet (the CLI still needs to be runnable to fix
# that exact problem).
_provider = None


def _get_provider():
    global _provider
    if _provider is None:
        _provider = build_provider(os.environ.get("AGENT_MODE", "local"))
    return _provider


_LOGIN_HINT = (
    "Your CRM credentials are missing or expired. Run "
    "`worklogicly-agent login` in a terminal, then retry."
)


# ---------------------------------------------------------------------------
# Read-only helper — still exposed for the agent so it can show its config
# and the user can see which CRM endpoint it's pointed at.
# ---------------------------------------------------------------------------


@function_tool
def get_settings_summary() -> dict[str, Any]:
    """Return a safe summary of which CRM the agent will write to.

    No secrets. Token contents are never returned; only booleans and
    the seconds remaining on the cached access token.
    """
    base_url = os.environ.get("CRM_BASE_URL", "")
    mode = os.environ.get("AGENT_MODE", "local")
    summary: dict[str, Any] = {
        "crm_base_url": base_url or "<unset>",
        "agent_mode": mode,
        "supabase_anon_key_configured": bool(os.environ.get("SUPABASE_ANON_KEY")),
        "lead_generation_endpoint": (
            f"{base_url.rstrip('/')}/functions/v1/generate-leads" if base_url else "<unset>"
        ),
        "lead_candidates_endpoint": (
            f"{base_url.rstrip('/')}/rest/v1/lead_candidates" if base_url else "<unset>"
        ),
        "promote_candidate_endpoint": (
            f"{base_url.rstrip('/')}/functions/v1/promote-candidate" if base_url else "<unset>"
        ),
    }
    if mode == "local":
        try:
            provider = _get_provider()
            summary["crm_refresh_token_configured"] = bool(
                getattr(provider, "has_refresh_token", lambda: False)()
            )
            expires_in = getattr(provider, "expires_in_seconds", lambda: None)()
            summary["access_token_expires_in_seconds"] = expires_in
        except Exception as exc:  # pragma: no cover - diagnostic only
            summary["crm_refresh_token_configured"] = False
            summary["access_token_expires_in_seconds"] = None
            summary["auth_error"] = str(exc)
    return summary


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
    `generate-leads` edge function with the admin's JWT (fetched from the
    configured :class:`JwtProvider`). The edge function enforces:
      - admin gate (3 layers: UI, function, RLS)
      - per-user rate limit (default 3/min)
      - monthly SerpAPI budget (250)
      - 14-day search cache (cache hits are free)
      - two-stage write: candidates -> top-N promoted to leads
      - upsert-with-ignore-on-conflict (no UPDATE, no DELETE — insert-only)

    Returns the edge function envelope:
        {requested, candidates_scraped, candidates_total, leads_promoted,
         duplicates, source: 'serpapi'|'cache', monthly_usage: {used, total}}

    On a missing/expired refresh token, returns a structured error
    payload telling the user to run ``worklogicly-agent login`` — the
    chat UI surfaces the ``message`` verbatim.
    """
    base_url = os.environ.get("CRM_BASE_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("CRM_BASE_URL is not set. The agent needs the Supabase project URL.")

    provider = _get_provider()

    try:
        jwt = await provider.get_jwt()
    except RefreshTokenExpired:
        return {
            "ok": False,
            "error": "auth_required",
            "message": _LOGIN_HINT,
        }

    limit = max(1, min(int(limit), 20))
    url = f"{base_url}/functions/v1/generate-leads"
    payload = {"city": city, "category": category, "limit": limit}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {jwt}",
                "Content-Type": "application/json",
            },
        )

        # Reactive refresh: one retry on 401, then surface.
        if resp.status_code == 401:
            new_jwt = await provider.refresh_on_401()
            if new_jwt is None:
                return {
                    "ok": False,
                    "error": "auth_required",
                    "message": _LOGIN_HINT,
                }
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {new_jwt}",
                    "Content-Type": "application/json",
                },
            )

    if resp.status_code >= 400:
        try:
            err = resp.json()
            message = err.get("error") or err.get("message") or resp.text
        except (ValueError, json.JSONDecodeError):
            message = resp.text or f"HTTP {resp.status_code}"
        raise RuntimeError(f"generate-leads failed ({resp.status_code}): {message}")

    return resp.json()


# ---------------------------------------------------------------------------
# Read-only — list staged candidates from the CRM via PostgREST.
# ---------------------------------------------------------------------------


@function_tool
async def list_lead_candidates(
    city: str | None = None,
    category: str | None = None,
    website_is_null: bool | None = None,
    min_rating: float | None = None,
    max_rating: float | None = None,
    min_review_count: int | None = None,
    max_review_count: int | None = None,
    status: str = "candidate",
    limit: int = 50,
) -> dict[str, Any]:
    """List staged lead candidates with optional filters.

    Reads from the CRM's `lead_candidates` table via PostgREST. No SerpAPI
    cost. Use this AFTER `request_lead_generation` to inspect what was
    scraped, then pass selected IDs to `promote_lead_candidates`.

    Filter semantics:
      - city/category match `seen_in_search->>city` and `seen_in_search->>category`.
      - website_is_null=True returns rows where the website column is NULL or empty.
      - website_is_null=False returns rows with a non-empty website.
      - min_rating / max_rating are inclusive bounds on `rating` (gte / lte).
      - min_review_count / max_review_count are inclusive bounds on `review_count`
        (gte / lte). Combine them for an ICP band, e.g. min_rating=4.0 +
        max_review_count=30 = "well-rated but still under-served".
      - status='any' disables the status filter; otherwise defaults to 'candidate'.

    Returns: {candidates: [{id, name, phone, website, address, rating,
                             review_count, lead_score, status, seen_in_search}],
              count: int}

    On a missing/expired refresh token, returns a structured error payload
    telling the user to run ``worklogicly-agent login``.
    """
    base_url = os.environ.get("CRM_BASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not base_url:
        raise RuntimeError("CRM_BASE_URL is not set. The agent needs the Supabase project URL.")
    if not anon_key:
        raise RuntimeError(
            "SUPABASE_ANON_KEY is not set. PostgREST requires the project's anon/publishable key as the apikey header."
        )

    provider = _get_provider()
    try:
        jwt = await provider.get_jwt()
    except RefreshTokenExpired:
        return {"ok": False, "error": "auth_required", "message": _LOGIN_HINT}

    limit = max(1, min(int(limit), 200))

    params: list[tuple[str, str]] = [
        (
            "select",
            "id,name,phone,website,address,rating,review_count,lead_score,status,seen_in_search",
        ),
        ("order", "lead_score.desc.nullslast"),
        ("limit", str(limit)),
    ]
    if status and status != "any":
        params.append(("status", f"eq.{status}"))
    if city:
        params.append(("seen_in_search->>city", f"eq.{city}"))
    if category:
        params.append(("seen_in_search->>category", f"eq.{category}"))
    if min_rating is not None:
        params.append(("rating", f"gte.{min_rating}"))
    if max_rating is not None:
        params.append(("rating", f"lte.{max_rating}"))
    if min_review_count is not None:
        params.append(("review_count", f"gte.{min_review_count}"))
    if max_review_count is not None:
        params.append(("review_count", f"lte.{max_review_count}"))
    if website_is_null is True:
        params.append(("or", "(website.is.null,website.eq.)"))
    elif website_is_null is False:
        params.append(("and", "(website.not.is.null,website.neq.)"))

    url = f"{base_url}/rest/v1/lead_candidates"

    def _headers(bearer: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {bearer}",
            "apikey": anon_key,
            "Accept": "application/json",
        }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers=_headers(jwt))

        if resp.status_code == 401:
            new_jwt = await provider.refresh_on_401()
            if new_jwt is None:
                return {"ok": False, "error": "auth_required", "message": _LOGIN_HINT}
            resp = await client.get(url, params=params, headers=_headers(new_jwt))

    if resp.status_code >= 400:
        try:
            err = resp.json()
            message = err.get("message") or err.get("error") or resp.text
        except (ValueError, json.JSONDecodeError):
            message = resp.text or f"HTTP {resp.status_code}"
        raise RuntimeError(f"lead_candidates query failed ({resp.status_code}): {message}")

    rows = resp.json()
    return {"candidates": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Mutating — promote one or more staged candidates into the leads table.
# Gated by the OmniAgents host (NOT in safe_tool_names).
# ---------------------------------------------------------------------------


@function_tool
async def promote_lead_candidates(
    candidate_ids: list[str],
) -> dict[str, Any]:
    """Promote one or more staged candidates into the CRM leads table.

    Calls the CRM's `promote-candidate` edge function once per ID. No SerpAPI
    cost (the scrape already happened). Idempotent — already-promoted
    candidates return their existing lead_id with `already_existed: true`.

    Use this AFTER `list_lead_candidates` has surfaced the rows the user
    wants to keep.

    Returns: {promoted: [{candidate_id, lead_id, already_existed}],
              failed:   [{candidate_id, error}],
              total_requested, total_succeeded}

    On a missing/expired refresh token, returns a structured error payload
    telling the user to run ``worklogicly-agent login``.
    """
    base_url = os.environ.get("CRM_BASE_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("CRM_BASE_URL is not set. The agent needs the Supabase project URL.")
    if not candidate_ids:
        return {"promoted": [], "failed": [], "total_requested": 0, "total_succeeded": 0}

    provider = _get_provider()
    try:
        jwt = await provider.get_jwt()
    except RefreshTokenExpired:
        return {"ok": False, "error": "auth_required", "message": _LOGIN_HINT}

    url = f"{base_url}/functions/v1/promote-candidate"

    def _headers(bearer: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        }

    semaphore = asyncio.Semaphore(5)

    async def _promote_one(
        client: httpx.AsyncClient, candidate_id: str
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        body = {"candidate_id": candidate_id}
        async with semaphore:
            try:
                resp = await client.post(url, json=body, headers=_headers(jwt))
                if resp.status_code == 401:
                    new_jwt = await provider.refresh_on_401()
                    if new_jwt is None:
                        return candidate_id, None, "auth_required"
                    resp = await client.post(url, json=body, headers=_headers(new_jwt))
            except httpx.HTTPError as exc:
                return candidate_id, None, str(exc)
        if resp.status_code >= 400:
            try:
                err = resp.json()
                message = err.get("error") or err.get("message") or resp.text
            except (ValueError, json.JSONDecodeError):
                message = resp.text or f"HTTP {resp.status_code}"
            return candidate_id, None, f"HTTP {resp.status_code}: {message}"
        try:
            return candidate_id, resp.json(), None
        except (ValueError, json.JSONDecodeError) as exc:
            return candidate_id, None, f"invalid JSON response: {exc}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        results = await asyncio.gather(
            *(_promote_one(client, cid) for cid in candidate_ids)
        )

    promoted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for cid, payload, error in results:
        if error is not None or payload is None:
            failed.append({"candidate_id": cid, "error": error or "unknown"})
        else:
            promoted.append(
                {
                    "candidate_id": cid,
                    "lead_id": payload.get("lead_id"),
                    "already_existed": payload.get("already_existed", False),
                }
            )

    if any(f["error"] == "auth_required" for f in failed):
        return {
            "ok": False,
            "error": "auth_required",
            "message": _LOGIN_HINT,
            "promoted": promoted,
            "failed": failed,
            "total_requested": len(candidate_ids),
            "total_succeeded": len(promoted),
        }

    return {
        "promoted": promoted,
        "failed": failed,
        "total_requested": len(candidate_ids),
        "total_succeeded": len(promoted),
    }
