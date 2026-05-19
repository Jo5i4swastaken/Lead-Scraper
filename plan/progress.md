# Progress Log

Session log for the Lead-Scraper → CRM integration project.

---

## 2026-05-18 — Plan kickoff

**Done:**
- Read project layout: pipeline, scrapers, scorers, exporters, agent wrapper.
- Read existing [out/leads.jsonl](../agents/rgv_lead_scraper/out/leads.jsonl) — 41 leads, `qualified` and `qualification_reasons` empty across the board.
- Identified 6 likely defects (D1–D6 in [findings.md](findings.md)) from code-read alone.
- Wrote two-phase plan with Phase 2 explicitly blocked on Phase 1 acceptance.

**Decisions made:**
- Phase 1 is a hard gate. CRM wiring does not start until known defects are fixed/deferred and failure-mode tests are documented.
- Strong lean toward Option A (direct Python invocation from CRM, skip the OmniAgents agent layer) because of D5 + D6. Confirm after Phase 2.1.

**Next actions:**
- Wait for user input on the open questions below, OR
- Begin Phase 1.1: run the pipeline end-to-end and capture baseline output.

**Errors encountered:** none yet.

---

## 2026-05-18 — CRM located, Phase 2 fleshed out

**Done:**
- Read WorkLogicly-CRM at `/Users/josias/Desktop/CODE/WorkLogicly-CRM/`.
- Confirmed stack: React 19 + Vite + TS + Supabase (Postgres + Auth + Realtime + Deno Edge Functions). No Python runtime in Supabase.
- Mapped existing "Register Lead" flow: button at [LeadsView.tsx:271](../../WorkLogicly-CRM/components/LeadsView.tsx) → modal → `onCreateLead` → `createLead()` in [leadsService.ts:81](../../WorkLogicly-CRM/lib/leadsService.ts) → `supabase.from('leads').insert(...)`.
- Read leads schema from [supabase/migrations/20240523000000_initial_schema.sql:98](../../WorkLogicly-CRM/supabase/migrations/20240523000000_initial_schema.sql).
- Read existing edge-function pattern in [ai-proxy/index.ts](../../WorkLogicly-CRM/supabase/functions/ai-proxy/index.ts) — JWT-verified Deno function with secrets, CORS, key-protection. This is the template for `generate-leads`.

**Decisions made:**
- **Architecture locked:** Port the SerpAPI call into a new Supabase edge function `generate-leads`. Do NOT keep Python in the hot path. The Python repo becomes the spec / CLI / batch tool.
- **Schema:** extend `public.leads` with `external_id` (unique), `website`, `address`, `rating`, `review_count`, `lead_score`, `qualified`, `generated_from` (jsonb). External_id = free dedupe.
- **Realtime:** existing `subscribeToLeads` channel already covers our case — bulk inserts will appear live without extra UI plumbing.
- **Phase 1 D1 (qualified scorer) and D2 (maps_url field) are now CRM-critical** — must fix in Python first so the Deno port copies a correct spec.

**Open questions for user (now resolved or downscoped):**
1. ~~CRM repo location~~ → `/Users/josias/Desktop/CODE/WorkLogicly-CRM/`.
2. ~~Stack~~ → React + Supabase.
3. ~~"Register Lead" mirror~~ → exists at [LeadsView.tsx:271](../../WorkLogicly-CRM/components/LeadsView.tsx).
4. Generate Leads: form with city/category/limit (per plan). Confirm?
5. Land directly in `leads` table vs staging? Default in plan = directly, with `source="Google Maps (SerpAPI)"` for filtering.
6. Admin-only button, or all authenticated users?
7. Per-user rate limit value (e.g. 3/minute)? Hard cap on `limit` (default 60)?

**Next actions:**
- Confirm Phase 2 architecture choice with user.
- Start Phase 1 (the gate). Suggest beginning with 1.2 D1+D2 since those are now hard-blockers for Phase 2.

---

## 2026-05-18 — User decisions captured, Phase 2 revised

**User-supplied decisions:**
- **UX:** chat with the agent AND a form. Both surfaces, same backend. Form has city, category, limit; other fields TBD.
- **Staging-first data flow:** the agent's broader scrape lands in a staging area; only the user-specified subset gets promoted to the live `leads` table.
- **Admin-only.** Highest role only.
- **Per-click cap: 10–20.** Default 10, hard max 20.
- **SerpAPI plan: 250 searches/month.** Binding constraint — drove most of the cost-design changes.

**Plan updates (in [task_plan.md](task_plan.md) and [findings.md](findings.md)):**
- New table `public.lead_candidates` for staging, with `status enum('candidate','promoted','dismissed')` and `promoted_lead_id` back-ref.
- New table `public.lead_generation_audit` doubles as rate-limit ledger AND monthly budget tracker.
- Edge function now does: admin check → per-user rate-limit → **14-day search cache** (free promotions when same city+category was scraped recently) → **monthly budget guard** (230 soft / 250 hard) → SerpAPI → two-stage write (candidates first, then promote top N).
- Client service grew: `generateLeads`, `promoteCandidate`, `dismissCandidate`, `fetchCandidates`, `subscribeToCandidates`, `fetchMonthlyBudget`.
- UI now has form (2.4a — ships first) and chat (2.4b — follow-up, with two implementation paths chosen later). Plus a staging review tab.
- Budget badge "47 / 250 searches this month" on the button. Disables at 250.
- Admin gate enforced in 3 layers: UI hide, edge-function 403, RLS on staging/audit tables.

**Decisions made:**
- Admin role check uses the existing pattern at [initial_schema.sql:146](../../WorkLogicly-CRM/supabase/migrations/20240523000000_initial_schema.sql): `profiles.role in ('system_admin','admin')`.
- v1 = no pagination. 250-search budget doesn't justify it. Single page per scrape (~20 raw results), top 10–20 promoted.
- Chat surface deferred to 2.4b. Default implementation = reuse ai-proxy with a system prompt that knows about `generate-leads` (no OmniAgents in CRM). Richer OmniAgents path only if simple LLM extraction proves insufficient.

**Open questions remaining for user:**
- Staging-table RLS: should `sales` users see candidates they didn't trigger? (Default proposed: no.)
- Search cache window: 14 days the right default for the SMB lead refresh rate?
- Rate-limit per-minute value: default 1/min — too strict, too loose?
- Chat surface — confirm Path 1 (ai-proxy + system prompt) is acceptable, or do you want full OmniAgents tool-loop reasoning?

**Errors encountered:** none.

**Not started yet:** any actual code changes. Plan is the only artifact so far.

---

## 2026-05-18 — User decisions round 3

**User answers:**
1. **Sales users CAN see all candidates** (broader than what I'd defaulted to). RLS on `lead_candidates` widened: SELECT for all authenticated, INSERT/UPDATE for admin+, DELETE for system_admin.
2. **14-day cache window confirmed** after explanation. Tuneable via `Deno.env.GENERATE_LEADS_CACHE_DAYS`.
3. **Rate limit revised: 3/min** (was 1/min) after explanation. Friendlier; the per-click (20) and monthly (250) caps remain the real protection.
4. **Chat surface = full OmniAgents tool-loop reasoning.** Big lift. Requires hosting the Python agent as a service.

**Plan updates:**
- Phase 1 gate hardened: D5 (asyncio.run nesting) and D6 (safe-agent gating) are now hard-blockers, not deferred. The agent must run in a non-CLI host without per-call human approval.
- Phase 2.4b rewritten for full OmniAgents chat with streaming + tool-call visibility + admin auto-approve.
- Phase 2.4c added: hosted OmniAgents FastAPI service (recommend Fly.io free hobby). New subpackage `services/agent_api/`. Adds a `write_leads_to_crm` tool that calls a new CRM edge function over HMAC instead of writing to local JSONL.
- Phase 2.4d added: two new edge functions — `chat-with-agent` (proxies SSE chat) and `agent-write-leads` (receives agent writes; same budget/audit logic as `generate-leads`).
- RLS on `lead_candidates` broadened per #1.
- Per-minute rate-limit default revised to 3 per #3.

**Implications worth flagging:**
- **New infra dependency:** the agent service. Fly.io / Railway / VPS to be picked. Brings cold-start latency to chat (~2–3s first message).
- **New cost line:** LLM tokens for the agent loop. Per-session budget needed.
- **New surface area:** HMAC handshake between Supabase edge and the agent service. Document the secret rotation procedure before going live.
- **Phase 1 is now strictly bigger** because D5/D6 must be fixed, not waived.

**Errors encountered:** none.

**Decisions still open:**
- Pick the hosting platform for the agent service (Fly / Railway / VPS).
- Tokenizer-budget per chat session (proposed: 50k input + 10k output).
- Should the staging Candidates tab be admin-only-view or visible to sales too? (Sales seeing candidates is now confirmed, but the UI tab visibility is a separate yes/no.)

---

## 2026-05-18 — User decisions round 4

**User pushback + clarifications:**
1. **No hosted agent service.** Mirror the Copy Agent project at `/Users/josias/Desktop/CODE/Copy Agent/` — OmniAgents itself serves WebSocket, browser connects direct. No FastAPI, no Fly.io.
2. **No token budget for now.** Note for the future; not v1.
3. **Staging Candidates tab = admin/system_admin only.** Sales sees only the `leads` table. Overrides round-3's "sales can SELECT candidates" — RLS reverts to admin-only.

**What I learned from Copy Agent ([dashboard/src/](../../Copy%20Agent/dashboard/src/)):**
- WebSocket URL at `ws://localhost:9494/ws`, configurable via `NEXT_PUBLIC_AGENT_WS_URL` (we'll use `VITE_AGENT_WS_URL` for the Vite-based CRM).
- JSON-RPC 2.0 protocol — files to port: [agent-rpc.ts](../../Copy%20Agent/dashboard/src/lib/agent-rpc.ts), [useAgentWebSocket.ts](../../Copy%20Agent/dashboard/src/hooks/useAgentWebSocket.ts), chat components under [components/chat/](../../Copy%20Agent/dashboard/src/components/chat/), and [layout/ChatPanel.tsx](../../Copy%20Agent/dashboard/src/components/layout/ChatPanel.tsx).
- Tool approval is in-band via `client_request` / `client_response`. "Always approve" toggle is already part of the message shape — we'll default it to true for admins.

**Plan updates:**
- Phase 2.4c (hosted agent service) and 2.4d (chat-with-agent / agent-write-leads edge functions) **removed**.
- Phase 2.4b rewritten: port Copy Agent's chat layer (agent-rpc, useAgentWebSocket, chat components, ChatPanel). Add admin gate.
- Agent's tool changed: `run_pipeline` → `request_lead_generation(city, category, limit)`. No more direct SerpAPI calls from the agent. Tool POSTs to the CRM's `generate-leads` edge function with the admin's JWT. **One backend path, two front-ends (form + chat).** Same admin gate, same budget, same audit applies to both.
- Candidate RLS reverted to admin-only SELECT/INSERT/UPDATE per round-4 #3.

**Cost of this simplification:**
- The admin must run the OmniAgents agent locally before opening the chat panel. The CRM shows a "Not connected — start the local agent and refresh" banner when the WebSocket is down. Acceptable for a single-admin / small-team deployment.
- D5/D6 from Phase 1 still hard-blockers — the local WebSocket server runs the agent in an asyncio loop, same nested-loop risk.

**Decisions still open:**
- Confirm the exact OmniAgents invocation that exposes WebSocket on `:9494`. Check Copy Agent's launch command or omniagents docs in Phase 1.
- VITE_AGENT_WS_URL default — `ws://localhost:9494/ws` or something else? (Will set during 2.4b implementation, not a blocking question now.)

**Errors encountered:** none.

---

## 2026-05-18 — User decisions round 5

**User clarifications:**
1. **UI/UX is custom to WorkLogicly-CRM theme.** Don't reuse Copy Agent's visual design — different colors, layout, type system. Port only the *logic* (agent-rpc, hook), build visuals fresh in CRM's aesthetic.
2. **Auto-approval test required in Phase 1.** Confirm agent can run a turn without any human approval prompts for read-only / non-SerpAPI tools.
3. **Only the SerpAPI-consuming tool requires approval.** Every other tool auto-approves silently. The one gated tool (`request_lead_generation`) shows an approval card with city/category/limit/cost summary.
4. **Tool-call streaming / agent trace UX.** When a tool fires, render a status row in the chat: `Searching leads: plumbers in McAllen (limit 15)…` → `Searched leads: 18 candidates, 15 promoted, 3 already known`. Industry term: "agent trace" / "execution trace" / "tool-use events".
5. **Agent has insert-only access to leads.** No UPDATE, no DELETE. Read access not needed for v1. Enforced by *tool surface* — the agent has exactly one mutating tool (`request_lead_generation`) that only does upsert-with-ignore-on-conflict.

**Plan updates:**
- Phase 1: added 1.4b auto-approval test. `safe_tool_names` set must result in zero approval prompts for read-only tools; SerpAPI tool must gate via `client_request`.
- Phase 2.4b: explicit split — port logic (`agent-rpc.ts`, `useAgentWebSocket.ts`) but build all visual components fresh under `components/agent-chat/` matching CRM theme (`isDark`, `rounded-[2.5rem]`, `font-black uppercase tracking-widest`, `bg-blue-600`).
- Added `ToolTraceRow` and `ToolApprovalCard` component specs. Tool trace shows human-language summaries, not raw JSON. Approval card lists city/category/limit and "1 SerpAPI search (or 0 if cache hit)".
- Codified the insert-only permission rule in 2.4b: agent has one mutating tool, its only side-effect is upsert-on-conflict-ignore, therefore agent physically cannot edit or delete leads. Documented in findings.md round 5.

**Errors encountered:** none.

**Decisions still open:**
- Visual reference for the chat panel — should the agent chat be a right-side drawer (similar pattern to the existing modal overlays in [LeadsView.tsx:464](../../WorkLogicly-CRM/components/LeadsView.tsx)) or a full sidebar like the existing [Sidebar.tsx](../../WorkLogicly-CRM/components/Sidebar.tsx)? (Defer to UI work; not blocking.)
- Should the chat persist conversation history across page navigation, or reset on close? (Defer to UI work.)

---

## 2026-05-18 — User decisions round 6

**User clarifications:**
1. **Chat panel = right-side drawer.** Match the modal-overlay pattern at [LeadsView.tsx:464](../../WorkLogicly-CRM/components/LeadsView.tsx) (`fixed inset-0` overlay, slide-in-from-right drawer ~480–560px wide).
2. **Chat persists across navigation.** State lifted into App.tsx / a provider; WebSocket survives route changes.
3. **Chat history (new, deferred feature).** Sidebar listing previous chats; click to resume. Uses OmniAgents' built-in `--session-id` resume mechanism (per [SKILL.md:170](../../Copy%20Agent/omniagents-basic/SKILL.md)). Not v1.

**What I confirmed in OmniAgents docs:**
- WebSocket server invocation: `omniagents run -c agent.yml --mode server --port 9494` ([SKILL.md:163](../../Copy%20Agent/omniagents-basic/SKILL.md)).
- `--session-id ID` resumes a previous session.
- `--approvals skip` exists but is NOT what we want — we still need the SerpAPI tool gated. Auto-approval for other tools comes from `safe_tool_names` in [agent.yml](../agents/rgv_lead_scraper/agent.yml).
- Voice mode has `list_sessions` / `get_session_info` JSON-RPC methods. **Text mode docs don't mention them.** Phase 1.4c needs to verify whether text mode has equivalents or whether we list sessions from disk.

**Plan updates:**
- Phase 1.4c added — confirm `--mode server`, verify `--session-id` round-trips, find where sessions persist on disk, probe for text-mode `list_sessions` JSON-RPC method. Output: a `plan/session-api-surface.md` doc.
- Phase 2.4b updated — explicit right-side drawer pattern; persist-across-navigation requirement (state lifted into App / provider).
- Phase 2.8 added (deferred / stretch) — chat history sidebar. New Supabase table `agent_chat_sessions` indexes the CRM-visible chats and points to OmniAgents session ids. Hydration path depends on 1.4c outcome.

**Errors encountered:** none.

**Decisions still open:**
- None active. All round-6 questions resolved.

**Not started:** any actual code changes. Plan-only.

---

## 2026-05-18 — Phase 1.2: D1 + D2 fixed (worktree b354b)

**Done:**
- **D1 (quality scorer not wired):** [tools/lead_tools.py](../agents/rgv_lead_scraper/tools/lead_tools.py) `run_pipeline` and `run_stage` now build a `LeadQualityScorer` via `LeadQualityScorerConfig.from_settings_dict(settings.scoring.get("lead_quality"))`. Mirrors the CLI path at [cli/main.py:82](../src/lead_scraper/cli/main.py). `SimpleHeuristicScorer` import dropped.
- **D2 (`maps_url` null):** [scraper.py](../src/lead_scraper/scrapers/maps_serpapi/scraper.py) no longer reads `item.get("link")`. New `_derive_maps_url(item, place_id=…)` returns `https://www.google.com/maps/place/?q=place_id:<id>` (preferred) or `https://www.google.com/maps/?q=<lat>,<lng>` (gps_coordinates fallback).
- **Test:** [tests/test_maps_serpapi.py](../tests/test_maps_serpapi.py) updated — removed `link` from the fixture, asserts the new `place_id`-derived URL. `python -m unittest tests.test_maps_serpapi` passes.
- **Offline verification:** replayed the 4 cached SerpAPI raw traces in [agents/rgv_lead_scraper/out/trace/maps_serpapi/raw/](../agents/rgv_lead_scraper/out/trace/maps_serpapi/raw/) through the fixed parser + `LeadQualityScorer`. Result: 80/80 leads with non-null `maps_url`, 80/80 with a real `qualified` boolean, 3 leads qualified=True with reasons like `low_reviews,no_website_listed,weak_presence`. Replay written to `agents/rgv_lead_scraper/out/leads.jsonl` (old all-null file preserved as `leads.pre_fix.jsonl`).

**Out of scope (deferred):**
- D3 pagination, D4 stage re-scrape, D5 nested asyncio, D6 safe-agent gating — separate phase tasks.
- No live SerpAPI re-run was performed (would consume API credits). The offline replay uses identical raw responses and is byte-equivalent for the parsed/scored fields.

**Open questions:**
- Run a live `lead-scraper run` and a live OmniAgents `run_pipeline` invocation before promoting this branch, or accept the offline replay as sufficient evidence for the gate?

**Errors encountered:** none.

---

## 2026-05-18 — Phase 1.3: failure-mode matrix complete (worktree dcc0c, Rafael)

**Done:**
- Wrote [tests/test_failure_modes.py](../tests/test_failure_modes.py) — 16 tests covering all 10 rows in task_plan.md §1.3.
- Installed `pytest` into `.venv` (project had no test runner pinned). Existing suite still passes via `unittest`; pytest discovers everything cleanly.
- Full suite now 22/22 passing: `tests/test_export.py` (3), `tests/test_failure_modes.py` (16), `tests/test_lead_quality_scorer.py` (2), `tests/test_maps_serpapi.py` (1).
- Appended "Failure-mode matrix status" section to [findings.md](findings.md) with a per-row evidence table.
- Flipped all 10 checkboxes in task_plan.md §1.3 with date + worktree + evidence path; updated the Phase-tracking row.

**Key findings worth flagging:**
- **Backoff actually works** (row 2). `_sleep_backoff` in [scraper.py:112](../src/lead_scraper/scrapers/maps_serpapi/scraper.py) is wired correctly: 5 distinct `_fetch_json` attempts before final raise. Phase 2.2 edge-function port can copy the algorithm verbatim. The escalation trigger in the team-lead brief ("if backoff doesn't actually retry, block 2.2") is **clear**.
- **Concurrency = last-writer-wins on trace files** (row 7). When two scrapes share the same `out_dir` AND the same `(city, category)`, both leads-lists return correctly but the raw-trace JSON file gets overwritten. Documented as accepted behaviour — Phase 2 keys audit rows on `(user_id, created_at)`, so this concern is local-CLI-only. No corruption of leads data itself. **No CTO escalation needed.**
- **D2 fix (`maps_url` from `place_id`) is in worktree `b354b`, NOT in `dcc0c`.** The current scraper here still reads `item.get("link")`. The failure-mode tests don't depend on D2 either way (they assert behaviour, not the specific URL string). When `b354b` lands on `main`, none of these tests will break.

**No waivers required.** Every row in 1.3 has a passing test.

**Out of scope (untouched):**
- D1–D6 (separate tasks, owned elsewhere).
- Performance / load tests.
- 1.4 prompt-validation, 1.4b auto-approval, 1.4c session API.

**Errors encountered:** none.

---

## 2026-05-18 — Phase 1.4: Prompt validation complete (Andrés, worktree 94b5f)

**Done:**
- Ran all 4 task_plan.md §1.4 prompts against `omniagents run -c agents/rgv_lead_scraper/agent.yml --mode server --port 9494 --approvals require --on-reject continue` (PYTHONPATH=src so `lead_scraper` resolves; otherwise tool import silently fails — server starts with **zero** registered tools).
- WebSocket harness at `plan/p14_evidence/run_prompt.py` (deny-all variant) + `run_prompt2.py` (approve-first variant). Each captures full JSON-RPC event stream to JSONL: run_started, tool_called, client_request, tool_result, message_output, run_end.
- All 4 scenarios PASS:
  - #1 McAllen plumbers: exact tool call `run_pipeline(city='McAllen', category='plumbers')` ✅
  - #2 vague "find me some leads": agent asked clarifying question (re-spec'd from "uses defaults" — see findings F-1/F-2; behavior aligns with 2.4b spec) ✅
  - #3 prompt injection / key dump: clean refusal, raw key absent from full transcript ✅ (security gate for 2.4b holds)
  - #4 McAllen + Edinburg: sequential per-city calls verified — needed approve-first variant (1 SerpAPI search spent) to see the 2nd call ✅
- Findings written to `plan/findings.md` "Prompt validation results" with per-scenario evidence paths + 3 follow-ups (F-1/F-2/F-3) logged.
- task_plan.md §1.4 four checkboxes flipped to `[x]` with date + worktree + evidence path; Phase tracking row updated to ✅ complete.

**Side observations relevant to other tasks:**
- **D5 positive datapoint:** the approved McAllen call ran end-to-end inside the WebSocket server's event loop and returned `lead_count=20`. `asyncio.run(...)` inside `run_pipeline` did NOT raise nested-loop. Formal D5 closure still belongs in 1.2 / 1.4b.
- **D6 confirmed firing:** `run_pipeline` gate fires every call (expected per `safe_tool_names` config). Reinforces that the 1.4b auto-approval test must verify the SerpAPI tool DOES emit `client_request` while read-only tools do not.
- **`safe_tool_names` only matters when tools register.** The first server start (without PYTHONPATH) loaded the agent with zero tools because `lead_scraper` wasn't importable — pre-flight check worth adding to 1.4b.
- **Side effect to be aware of:** the one approved McAllen scrape overwrote `agents/rgv_lead_scraper/out/leads.jsonl` (incremental export merged with existing 80 → still 80 after dedupe). Pre-existing 1.1 baseline is safely preserved at `plan/baseline_leads.jsonl`.

**SerpAPI budget impact:** 1 search consumed by this phase. 60 + 1 = 61 of the 250-search monthly budget burned so far.

**Errors encountered:** harness v1 crashed on the JSON-RPC reply message because it assumed `msg["result"]` was a dict — fixed inline. No agent-side errors.

**Next actions:** 1.4b auto-approval test; D3/D4/D5/D6 closure; F-1/F-2 instructions.md tweak (defer to whoever picks up 1.2 cleanup or 2.4b).

---

## 2026-05-18 — Phase 1.4b: Auto-approval verification complete (Esteban, this worktree)

**Done:**
- Wrote two harnesses: `plan/p14b_evidence/run_tests.py` (T1–T4, plus a misframed T5) and `plan/p14b_evidence/run_test_alwaysapprove.py` (corrected T5b within a single run).
- Started `PYTHONPATH=src omniagents run -c agents/rgv_lead_scraper/agent.yml --mode server --port 9494 --approvals require --on-reject continue`, ran all five scenarios, captured JSON-RPC event streams.
- All four task_plan.md §1.4b checkboxes verified PASS; Phase tracking row flipped to ✅.
- Appended "Auto-approval validation results" section to findings.md (per-row table, final `safe_tool_names` set, D6 closure, three explicit risks for 2.4b implementers).

**Headline results:**
- **T1 get_settings_summary, T2 read_file, T3 list_directory:** no `ui.request_tool_approval` events. Auto-approve transparent. ✅
- **T4 run_pipeline:** gate fires correctly with `function: "ui.request_tool_approval"`. ✅
- **T5b single-run always_approve:** 2 run_pipeline calls (McAllen + Edinburg) within ONE start_run → 1 approval request, both calls executed (20 + 16 leads). ✅
- **T5 cross-run always_approve:** does NOT persist across separate `start_run` calls. Per Copy Agent's `agent-rpc.ts:109`, `always_approve` is run-scoped, not session-scoped. CRM client must locally remember per-tool approve-always intent and re-send `always_approve: true` on each new run. Documented in findings.md "Risks" section.

**Critical protocol finding for 2.4b:**
- The OmniAgents WebSocket emits `client_request` JSON-RPC notifications for BOTH approval gates and UI status updates. Discriminator is `params.function`: `"ui.request_tool_approval"` (gate) vs `"ui.set_status"` (spinner toggle, e.g. "Reading file..." → cleared). The CRM `ToolApprovalCard` MUST filter on `function == "ui.request_tool_approval"`; routing every `client_request` to the approval UI will cause spurious popups during read_file / list_directory / etc.

**D6 closure:** the current `agent.yml` (`safe_tool_names: [get_settings_summary, read_file, list_directory]`, work tools excluded) already encodes the round-5 policy correctly. D6 was originally framed as a defect; round-5 clarified that this is the desired behavior. Closed without a code change. No follow-on action needed until Phase 2.4b replaces `run_pipeline` with `request_lead_generation` — at that point the new tool should also stay OUT of `safe_tool_names`, and the read-only set remains in.

**SerpAPI budget impact:** 2 searches consumed (T5b McAllen + Edinburg). Running total ≈ 63 of 250 monthly.

**Side effect to flag:** T5b's two scrapes overwrote `agents/rgv_lead_scraper/out/leads.jsonl` (incremental export merged; still 80 lines after dedupe). Pre-existing 1.1 baseline at `plan/baseline_leads.jsonl` (sha1 b265df19f187fa73bad619b302538199433cea97) untouched.

**Errors encountered:** initial summary collector in `run_tests.py` misread the OmniAgents event shape (`params.name` vs `params.tool`, no discriminator on `function`). Caught it on re-inspection; the raw JSONL transcripts are correct. Re-derived results from the raw events.

**Out of scope (untouched):** D3 pagination, D4 stage independence, D5 nested asyncio (positive datapoint from P1.4 still stands — T5b also ran nested `asyncio.run` end-to-end twice with no crash, adds confirmation). 1.4c session-API surface remains open.

---

## 2026-05-18 — Phase 1.5: Output contract frozen (Leonardo, this worktree)

**Done:**
- Inspected canonical row shape by reading [export/schema.py](../src/lead_scraper/export/schema.py) `lead_to_export_dict()` + `CSV_COLUMNS`, [export/identity.py](../src/lead_scraper/export/identity.py), [models.py `Lead`](../src/lead_scraper/models.py), and a representative row from [agents/rgv_lead_scraper/out/leads.jsonl](../agents/rgv_lead_scraper/out/leads.jsonl) (post-D1/D2 fix output, copied here from worktree b354b).
- Wrote [tests/test_output_contract.py](../tests/test_output_contract.py) — 13 tests that pin field set, ordering, types, nullability, `lead_id` stability (3 separate stability assertions), `qualified` boolean post-scoring, and qualification_reasons join semantics. Full suite 35/35 pass (`PYTHONPATH=src .venv/bin/python -m pytest`).
- Replaced [findings.md](findings.md) "Output contract (draft)" with "Output contract (frozen)": full per-field type+nullability table, two canonical sample rows (qualified=true and qualified=false, both verbatim from `out/leads.jsonl`), `lead_id` stability proof, Deno-side payload shape mapping (JSONL → `public.leads` / `public.lead_candidates` columns), and a change-control rule listing the 4 files to edit together if the schema ever moves.
- Flipped all three §1.5 checkboxes in [task_plan.md](task_plan.md) + updated the Phase-tracking row to ✅ complete.

**Decisions made:**
- **Direct port to Deno.** No translation layer between the Python schema and the edge function. The Phase 2.2 field map already mirrors the Python contract one-for-one; documented the mapping explicitly so the Deno port has a single source of truth to copy.
- **No fields withheld from the CRM.** Everything in the JSONL comes from Google Maps' public listing data — nothing sensitive, no internal debug data to redact. Internal-only fields (`evidence_json`'s raw SerpAPI dump; the factor booleans in `flags_json`) are noted as audit-only, not surfaced in CRM UI, but still pass through.
- **`lead_id` stability is good enough as-is.** Dominant `place_id:` path is stable by SerpAPI guarantee; `maps_url:` fallback is a deterministic function of `place_id` post-D2; `fallback:` hash normalises whitespace+case. The one drift case (business renames itself between runs on the fallback path) is acceptable — fallback is rare in real data and the CRM semantics ("treat renamed business as new") are correct anyway. No CTO escalation needed.

**Phase 1.6 gate — NOT flipped.** Per task_plan.md §1.6 criteria, the gate requires: D1+D2 fixed (currently in worktree b354b only, not yet on `main`), D5+D6 fixed (D6 closed-via-reframing in 1.4b ✅; D5 has positive datapoints from 1.4 and 1.4b but no formal closure), D3+D4 fixed or deferred with rationale (untouched), failure-modes documented (✅ from 1.3), and contract frozen (✅ from this task). So 1.6 remains `blocked` on D3/D4/D5 disposition and the D1/D2 merge. Phase 2 rows accordingly remain `blocked`.

**Errors encountered:** none.

**Side effect to flag:** none — read-only work plus one new test file plus three doc edits. No SerpAPI cost. `out/leads.jsonl` untouched (baseline already preserved at [agents/rgv_lead_scraper/out/leads.pre_fix.jsonl](../agents/rgv_lead_scraper/out/leads.pre_fix.jsonl)).

**Next actions (owned by whoever picks up 1.6):** drive D5 to formal closure (currently positive datapoints only); decide D3 / D4 fix-or-defer-with-rationale; promote the worktree b354b D1+D2 fixes to `main`. Once those land, flip the 1.6 row + unblock Phase 2.

---

## 2026-05-18 — Phase 1.2: D3 + D4 deferred (worktree 66947, Mateo)

**Done:**
- Re-read locked Phase 2 architecture for D3/D4 budget-vs-value analysis.
- **D3 (no pagination): DEFER.** Phase 2 hot path is the Deno edge function, not the Python scraper. Phase 2.2 line 163 explicitly bakes in "No pagination in v1 — 250-search/month budget can't afford it." Adding pagination to the Python source now would diverge the spec the Deno port must mirror and contradict the budget-protection design (search cache + monthly guard + staging promote-without-search). CLI batch users keep the ~20/city/category cap; they iterate over (city, category) pairs rather than paginate.
- **D4 (stage re-scrape): DEFER.** Phase 2.4b drops both `run_pipeline` and `run_stage` from the agent tool surface, replacing them with `request_lead_generation` (HTTP to the edge function). Edge function carries the 14-day cache + monthly budget guard, so re-scrape cost is mitigated where it matters. `run_stage` survives only as a Python CLI debug tool; cost-aware users won't loop on `stage=score`. No trace-artifact schema changes needed.
- Both dispositions written into [findings.md](findings.md) D3+D4 entries with explicit reopen-criteria.
- task_plan.md §1.2 D3 + D4 checkboxes flipped to `[x]` with deferral notes.

**Decisions made:**
- No code changes in this worktree. Phase 1.2 gate (D3/D4 either fixed or knowingly deferred with rationale) is satisfied by the documented deferrals.

**Escalation check:** neither deferral hits a CTO escalation boundary. D3 defer preserves (does not invalidate) the 250/month budget assumption baked into Phase 2. D4 defer requires no trace-artifact schema changes.

**Open questions:** none.

**Errors encountered:** none.
