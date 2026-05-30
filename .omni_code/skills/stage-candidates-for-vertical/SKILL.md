---
name: stage-candidates-for-vertical
description: Scrape one business vertical in one city and stage the results into the
  CRM lead_candidates table, capped at 20. Use when the user wants to find/pull/scrape
  a category of businesses in a city ("find plumbers in McAllen", "scrape RGV
  roofers", "stage HVAC leads in Mission") and expects a fresh search.
---

# Stage candidates for a vertical

```yaml
# --- skill descriptor (the contract) ---
name: stage-candidates-for-vertical
description: >-
  Scrape one (city, vertical) pair via the CRM generate-leads flow, stage the full
  batch (~20) into lead_candidates, and surface what was staged. Fixed query
  template, result cap of 20.

when_to_use:
  - "find <category> in <city>"            # "find plumbers in McAllen"
  - "scrape / pull / get me <category> leads in <city>"
  - "stage <category> for <city>"
  - user wants a FRESH search of a vertical (not a review of already-staged rows)

# Inputs the caller supplies (resolved into the {{ }} templates below):
#   city      (str, required)
#   vertical  (str, required)  — the business category, e.g. "plumbers"
#   limit     (int, optional, default 20) — how many of the staged batch to promote;
#             hard-capped at 20 by the args template.
tool_playbook:
  - step: 1
    tool: request_lead_generation
    args:
      city: "{{ city }}"
      category: "{{ vertical }}"
      limit: "{{ min(limit | default(20), 20) }}"
    when: always
    note: >-
      The ONLY scrape in this skill. Stages all ~20 maps results into
      lead_candidates and promotes the top `limit`. May consume one SerpAPI search
      unless the same (city, vertical) was scraped in the last 14 days (cache = free).
  - step: 2
    tool: list_lead_candidates
    args:
      city: "{{ city }}"
      category: "{{ vertical }}"
      status: candidate
      limit: 20
    when: "step1.result.candidates_scraped > 0 or step1.result.source == 'cache'"
    note: >-
      Free read-back so the user sees the staged batch with ids for later promotion.
      Skip if step 1 returned an error envelope.

success_criteria:
  - step 1 returned an envelope with candidates_scraped >= 1 OR source == 'cache'
  - step 2 returned candidates whose seen_in_search matches (city, vertical)
  - no more than ONE request_lead_generation call was made

fallback_behavior:
  - on: "step 1 returns {ok:false, error:'auth_required'}"
    do: Surface the login hint verbatim. Do NOT call list_lead_candidates. Stop.
  - on: "step 1 raises a budget/rate-limit error (monthly SerpAPI budget exhausted)"
    do: >-
      Tell the user the budget is exhausted and suggest reviewing existing staged
      rows with a list-only flow instead of scraping. Do NOT retry the scrape.
  - on: "step 1 succeeds but candidates_scraped == 0 (no maps results)"
    do: Report zero results for that (city, vertical). Do not promote anything.

stop_conditions:
  - Never call request_lead_generation more than once per invocation.
  - Never raise `limit` above 20.
  - Never invent a city or vertical — if either is missing, ask one clarifying
    question instead of guessing, and do not start the playbook until both are known.
  - Never promote candidates here — staging/promotion of a filtered subset is the
    job of a different skill (see promote-no-website-candidates).
```

## How the agent executes this

1. Resolve `city` and `vertical` from the user's request. If either is missing, ask
   one clarifying question and stop — do not begin the playbook.
2. Run step 1: `request_lead_generation(city, category=vertical, limit=min(limit,20))`.
   This is gated — the user approves it. Wait for the result.
3. If step 1 returned an auth/budget error, follow `fallback_behavior` and stop.
4. Otherwise run step 2: `list_lead_candidates(city, category=vertical, status='candidate', limit=20)`
   and present the staged rows compactly, **including each candidate's `id`** so they
   can be promoted later.
5. Summarize in plain language (fresh vs. cache, how many staged/promoted).

Behavior rules are non-negotiable: one scrape only, cap 20, never guess inputs.
