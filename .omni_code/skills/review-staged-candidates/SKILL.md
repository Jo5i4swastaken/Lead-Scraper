---
name: review-staged-candidates
description: Show what's already staged in lead_candidates with any combination of
  filters, read-only. Use when the user wants to browse/inspect/see staged rows
  ("show me staged roofers in Mission", "what no-website plumbers do we have rated
  4+", "list everything staged") without promoting or scraping. Surfaces ids for
  later promotion.
---

# Review staged candidates

```yaml
# --- skill descriptor (the contract) ---
name: review-staged-candidates
description: >-
  Read-only browse of the lead_candidates table with optional filters. No SerpAPI
  cost, no approval gate, no mutation. Presents rows compactly WITH their ids so the
  user can hand them to a promotion skill next.

when_to_use:
  - "show me / list / what staged <category> do we have in <city>"
  - "browse staged candidates rated over 4 with no website"
  - "how many candidates are staged for <vertical>"
  - user wants to SEE staged rows, not promote or scrape them

# Inputs — all optional, passed straight through to the read:
#   city, category, website ("none"|"has"|"any"), min_rating, max_rating,
#   min_review_count, max_review_count, limit
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
      limit: "{{ limit | default(50) }}"
    when: always
    note: The only call. Free, ungated, read-only.

success_criteria:
  - returned rows are presented compactly including each row's id
  - the filter used is stated back to the user
  - no mutation tool was called

fallback_behavior:
  - on: "step 1 returns {ok:false, error:'auth_required'}"
    do: Surface the login hint verbatim. Stop.
  - on: "step 1 returns count == 0"
    do: Tell the user nothing matches that filter and restate it so they can loosen it.

stop_conditions:
  - NEVER call a mutating tool from this skill — no promote, no scrape. Read-only.
  - If the user then asks to promote what they're seeing, switch to a promotion skill.
```

## How the agent executes this

1. Map the user's words to filter inputs (same mapping as the ICP skill: "no website"
   → `website='none'`, "rated 4+" → `min_rating`, etc.).
2. Run step 1: `list_lead_candidates` with those filters. Free, no approval.
3. Present the rows compactly — name, rating, review_count, website (yes/no), and the
   `id`. Restate the filter you applied.
4. Offer the natural next step (promote a subset) but do NOT promote here.
