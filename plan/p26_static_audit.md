# P2.6 Static Audit — Phase 2 End-to-End Verification

**Lead:** Tomás · **Worktree:** `db3a1` (WorkLogicly-CRM, detached HEAD on P2.5 tip `b88b2b5`)
**Date:** 2026-05-26
**Mode:** Static-only sweep (subagent-driven). Live verification deferred to CTO per round-of-decision 2026-05-26 (user will execute interactive checks 1-13 with prepped scripts from `scripts/p26_verification/` in the CRM worktree).

## Chain integrity — PASS

`git log --oneline` in CRM worktree shows the full P2.1 → P2.5 chain commit-by-commit:

```
b88b2b5 P2.5: ENABLE_LEAD_GENERATION feature flag + 503 mapping
0d23d83 P2.4b follow-up: chat-drawer UX polish + candidate-staging filters
1fc92cf P2.4b: agent chat drawer for lead-scraping (CRM side)
c19dd18 P2.4a follow-up: CORS Allow-Headers echo + non-partial leads_external_id index
4dbb408 P2.4a hotfix: decouple lead-gen CORS from project-wide ALLOWED_ORIGIN
2cc3f89 P2.4a: edge function CORS — support comma-separated ALLOWED_ORIGIN
85a8d4d P2.4a: lead generation form + candidates staging tab
a833cb2 P2.3: leadGenerationService + promote-candidate edge function
4e1e6fe P2.2: generate-leads edge function
0506ae7 P2.1: Lead generation schema (leads extension + staging + audit)
```

All key artifacts present: `supabase/functions/generate-leads/index.ts`, `supabase/functions/promote-candidate/index.ts`, `supabase/migrations/20240525000000_lead_generation_schema.sql`, `supabase/migrations/20240526000000_leads_external_id_unique_non_partial.sql`, `components/agent-chat/{AgentChatPanel,ChatInput,ChatMessages,ToolApprovalCard,ToolTraceRow}.tsx`, `lib/leadGenerationService.ts`.

## Static-audit results (4 subagent reviewers, parallel)

### Headline

| Concern | Verdict | Source |
|---|---|---|
| Admin gate (3 layers: UI / edge / RLS) | **PASS** | Security review |
| `ENABLE_LEAD_GENERATION` flag (default OFF, both fns, 503 short-circuit) | **PASS** | Cross-cutting review |
| Audit row on every exit path | **PASS-with-nit** | Cross-cutting review |
| Per-click cap (server-side `min(limit, MAX_LIMIT=20)`) | **PASS** | Cross-cutting + edge review |
| `monthly_usage.used` post-increment in response | **PASS** | Cross-cutting review |
| Two-stage write (candidates → top-N → leads with `ignoreDuplicates`) | **PASS** | Edge review |
| Field correctness (D2 fix, place_id-skip, frozen contract) | **PASS** | Edge review |
| Realtime subscriptions (leads + candidates) | **PASS** | Frontend review |
| Promote-from-staging (no second SerpAPI call) | **PASS** | Frontend review |
| Error UX (friendly toasts, no stack traces) | **PASS** | Frontend review |
| Chat drawer (lifted state, WS survives nav, approval filter) | **PASS** | Frontend review |
| Camel↔snake transforms incl. numeric coercion | **PASS** | Frontend review |
| Backoff port (base 0.8 × 2^n, cap 20s, jitter, 5 attempts) | **PASS** | Edge review |
| Rate-limit query exploits `(user_id, created_at desc)` index | **PASS** | Edge review |
| **Cross-city `seen_in_search` merge (P2.6 check 13)** | **🔴 FAIL — BLOCKER** | Edge + cross-cutting review (independent) |
| Search-cache index utilization (`ilike` vs `lower()` functional index) | **PARTIAL** | Edge review |
| `LeadQualityScorer` weak_presence clause vs Python source | **PARTIAL** | Edge review |
| 503 body missing machine-readable `code:"feature_disabled"` | **PARTIAL** | Edge review |
| Dismissed candidates have no UI affordance to view | **PARTIAL** | Frontend review |
| Hard-cap message does not mention "resets on the 1st" | **PARTIAL** | Frontend review |
| Soft-warning (≥230) is color-only, no textual banner | **PARTIAL** | Frontend review |

**Totals:** 13 PASS / 1 FAIL (blocker) / 6 PARTIAL.

### Blocker — cross-city `seen_in_search` overwrite (P2.6 check 13)

**Both** the edge-function code-reviewer and the cross-cutting code-reviewer independently flagged this:

> `supabase/functions/generate-leads/index.ts:619-625` upserts candidates with `onConflict: 'external_id'` using PostgREST's default UPDATE-all-fields behaviour. When the same `place_id` appears in two different `(city, category)` scrapes, the second upsert **overwrites** `seen_in_search` with the new `{city, category, query, scraped_at}` object — the first observation is lost. The header comment at `:17` claims merge semantics; the code does not match.

Compounding effect at `:656-657`: the top-N pick filter selects candidates by `seen_in_search->>city = $city AND seen_in_search->>category = $category`. Once the row has been relabeled by a second-city scrape, the original city's pick can no longer find it.

**Concurrency risk:** even a client-side select-then-merge fix is racy. Two simultaneous requests for the same business in different cities both read the pre-update state, both merge into their own local copy, and the second write loses the first's observation. A correct fix needs server-side jsonb append (RPC or raw SQL) and likely a schema migration to model `seen_in_search` as an array (`jsonb` array, not a single object).

**Owner:** Cristian (P2.2 edge function) — the code that overwrites is in his commit `4e1e6fe`. The unique-key choice (full unique, allows append) is correct from Alejandro's P2.1.

**Recommendation:** do NOT flip `enable_lead_generation=true`. Do NOT merge the Phase 2 chain to `main`. Open a hotfix phase (call it `P2.5c` to keep the chain shape) that:
1. Changes `seen_in_search` to a jsonb array (migration).
2. Introduces an SQL function or RPC for the upsert path that appends instead of overwrites.
3. Updates the pick-by-city filter to use jsonb containment (`seen_in_search @> '[{"city": $1, "category": $2}]'`).
4. Re-runs P2.6 check 13 + a same-city-rescrape regression.

### Other PARTIAL items — recommendations

| # | Item | Recommendation |
|---|---|---|
| 1 | `LeadQualityScorer.weak_presence` clause vs Python source | Diff `generate-leads/index.ts:222-227` against `src/lead_scraper/scorers/lead_quality.py`. If divergence, file as part of the P2.5c hotfix. Otherwise close PARTIAL → PASS. |
| 2 | 503 body missing `code:"feature_disabled"` | Two-line edge-function patch. Client already maps 503 by status OR substring (`leadGenerationService.ts:179-186`), so the gap is cosmetic. Defer to follow-up. |
| 3 | Cache `ilike` may seq-scan at 10k+ audit rows | Either switch to `.eq('city', city.toLowerCase())` (requires storing city/category lower-cased in audit rows — migration) or change the index to plain `(city, category, created_at desc)`. Current 250/month plan means audit grows ≤3000 rows/year — non-issue for v1. Reopen if usage scales. |
| 4 | Dismissed candidates can't be viewed from UI | Add a "Show dismissed" toggle to the Candidates tab filter row. Owner: Salvador (P2.4a) or follow-up to him. Not a v1 blocker per round-4 ("dismiss is destructive but reversible from DB"). |
| 5 | No "resets on the 1st" text on hard-cap | One-line tooltip change on the disabled CTA at `LeadsView.tsx:545`. Owner: Salvador. Follow-up. |
| 6 | No textual soft-warning at ≥230 | Add an amber banner above the leads table when `budgetUsed >= 230 && budgetUsed < 250`. Owner: Salvador. Follow-up. |

### Cross-cutting risks (works but fragile)

1. **Hard-cap check ordering**: cache hits past the hard cap are incorrectly blocked at `generate-leads/index.ts:491` (runs before cache lookup at `:506`). The comment at `:522-523` says this shouldn't happen. Code/intent disagree. Recommended fix: move hard-cap-only-blocks-serpapi after cache check, like the soft-cap.
2. **`writeAudit` swallows errors** (`generate-leads/index.ts:346` — `console.error` only). If the audit table itself becomes unwritable, the function still returns 200; monthly counter drifts; rate-limit allows extra calls. Risk is low (audit table is rarely the failure point) but the silent path is dangerous. Recommend: bubble write-audit failure on the success path to a 500.
3. **`findCacheHit` does not escape `%`/`_`** in the `ilike` predicate. A user-supplied category like `tile%setters` would broaden the cache match. Low-impact (admin-only, no security boundary crossed) but worth a one-line sanitize.
4. **Realtime delivery race vs success toast.** Server returns 200 + `monthly_usage` before realtime emits the new lead rows. UI toast shows "3 leads added" but leads table may stay empty for several seconds. Consider explicit `await fetchLeads()` post-success or a "syncing…" indicator.
5. **AgentChatPanel has no internal role guard** — safe today (only `agentChat.toggle()` call site is admin-gated and `isOpen` starts false), but a future caller from a non-admin surface would bypass. Defensive add-on for P2.7.
6. **Five post-user 5xx paths don't write audit** (`generate-leads/index.ts:418, 472, 488, 517` + env-misconfig at 383/389). All are rare (Supabase env/profile-lookup failures). Nit; not a blocker.

## Live-verification readiness

The static audit cannot replace checks 1-13 from §2.6 of the task plan. The CTO will execute live verification using the prepped bundle at `WorkLogicly-CRM/scripts/p26_verification/`:

- `README.md` — order-of-operations and prerequisites (Supabase started, env vars, admin/sales users, SerpAPI key).
- `01_local_infra.sh` — `supabase start` + `supabase functions serve generate-leads` + smoke probes.
- `02_admin_gate_curl.sh` — admin JWT happy-path + sales JWT 403 + missing-bearer 401.
- `03_rls_direct_insert.sql` — SQL to test RLS blocks direct inserts.
- `04_budget_backfill.sql` — backfill 230/250 audit rows to test soft/hard caps.
- `05_dedupe_crosscity.sh` — runs the McAllen-then-Edinburg pair (only after the blocker above is fixed).
- `06_field_correctness.sql` — spot-check the 5 most-recently inserted leads against the raw SerpAPI trace files.
- `checklist.md` — every check 1-13 with PASS/FAIL columns to fill in.

## Recommendation

**Do NOT flip `enable_lead_generation=true`.** **Do NOT merge the Phase 2 chain to `main`.** The cross-city `seen_in_search` overwrite is a documented contract violation that P2.6 check 13 will fail on. Even if the live-verification run somehow papered over it (e.g. CTO doesn't trigger the cross-city scenario), shipping with this bug means staging silently corrupts every time a business surfaces in two cities — and the same code path is exercised on every same-business re-scrape, which is the explicit growth model for the budget design.

**Suggested next step:** open `P2.5c` (hotfix to Cristian's P2.2). Scope:
- Migration: `seen_in_search` jsonb array (or new join table `lead_candidate_searches`).
- Edge function: server-side jsonb append via RPC.
- Pick filter: `@>` containment.
- Regression test in `scripts/p26_verification/05_dedupe_crosscity.sh`.

Once P2.5c is done, this static audit re-runs in 5 minutes (just check 13 + diff weak_presence) and the CTO proceeds with the live bundle.
