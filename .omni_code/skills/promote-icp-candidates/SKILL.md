---
name: promote-icp-candidates
description: Promote staged candidates that match an Ideal-Customer-Profile filter —
  any combination of city, category, website present/absent, rating band, and review
  band. Use when the user describes WHO to promote by attributes ("promote the
  well-rated McAllen roofers with under 30 reviews", "add the no-website plumbers
  rated 4+", "promote low-rated landscapers"). Not for fresh scrapes.
---

# Promote ICP candidates

```yaml
# --- skill descriptor (the contract) ---
name: promote-icp-candidates
description: >-
  One parametrized promotion skill. Build an Ideal-Customer-Profile filter from any
  combination of dimensions, list the matching staged rows, and promote exactly
  those. Every dimension is pushed to the list_lead_candidates query — fully
  server-side and deterministic, no client-side guessing.

when_to_use:
  - "promote the <quality> <category> in <city>" where quality is an attribute band
  - "add the no-website / has-website <category> rated <X>+ / under <Y> reviews"
  - "promote low-rated / high-review / under-served candidates"
  - user targets a SUBSET of already-staged rows by attributes (not by name, not a scrape)

# Inputs — all optional, composable. Omit a dimension to leave it unfiltered.
#   city            (str)   — seen_in_search.city
#   category        (str)   — seen_in_search.category
#   website         (enum)  — "none" | "has" | "any" (default "any")
#   min_rating      (float) — rating floor  (well-rated)
#   max_rating      (float) — rating ceiling (poorly-rated)
#   min_review_count(int)   — reviews floor (established / high-review)
#   max_review_count(int)   — reviews ceiling (under-served / low-review)
tool_playbook:
  - step: 1
    tool: list_lead_candidates
    args:
      city: "{{ city | default(omit) }}"
      category: "{{ category | default(omit) }}"
      website_is_null: "{{ true if website == 'none' else (false if website == 'has' else omit) }}"
      min_rating: "{{ min_rating | default(omit) }}"
      max_rating: "{{ max_rating | default(omit) }}"
      min_review_count: "{{ min_review_count | default(omit) }}"
      max_review_count: "{{ max_review_count | default(omit) }}"
      status: candidate
      limit: 50
    when: always
    note: >-
      Every ICP dimension is a query param, so the returned set IS the eligible set.
      Do NOT apply any additional filtering after this call — the query already did it.
  - step: 2
    tool: promote_lead_candidates
    args:
      candidate_ids: "{{ step1.result.candidates | map(attribute='id') | list }}"
    when: "step1.result.count > 0"
    note: Promote exactly the ids step 1 returned — no more, no fewer.

success_criteria:
  - every candidate_id sent to step 2 came from step 1's result
  - the count promoted + already-existed + failed == step1.result.count
  - no row outside the ICP filter was promoted (guaranteed: filtering is server-side)

fallback_behavior:
  - on: "step 1 returns {ok:false, error:'auth_required'}"
    do: Surface the login hint verbatim. Do NOT promote. Stop.
  - on: "step 1 returns count == 0"
    do: >-
      Tell the user no staged rows match that ICP. State the filter you used so they
      can loosen it. Promote nothing. Do NOT scrape to fill the gap.
  - on: "step 2 returns failed[] entries"
    do: Report promoted vs. failed ids; do not retry.

stop_conditions:
  - Never add a filter dimension the user did not ask for, and never drop one they did.
  - Never promote ids not present in step 1's result.
  - Never run request_lead_generation — this skill only promotes already-staged rows.
  - If the user named a specific business (not an attribute), this is the wrong
    skill — use promote-selected-candidates instead.
```

## How the agent executes this

1. Translate the user's description into ICP inputs: map "no website" → `website='none'`,
   "has a website" → `website='has'`; "rated 4+" → `min_rating=4.0`; "low-rated" →
   `max_rating` (pick the stated ceiling); "under N reviews" → `max_review_count=N`;
   "at least N reviews / established" → `min_review_count=N`. Carry `city`/`category`
   through. Leave anything unstated unfiltered.
2. Run step 1: `list_lead_candidates` with exactly those params. This is free.
3. If `count == 0`, report the filter you used and stop. If auth error, surface and stop.
4. Otherwise run step 2: `promote_lead_candidates` with **all** ids from step 1.
5. Summarize: how many promoted vs. already existed vs. failed, and restate the ICP.

The eligible set is whatever the query returns — never widen or narrow it afterward.
