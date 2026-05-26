# Safety-Rails Audit (P2.5)

Source-of-truth citations for every safety rail required by task_plan.md §2.5.
Verified 2026-05-26 (Ricardo, P2.5 worktree). Citations are `file:line` against
the current state of the Phase-2 chain (HEAD on this worktree's branch).

## 1. Admin gate — three independent layers

| Layer | File | Citation | Verified |
|---|---|---|---|
| L1 — RLS on `lead_candidates` | `WorkLogicly-CRM/supabase/migrations/20240525000000_lead_generation_schema.sql` | lines 83–130 (SELECT/INSERT/UPDATE policies gate on `profiles.role in ('system_admin','admin')`; DELETE gates on `role = 'system_admin'`) | ✅ |
| L1 — RLS on `lead_generation_audit` | `WorkLogicly-CRM/supabase/migrations/20240525000000_lead_generation_schema.sql` | lines 167–189 (SELECT + INSERT admin-only; no UPDATE/DELETE → append-only) | ✅ |
| L2 — Edge function `generate-leads` | `WorkLogicly-CRM/supabase/functions/generate-leads/index.ts` | lines 404–429 (JWT fetched via caller-scoped client; profile-role lookup via service-role client; non-admin → 403 at line 427) | ✅ |
| L2 — Edge function `promote-candidate` | `WorkLogicly-CRM/supabase/functions/promote-candidate/index.ts` | lines 118–145 (same pattern: getUser → profiles.role → 403 at line 141) | ✅ |
| L3 — UI hide | `WorkLogicly-CRM/components/LeadsView.tsx` | line 93 (`isAdminRole`); line 124 (`isAdmin`); lines 534, 542, 553, 572, 797 (every Generate / budget / Candidates surface wrapped in `{isAdmin && …}`) | ✅ |

Each layer is independent: bypassing one (e.g. direct HTTP call to the edge
function with a sales JWT) still hits the other two.

## 2. Per-click cap

| Detail | File | Citation |
|---|---|---|
| Hard cap default 20, env `GENERATE_LEADS_MAX_LIMIT` | `WorkLogicly-CRM/supabase/functions/generate-leads/index.ts` | line 59 (`MAX_LIMIT = intEnv("GENERATE_LEADS_MAX_LIMIT", 20)`) |
| `limit = min(client_limit, MAX_LIMIT)` enforcement | same file | lines 447–450 (`Math.max(1, Math.min(MAX_LIMIT, body.limit ?? DEFAULT_LIMIT))`) |

Client also clamps in the agent path (`Lead-Scraper/agents/rgv_lead_scraper/tools/lead_tools.py`)
but the edge-function clamp is the source of truth.

## 3. Per-user rate limit

| Detail | File | Citation |
|---|---|---|
| Default 3/min, env `GENERATE_LEADS_PER_MIN` | `WorkLogicly-CRM/supabase/functions/generate-leads/index.ts` | line 54 (`PER_MIN_LIMIT = intEnv("GENERATE_LEADS_PER_MIN", 3)`) |
| Counts audit rows in last 60s and returns 429 | same file | lines 453–475 (`countAuditInWindow(userId, since=-60s)`; threshold check at 462 → 429) |
| Backing index used | `WorkLogicly-CRM/supabase/migrations/20240525000000_lead_generation_schema.sql` | lines 155–156 (`(user_id, created_at desc)`) |

## 4. Monthly SerpAPI budget

| Detail | File | Citation |
|---|---|---|
| Hard cap default 250, env `GENERATE_LEADS_HARD_CAP` | `WorkLogicly-CRM/supabase/functions/generate-leads/index.ts` | line 57 |
| Soft cap default 230, env `GENERATE_LEADS_SOFT_CAP` | same file | line 56 |
| Monthly counter (current UTC month, `serpapi_called=true`) | same file | lines 310–321 (`countMonthlySerpApiCalls`); called at line 484 |
| Hard-cap enforcement (block even cache hits) | same file | lines 491–500 (`monthlyUsed >= HARD_CAP → 429`) |
| Soft-cap enforcement (block only fresh searches) | same file | lines 524–534 (`!cacheHit && monthlyUsed >= SOFT_CAP → 429`) |
| Backing index for the monthly rollup | `WorkLogicly-CRM/supabase/migrations/20240525000000_lead_generation_schema.sql` | lines 159–160 (`(created_at)`) |
| UI budget badge ("X / 250 this month") | `WorkLogicly-CRM/components/LeadsView.tsx` | line 534 (admin-gated badge); refreshed from every `generateLeads` response's `monthly_usage` |
| UI button disabled at hard cap | `WorkLogicly-CRM/components/LeadsView.tsx` | line 542 ("Generate Leads" button disabled when `budgetUsed >= 250`) |

The "resets on the 1st" copy lives in the friendly error message produced by
`mapEdgeError` (`lib/leadGenerationService.ts:196–203`) for the
`budget_exhausted` code.

## 5. Search cache (14-day default)

| Detail | File | Citation |
|---|---|---|
| Default 14 days, env `GENERATE_LEADS_CACHE_DAYS` | `WorkLogicly-CRM/supabase/functions/generate-leads/index.ts` | line 55 |
| Cache lookup (skipped when `force_refresh=true`) | same file | lines 323–339 (`findCacheHit`); called at lines 502–520 (`!forceRefresh` guard) |
| Backing index | `WorkLogicly-CRM/supabase/migrations/20240525000000_lead_generation_schema.sql` | lines 164–165 (`(lower(city), lower(category), created_at desc)`) |

## 6. Audit row per request

| Detail | File | Citation |
|---|---|---|
| `AuditInsert` shape (all required fields) | `WorkLogicly-CRM/supabase/functions/generate-leads/index.ts` | lines 127–137 (user_id, city, category, requested_limit, serpapi_called, candidates_inserted, leads_promoted, duplicates, error) |
| `writeAudit` helper | same file | lines 341–347 |
| Audit written on every exit path | same file | SerpAPI failure: line 550; upsert failure: 628; pick failure: 663; lead insert failure: 722; success: 773 |
| `created_at` defaulted in schema | `WorkLogicly-CRM/supabase/migrations/20240525000000_lead_generation_schema.sql` | line 142 (`timestamptz default now()`) |

## 7. Feature flag

| Detail | File | Citation |
|---|---|---|
| Env name + default | both edge functions: `ENABLE_LEAD_GENERATION` (default `"false"`; must equal case-insensitive `"true"` to enable) | `generate-leads/index.ts:63–65` (`isFeatureEnabled` helper); `promote-candidate/index.ts:60–62` |
| Short-circuit to 503 in `generate-leads` | `WorkLogicly-CRM/supabase/functions/generate-leads/index.ts` | lines 359–366 (checked after method validation, before auth + DB) |
| Short-circuit to 503 in `promote-candidate` | `WorkLogicly-CRM/supabase/functions/promote-candidate/index.ts` | lines 83–90 |
| Client maps 503 → `feature_disabled` friendly message | `WorkLogicly-CRM/lib/leadGenerationService.ts` | line 83 (new `feature_disabled` code in `LeadGenErrorCode`); lines 179–186 (mapping branch) |

`promote-candidate` is gated by the same flag because it is the second
mutation surface for the lead-generation feature; disabling generation
without disabling staged-promotion would leave admins able to keep moving
candidates into `leads` while the rest of the feature is off.

## Verification recipe (P2.5, run in WorkLogicly-CRM)

```bash
# 1. With flag unset (default), both edge functions return 503.
supabase functions serve generate-leads
curl -s -X POST -H 'Authorization: Bearer <admin-jwt>' \
  -H 'Content-Type: application/json' \
  -d '{"city":"McAllen","category":"plumbers"}' \
  http://localhost:54321/functions/v1/generate-leads
# → {"error":"Lead generation is currently disabled"} (503)

# 2. With flag on, the normal flow proceeds (admin gate, rate limit, etc).
ENABLE_LEAD_GENERATION=true supabase functions serve generate-leads
# repeat curl → either 200 or whichever next rail trips (e.g. 401 if no JWT).

# 3. Rate-limit double-click test.
GENERATE_LEADS_PER_MIN=1 ENABLE_LEAD_GENERATION=true supabase functions serve generate-leads
# first call OK; second within 60s → 429 "Rate limit: max 1 requests per minute".
```

The P2.6 verification phase exercises the rails end-to-end (admin-vs-sales
JWT, double-click 429, soft/hard budget thresholds with backfilled audit
rows, cache hit vs force_refresh). This audit only confirms the rails *exist*
at the documented locations.
