---
name: preflight-check
description: Confirm the agent is correctly configured and authenticated before doing
  real work, and report SerpAPI budget status. Use when the user asks "are you set
  up / connected / ready", "which CRM are you writing to", "how much budget is left",
  or when a previous call failed and you need to diagnose config/auth. Read-only.
---

# Preflight check

```yaml
# --- skill descriptor (the contract) ---
name: preflight-check
description: >-
  Read-only health check. Reports which CRM the agent targets, whether the admin JWT
  is present/valid, and (when surfaced) remaining SerpAPI budget — so the user knows
  the agent is ready before spending a gated, possibly-paid call.

when_to_use:
  - "are you set up / connected / ready to go"
  - "which CRM / project are you writing to"
  - "how much SerpAPI budget / searches do we have left"
  - a prior tool call failed and the cause (config vs. auth vs. budget) is unclear

# No inputs.
tool_playbook:
  - step: 1
    tool: get_settings_summary
    args: {}
    when: always
    note: >-
      Returns crm_base_url, endpoints, anon-key configured?, refresh-token configured?,
      and access-token seconds remaining. Never contains secrets.

success_criteria:
  - the user is told the target CRM, auth readiness, and (if known) budget remaining
  - any missing piece (unset URL, missing/expired token) is called out with the fix

fallback_behavior:
  - on: "crm_base_url is '<unset>' or anon key not configured"
    do: Tell the user the agent isn't pointed at a CRM yet and which env var is missing.
  - on: "refresh token missing/expired (access-token seconds null or auth_error present)"
    do: Tell the user to run `worklogicly-agent login`, then retry their request.

stop_conditions:
  - NEVER call a scraping or promotion tool from this skill — diagnostics only.
  - Never print token contents or secrets; report booleans/seconds only.
```

## How the agent executes this

1. Run step 1: `get_settings_summary`. Free, read-only.
2. Report in plain language: the CRM base URL, whether auth is ready (refresh token
   present, access token valid), and budget remaining if present in the summary.
3. If anything's missing, name the specific fix (set `CRM_BASE_URL`, run
   `worklogicly-agent login`, etc.). Do not attempt any scrape/promote here.
