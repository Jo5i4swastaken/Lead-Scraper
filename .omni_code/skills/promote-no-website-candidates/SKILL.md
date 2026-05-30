---
name: promote-no-website-candidates
description: Promote ONLY the staged candidates that have no website into the CRM
  leads table. Use when the user wants to keep/promote the no-website businesses from
  what was already scraped ("promote the ones with no website", "add the McAllen
  roofers without a site", "no-website candidates only"). Never promotes a row that
  has a website.
---

# Promote no-website candidates

```yaml
# --- skill descriptor (the contract) ---
name: promote-no-website-candidates
description: >-
  Filter the staged lead_candidates down to website == null/empty and promote only
  those into leads. A targeting recipe for the "businesses without a web presence"
  outreach play. Hard guarantee: a candidate with a non-empty website is never
  promoted.

when_to_use:
  - "promote the ones with no website"
  - "add the <city> <category> without a site / without a website"
  - "no-website candidates only"
  - user wants to promote a website-less SUBSET of already-staged rows (no new scrape)

# Inputs the caller supplies:
#   city      (str, optional)  — narrows the staged batch
#   category  (str, optional)  — narrows the staged batch
# (No `limit` input changes the filter; the website==null filter is the whole point.)
tool_playbook:
  - step: 1
    tool: list_lead_candidates
    args:
      city: "{{ city | default(omit) }}"
      category: "{{ category | default(omit) }}"
      website_is_null: true          # <-- the defining filter, applied at query level
      status: candidate
      limit: 50
    when: always
    note: >-
      Free read. website_is_null=true makes PostgREST return only rows where website
      IS NULL or empty, so non-website rows never enter the candidate set.
  - step: 2
    tool: promote_lead_candidates
    args:
      candidate_ids: "{{ step1.result.candidates | selectattr('website', 'falsy') | map(attribute='id') | list }}"
    when: "step1.result.count > 0"
    note: >-
      Promote exactly the ids from step 1. The selectattr('website','falsy') guard is
      a SECOND defense: even if the query returned a websited row, it is dropped here.

success_criteria:
  - every candidate_id passed to step 2 came from a step-1 row with an empty/null website
  - step 2's promoted[] count + already-existed count == number of ids submitted minus failures
  - no row with a non-empty website appears in the promoted set

fallback_behavior:
  - on: "step 1 returns {ok:false, error:'auth_required'}"
    do: Surface the login hint verbatim. Do NOT call promote_lead_candidates. Stop.
  - on: "step 1 returns count == 0"
    do: >-
      Tell the user there are no no-website candidates matching the filter. Promote
      nothing. Stop. (Do not fall back to scraping or to promoting websited rows.)
  - on: "step 2 returns some failed[] entries"
    do: Report which candidate_ids promoted vs. failed; do not retry websited rows.

stop_conditions:
  - NEVER promote a candidate whose website is non-empty — this is the skill's
    contract. Both the website_is_null=true query filter AND the selectattr falsy
    guard must hold; if either is bypassed, abort rather than promote.
  - Never run a new scrape (request_lead_generation) — this skill only promotes
    already-staged rows.
  - Never invent candidate_ids — only ids returned by step 1 may be promoted.
```

## How the agent executes this

1. Run step 1: `list_lead_candidates(..., website_is_null=true, status='candidate')`
   with whatever `city`/`category` the user named. This is free and needs no approval.
2. If it returns `count == 0`, tell the user there are no website-less candidates and
   stop — do not promote anything.
3. Build the promotion set from step 1's rows. As a second guard, drop any row whose
   `website` is non-empty even if the query returned it. The remaining ids are the
   only ones eligible.
4. Run step 2: `promote_lead_candidates(candidate_ids=[...])`. This is gated — the
   user approves it.
5. Summarize what promoted vs. failed, and confirm every promoted row had no website.

The contract is absolute: **a candidate with a website is never promoted by this
skill.** If you cannot prove a row's website is empty, do not include it.
