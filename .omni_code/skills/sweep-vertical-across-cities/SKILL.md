---
name: sweep-vertical-across-cities
description: Scrape one vertical across several Rio Grande Valley cities in sequence,
  staging each. Use when the user wants a category covered region-wide ("find roofers
  across the RGV", "plumbers in every valley city", "sweep HVAC across McAllen,
  Edinburg and Mission"). One scrape per city, each capped, budget-aware.
---

# Sweep a vertical across cities

```yaml
# --- skill descriptor (the contract) ---
name: sweep-vertical-across-cities
description: >-
  Run stage-candidates-for-vertical's scrape once per city across a fixed RGV city
  list (or a user-supplied subset), sequentially, one city per turn. Each city is
  capped at 20 and may consume one SerpAPI search unless cached. Stops early on
  budget/auth failure.

when_to_use:
  - "find <category> across the RGV / the whole valley / every city"
  - "sweep <category> across <city>, <city>, and <city>"
  - user wants ONE vertical covered in MULTIPLE cities

# Inputs:
#   vertical (str, required) — the business category
#   cities (list[str], optional) — defaults to the RGV core list below
#   limit (int, optional, default 20) — promote cap per city, hard-capped at 20
#
# Default RGV city list (fixed for determinism):
#   [McAllen, Edinburg, Mission, Pharr, Brownsville, Harlingen, Weslaco, San Juan]
tool_playbook:
  - step: 1
    tool: request_lead_generation
    args:
      city: "{{ cities[i] }}"               # iterate the resolved city list in order
      category: "{{ vertical }}"
      limit: "{{ min(limit | default(20), 20) }}"
    when: "for each city in `cities`, in list order, ONE call per turn"
    note: >-
      Repeat this step per city, sequentially — one request_lead_generation per turn
      message (per the agent's one-mutating-call-per-turn rule). Each is gated.

success_criteria:
  - exactly one request_lead_generation call per city in the resolved list
  - cities are processed in the fixed list order (deterministic)
  - a per-city summary (staged / promoted / cache vs. fresh) is reported

fallback_behavior:
  - on: "a city returns {ok:false, error:'auth_required'}"
    do: Surface the login hint and STOP the sweep (don't attempt remaining cities).
  - on: "a city raises a budget/rate-limit error"
    do: >-
      Report which cities completed, state the budget is exhausted, and STOP. Suggest
      resuming next month or promoting already-staged rows. Do not retry.
  - on: "a city returns 0 candidates"
    do: Note it and continue to the next city (a dry city is not a failure).

stop_conditions:
  - Never exceed the resolved city list — no improvised extra cities.
  - Never raise the per-city limit above 20.
  - Stop the whole sweep immediately on an auth or budget error.
  - One request_lead_generation per turn — never fire several scrapes in one message.
```

## How the agent executes this

1. Resolve `vertical` (required — ask if missing) and the `cities` list. If the user
   named specific cities, use exactly those in the order given; otherwise use the
   fixed RGV core list. Tell the user the plan ("I'll sweep roofers across 8 RGV
   cities, one at a time.").
2. For each city, in order, run `request_lead_generation(city, category=vertical,
   limit=min(limit,20))` — one per turn. Each is gated for approval.
3. After each city, give a one-line result. On an auth or budget error, stop the
   sweep and report progress.
4. When the list is exhausted, give a roll-up: total staged/promoted per city.
