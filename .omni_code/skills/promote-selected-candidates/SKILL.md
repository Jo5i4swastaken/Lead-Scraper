---
name: promote-selected-candidates
description: Promote a specific set of staged candidates the user named by business
  name or by their position in a recent list (e.g. promote the first and third one,
  or add Miravalle and Lone Star Roofing). Use when the user picks individual
  businesses, not an attribute band. Resolves each pick to a real candidate id before
  promoting.
---

# Promote selected candidates

```yaml
# --- skill descriptor (the contract) ---
name: promote-selected-candidates
description: >-
  Promote the exact staged rows the user pointed at by name or list position. The
  skill resolves every pick to a real lead_candidates id (re-listing if needed) so
  it never guesses an id, then promotes only the resolved set.

when_to_use:
  - "promote #1, #3, and the fifth one"
  - "add <Business Name> and <Business Name> to leads"
  - "promote those two" (referring to rows in a list shown earlier this conversation)
  - user selects INDIVIDUAL businesses, not a filter band (that's promote-icp-candidates)

# Inputs:
#   picks (list[str], required) — the names / list-positions the user named
#   city, category (str, optional) — to scope the lookup if a re-list is needed
tool_playbook:
  - step: 1
    tool: list_lead_candidates
    args:
      city: "{{ city | default(omit) }}"
      category: "{{ category | default(omit) }}"
      status: candidate
      limit: 50
    when: "no recent list_lead_candidates result already contains every pick"
    note: >-
      Skip if a list from earlier this turn/conversation already holds all the named
      rows. Otherwise list so we can resolve names/positions to ids.
  - step: 2
    tool: promote_lead_candidates
    args:
      candidate_ids: "{{ resolved_ids }}"   # ids matched from picks against the list
    when: "resolved_ids is non-empty"
    note: Promote only the ids resolved from the user's explicit picks.

success_criteria:
  - every id promoted maps to a business the user actually named
  - picks that could not be resolved are reported back, not silently dropped
  - no id was invented — each came from a list result

fallback_behavior:
  - on: "a pick can't be matched to any staged row"
    do: >-
      Tell the user that pick wasn't found among staged candidates (suggest they
      re-run a scrape or check the name/spelling). Promote the ones that resolved.
  - on: "step 1/2 returns {ok:false, error:'auth_required'}"
    do: Surface the login hint verbatim. Stop.
  - on: "ambiguous pick (two staged rows share a name)"
    do: Ask the user which one (show address/phone to disambiguate). Do not promote a guess.

stop_conditions:
  - NEVER invent or guess a candidate_id — only promote ids matched from a list result.
  - Never promote rows the user did not name.
  - Never run request_lead_generation — this skill promotes already-staged rows only.
```

## How the agent executes this

1. Collect the user's picks (names and/or list positions like "#1").
2. If you already have a recent `list_lead_candidates` result containing all of them,
   reuse it. Otherwise run step 1 to fetch the staged rows (scoped by city/category
   if known).
3. Resolve each pick to a candidate `id`. If a pick is ambiguous or missing, ask /
   report rather than guess.
4. Run step 2: `promote_lead_candidates(candidate_ids=[resolved ids])`.
5. Summarize what promoted, what already existed, and any unresolved picks.
