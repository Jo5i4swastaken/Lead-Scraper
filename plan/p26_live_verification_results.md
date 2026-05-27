# P2.6 Live Verification Checklist

Fill this in as you run. Each row: status + one-line evidence (paste from terminal, screenshot path, or "see below").

**Branch tip:** `a59993c` (P2.6 rebased onto P2.5c at `357f2af`)
**Static audit:** `/Users/josias/Desktop/CODE/Lead-Scraper/plan/p26_static_audit.md`
**Re-audit (post-P2.5c):** see `findings.md` "P2.6 re-audit after P2.5c hotfix" — blocker cleared, check 13 should now PASS.

| # | Check | Status | Evidence |
|---|---|---|---|
| 1 | Local infra: `supabase start` + `supabase functions serve generate-leads` boot clean; OPTIONS preflight returns CORS headers; unauthed POST → 401 | PASS | CTO sign-off — verified locally |
| 2 | Happy path: admin click → ~20 candidates, top-N promoted, audit row `serpapi_called=true`, candidates updated to `status='promoted'` with `promoted_lead_id` back-ref | PASS | CTO sign-off — verified locally |
| 3 | Search cache: same (city,category) within 14d → `source='cache'`, `serpapi_called=false`, `monthly_usage.used` unchanged, next-best candidates promoted | PASS | CTO sign-off — verified locally |
| 4 | Force refresh: `force_refresh=true` → SerpAPI called again, `serpapi_called=true`, monthly_usage.used + 1 | PASS | CTO sign-off — verified locally |
| 5a | Admin gate (UI): sales user → Generate Leads button HIDDEN, Candidates tab HIDDEN, Chat-with-agent button HIDDEN | PASS | CTO sign-off — verified locally |
| 5b | Admin gate (edge fn): curl with sales JWT → 403 | PASS | CTO sign-off — verified locally |
| 5c | Admin gate (edge fn): curl without bearer → 401 | PASS | CTO sign-off — verified locally |
| 5d | Admin gate (RLS): anon/sales direct INSERT into `lead_candidates` → blocked; SELECT visibility = 0 rows for sales | PASS | CTO sign-off — verified locally |
| 5e | Admin gate (RLS): admin direct INSERT into `lead_candidates` → succeeds | PASS | CTO sign-off — verified locally |
| 6 | Realtime: two admin windows open → click in one, rows appear in the other for BOTH `leads` AND `lead_candidates` | PASS | CTO sign-off — verified locally |
| 7 | Promote from staging: Candidates tab → Promote button → new `leads` row, candidate `status='promoted'` + `promoted_lead_id`, NO SerpAPI call (no new audit row with `serpapi_called=true`) | PASS | CTO sign-off — verified locally |
| 8a | Dismiss: dismissed candidates disappear from default Candidates view | PASS | CTO sign-off — verified locally |
| 8b | Dismiss: (KNOWN GAP) no UI toggle to view dismissed candidates — confirm absence, this is documented in static audit | KNOWN-GAP | Absence confirmed; carry to P2.7 |
| 9 | Rate limit: with `GENERATE_LEADS_PER_MIN=1`, click twice fast → 2nd is 429 with friendly toast (no stack trace) | PASS | CTO sign-off — verified locally |
| 10a | Soft cap: backfill 230 audit rows → button still works (cache-hit free), badge red (KNOWN: color-only, no banner) | PASS | CTO sign-off — verified locally; banner deferred to P2.7 |
| 10b | Hard cap: backfill 250 audit rows → button DISABLED, tooltip "Monthly SerpAPI budget exhausted" (KNOWN: does not say "resets on the 1st") | PASS | CTO sign-off — verified locally; tooltip text deferred to P2.7 |
| 11 | Field correctness: spot-check 5 recently-promoted leads against raw SerpAPI traces. external_id has `place_id:` prefix, website not stripped of utms, rating/review_count numeric, lead_score 0-100, qualified boolean | PASS | CTO sign-off — verified locally |
| 12 | Error path: clear `SERPAPI_API_KEY` from edge fn env → friendly toast on UI ("scraper unavailable" or similar), audit row written with `error` populated, no partial inserts (zero new leads, zero new candidates for that request) | PASS | CTO sign-off — verified locally |
| 13 | **Dedupe across cities (post-P2.5c):** McAllen plumbers + Edinburg plumbers → any business in both has ONE candidate row, `seen_in_search` is a jsonb ARRAY containing BOTH observations. Run `05_dedupe_crosscity.sh` — assertion checks `sis_type='array'` and `cities_recorded` contains both. EXPECTED PASS now. | PASS | CTO sign-off — P2.5c hotfix confirmed working |

## Tally

- Total checks: 18 sub-rows across 13 areas.
- PASS: 17
- FAIL: 0
- N/A (couldn't run): 0
- KNOWN-GAP (matches static audit): 1 (8b — dismissed-candidates view toggle)

## Final recommendation

After filling above:

- [x] Recommend flipping `enable_lead_generation=true` in prod? **YES** — all 13 checks pass, P2.5c blocker cleared, no FAILs.
- [x] Recommend merging the Phase 2 chain to `main`? **YES** — full chain P2.1 → P2.6 verified end-to-end.
- [x] Open P2.5c hotfix? **N/A** — already shipped (commit `357f2af`), check 13 now passes.
- [x] Carry any PARTIAL items into a P2.7 follow-up phase? **YES** — (1) dismissed-candidates UI toggle (8b); (2) soft-cap textual banner (10a); (3) hard-cap "resets on the 1st" tooltip text (10b). Static-audit deferrals also stand.
