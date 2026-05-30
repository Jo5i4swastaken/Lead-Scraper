---
name: acquire-no-website-leads
description: End-to-end play — scrape a vertical in a city, then promote only the
  results that have no website, in one workflow. Use when the user wants fresh
  no-website leads from scratch ("find McAllen roofers without a website and add
  them", "get me no-website plumbers in Mission"). Composes a fresh scrape with the
  no-website promotion filter.
---

# Acquire no-website leads (end-to-end)

```yaml
# --- skill descriptor (the contract) ---
name: acquire-no-website-leads
description: >-
  The headline acquisition workflow. Runs a fresh scrape for a (city, vertical),
  then filters the freshly-staged batch to website==null/empty and promotes only
  those. Equivalent to stage-candidates-for-vertical followed by
  promote-no-website-candidates, sequenced as one play.

when_to_use:
  - "find <category> in <city> without a website and add them"
  - "get me no-website <category> leads in <city>" (implies a FRESH scrape)
  - user wants website-less leads but nothing is staged yet (needs a scrape first)

# Depends on: stage-candidates-for-vertical (scrape), promote-no-website-candidates
# (filter+promote). Read both if their rules are unclear.
#
# Inputs:
#   city (str, required), vertical (str, required)
tool_playbook:
  - step: 1
    tool: request_lead_generation
    args:
      city: "{{ city }}"
      category: "{{ vertical }}"
      limit: 20
    when: always
    note: >-
      Fresh scrape — stages ~20 into lead_candidates. May cost one SerpAPI search
      unless cached. Gated for approval. (limit=20 just maximizes the staged batch;
      the real promotion set is decided by the no-website filter in step 2-3.)
  - step: 2
    tool: list_lead_candidates
    args:
      city: "{{ city }}"
      category: "{{ vertical }}"
      website_is_null: true
      status: candidate
      limit: 50
    when: "step1 did not return an auth/budget error"
    note: Pull the freshly-staged rows that have no website. Free.
  - step: 3
    tool: promote_lead_candidates
    args:
      candidate_ids: "{{ step2.result.candidates | map(attribute='id') | list }}"
    when: "step2.result.count > 0"
    note: Promote exactly the website-less ids from step 2. Gated.

success_criteria:
  - exactly one fresh scrape ran (step 1)
  - every promoted row had an empty/null website (enforced by website_is_null=true)
  - a clear summary of scraped -> no-website found -> promoted is reported

fallback_behavior:
  - on: "step 1 returns auth_required"
    do: Surface the login hint. Stop before listing/promoting.
  - on: "step 1 budget/rate-limit error"
    do: >-
      Report the budget is exhausted. If the user wants, fall back to
      promote-no-website-candidates against whatever is ALREADY staged (no new scrape).
  - on: "step 2 returns count == 0"
    do: Tell the user the scrape found no website-less businesses for that vertical. Promote nothing.

stop_conditions:
  - Never call request_lead_generation more than once.
  - NEVER promote a row with a non-empty website — the website_is_null=true filter is the contract.
  - Never raise the scrape limit above 20.
  - If the user only wants to promote from ALREADY-staged rows (no fresh search),
    this is the wrong skill — use promote-no-website-candidates.
```

## How the agent executes this

1. Resolve `city` and `vertical` (ask if either is missing). Tell the user the plan
   ("I'll scrape McAllen roofers, then promote just the ones with no website.").
2. Step 1 — `request_lead_generation(city, vertical, limit=20)`. Gated. On auth/budget
   error, follow the fallback and stop.
3. Step 2 — `list_lead_candidates(city, vertical, website_is_null=true)`. Free. If zero,
   report and stop.
4. Step 3 — `promote_lead_candidates` with the website-less ids. Gated.
5. Summarize the funnel: scraped → no-website found → promoted, and confirm every
   promoted row had no website.
