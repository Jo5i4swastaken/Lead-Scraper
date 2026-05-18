# Findings — Lead-Scraper → CRM Integration

Research log. Append discoveries here. Each entry: short title, file:line evidence, implication.

## Architecture snapshot (from initial code read)

- **Pipeline shape:** `scrape → enrich → score → export` — [src/lead_scraper/pipeline.py](../src/lead_scraper/pipeline.py).
- **Only scraper implemented:** SerpAPI Google Maps — [src/lead_scraper/scrapers/maps_serpapi/scraper.py](../src/lead_scraper/scrapers/maps_serpapi/scraper.py).
- **Enricher is a no-op:** [src/lead_scraper/enrichers/noop.py](../src/lead_scraper/enrichers/noop.py). No website fetching, no social scraping — `social_links` will be empty for now.
- **Two scorers exist:** `SimpleHeuristicScorer` (rating * 20 + reviews/10) and `LeadQualityScorer` (config-weighted, sets `qualified`). Only the simple one is wired through the agent — see "defect: scorer not wired" below.
- **Exporters:** JSONL, CSV, SQLite (`out_dir`/`leads.jsonl` etc). Incremental mode supported.
- **Identity / dedupe key:** `place_id` > `maps_url` > sha256 of name+category+phone+address — [src/lead_scraper/export/identity.py](../src/lead_scraper/export/identity.py). Matches dedupe key in [pipeline.py](../src/lead_scraper/pipeline.py).
- **Agent layer:** OmniAgents agent at [agents/rgv_lead_scraper/](../agents/rgv_lead_scraper/) exposes `run_pipeline`, `run_stage`, `get_settings_summary`. Model declared as `gpt-5.2` in [agent.yml](../agents/rgv_lead_scraper/agent.yml).

## Defects confirmed from code read (verify in Phase 1.2)

### D1: Quality scorer not wired through the agent — **fixed (2026-05-18, worktree b354b)**
- **Evidence:** [tools/lead_tools.py:71](../agents/rgv_lead_scraper/tools/lead_tools.py) and line 109 instantiate `SimpleHeuristicScorer` only.
- **Symptom in output:** [out/leads.jsonl](../agents/rgv_lead_scraper/out/leads.jsonl) — every row has `"qualified": null` and `"qualification_reasons": ""`.
- **Implication for CRM:** "Generate Leads" needs to surface qualified leads. Currently impossible.
- **Fix:** agent path now routes through `LeadQualityScorer` built via `LeadQualityScorerConfig.from_settings_dict(settings.scoring.get("lead_quality"))`, matching the CLI path at [cli/main.py:82](../src/lead_scraper/cli/main.py). Offline replay of cached SerpAPI traces produces 80/80 leads with a real `qualified` boolean; reasons populate when factors are active (e.g. `low_reviews,no_website_listed,weak_presence`). Worktree `b354b` — not yet on main.

### D2: `maps_url` always null — **fixed (2026-05-18, worktree b354b)**
- **Evidence:** [scraper.py](../src/lead_scraper/scrapers/maps_serpapi/scraper.py) reads `item.get("link")` but SerpAPI Google Maps responses use `place_id_search` / build URL from `place_id`.
- **Symptom in output:** Every row `"maps_url": null`.
- **Implication:** CRM users can't click through to verify the business on Google Maps.
- **Fix:** new helper `_derive_maps_url(item, place_id=…)` returns `https://www.google.com/maps/place/?q=place_id:<id>` when `place_id` is present, falling back to `https://www.google.com/maps/?q=<lat>,<lng>` from `gps_coordinates`. The scraper no longer reads `link` at all. Offline replay shows 80/80 leads now carry a non-null `maps_url`. Worktree `b354b` — not yet on main.

### D3: No pagination
- **Evidence:** [scraper.py](../src/lead_scraper/scrapers/maps_serpapi/scraper.py) — single request, reads only the first page's `local_results`.
- **Implication:** CRM "Generate Leads" caps at ~20 results per city+category click. Likely undersells the feature.

### D4: Stages aren't independent — `run_stage` re-scrapes
- **Evidence:** [tools/lead_tools.py:100,106,112](../agents/rgv_lead_scraper/tools/lead_tools.py) — `run_stage("score")` calls `_scrape` then `run_enrich` then `run_score`.
- **Implication:** Calling `stage=score` repeatedly burns SerpAPI credits. Not safe to expose as-is to a CRM caller.

### D5: `asyncio.run` inside a function tool may conflict with host loop
- **Evidence:** [tools/lead_tools.py:69,70,97,100](../agents/rgv_lead_scraper/tools/lead_tools.py).
- **Implication:** If OmniAgents runs tools inside a running event loop, this raises. Needs runtime verification.

### D6: Safe-agent gate fires on the only useful tools
- **Evidence:** [agent.yml](../agents/rgv_lead_scraper/agent.yml) lists only read-only tools in `safe_tool_names`. `run_pipeline` and `run_stage` are gated → require user approval at runtime.
- **Implication:** A CRM backend cannot trigger the agent autonomously without bypassing this gate. Reinforces the case for Option A (direct Python invocation, no agent layer in the hot path).

## Output contract (draft — finalize in 1.5)

Current JSONL row shape, derived from [export/schema.py](../src/lead_scraper/export/schema.py):

| Field | Type | Nullable | Notes |
|---|---|---|---|
| `lead_id` | string | no | `place_id:...` or `maps_url:...` or `fallback:<sha>` |
| `name` | string | no | |
| `category` | string | no | from SerpAPI `type` or query category |
| `address` | string | yes | |
| `phone` | string | yes | freeform, e.g. `(956) 686-6656` |
| `website` | string | yes | may include UTM params |
| `review_count` | int | yes | |
| `rating` | float | yes | |
| `maps_url` | string | yes | derived from `place_id` (D2 fixed) |
| `social_links_json` | object | no | empty until enricher exists |
| `flags_json` | object | no | contains `google_place_id`, `query_category` |
| `lead_score` | float | yes | from SimpleHeuristicScorer |
| `qualified` | bool | yes | populated by `LeadQualityScorer` (D1 fixed) |
| `qualification_reasons` | string | no | comma-joined active factors; populated when score ≥ threshold (D1 fixed) |
| `evidence_json` | array | no | includes full SerpAPI raw item |
| `exported_at` | ISO8601 string | no | UTC |

## CRM (WorkLogicly-CRM) — resolved

Path: `/Users/josias/Desktop/CODE/WorkLogicly-CRM/`

### Stack
- React 19 + Vite + TypeScript + TailwindCSS v4
- Supabase: Postgres + Auth (JWT) + Realtime + Edge Functions (Deno/TS)
- No backend server of its own — everything goes Edge Function → Postgres
- AI calls proxied through [supabase/functions/ai-proxy/index.ts](../../WorkLogicly-CRM/supabase/functions/ai-proxy/index.ts) so keys stay server-side. **This is the pattern to copy for SerpAPI.**

### Existing "Register Lead" flow (the one to mirror)
1. Button at [LeadsView.tsx:271](../../WorkLogicly-CRM/components/LeadsView.tsx) — `<Plus /> Register Lead`, opens modal.
2. Modal submit calls `handleCreateLeadSubmit` → `onCreateLead` prop ([LeadsView.tsx:150](../../WorkLogicly-CRM/components/LeadsView.tsx)).
3. `App.tsx` wires `onCreateLead={handleCreateLead}` ([App.tsx:944](../../WorkLogicly-CRM/App.tsx)) → calls `createLead` from [lib/leadsService.ts:81](../../WorkLogicly-CRM/lib/leadsService.ts).
4. `createLead` does `supabase.from('leads').insert(row).select().single()`.
5. Realtime subscription [leadsService.ts:140](../../WorkLogicly-CRM/lib/leadsService.ts) auto-pushes new rows to all open clients — **bulk inserts will appear live, no extra UI plumbing.**

### Leads table schema ([supabase/migrations/20240523000000_initial_schema.sql:98](../../WorkLogicly-CRM/supabase/migrations/20240523000000_initial_schema.sql))
```
id uuid pk
created_at, updated_at timestamptz
company text
name text not null
email text
phone text
status text check in (New, Discovery, Contacted, Qualified, Proposal, Closed Won, Closed Lost)
source text
value numeric(12,2)
last_contact timestamptz
notes text
tags text[]
owner_id uuid → profiles(id)
```
RLS: any authenticated user can SELECT/INSERT/UPDATE; only admin can DELETE.

### Frontend Lead type ([types.ts:60](../../WorkLogicly-CRM/types.ts))
`{ id, name, company, email, phone?, source, status, value, lastContact, createdAt?, notes?, tags? }`

### Field-mismatch problem — **this is the big one**
Scraper output has: `rating`, `review_count`, `website`, `address`, `maps_url`, `lead_score`, `qualified`, `lead_id` (place_id).
CRM lead table has none of these. Options:
- **A.** Migration: add `website`, `address`, `rating`, `review_count`, `lead_score`, `qualified`, `external_id` (unique) to `public.leads`. Cleanest.
- **B.** Stuff scraper fields into `notes` + `tags`. No schema change, but unsearchable.
- **C.** New side table `public.lead_enrichment(lead_id, rating, review_count, …)`. Adds joins but keeps `leads` clean.

**Recommendation:** A. The CRM is young (3 migrations), schema can grow. Add `external_id` with a UNIQUE constraint → free dedupe.

## Language-mismatch problem — Python scraper vs Deno edge

The scraper is Python. Supabase Edge Functions are Deno/TypeScript. There is no Python runtime inside Supabase. Three viable architectures:

### Option 1 — Port the SerpAPI call into a Deno edge function
- New edge function `generate-leads`, modeled on [ai-proxy](../../WorkLogicly-CRM/supabase/functions/ai-proxy/index.ts).
- Stores `SERPAPI_API_KEY` via `supabase secrets set` (same as `OPENAI_API_KEY` today).
- Re-implements: SerpAPI request + retry/backoff, item → row mapping, dedupe-on-insert (via Postgres unique constraint), simple scoring.
- Inserts directly into `public.leads` using service role or as the authenticated user.
- **Pros:** zero infra, same auth model as the rest of the CRM, realtime pushes new leads automatically.
- **Cons:** must reimplement the parts of the Python scraper that matter. But the meaningful logic is ~80 lines (SerpAPI call + field map + score formula). The Python lead_scraper repo continues to exist for CLI / batch use.

### Option 2 — Stand up Python scraper as an HTTP service, edge function proxies to it
- Deploy [lead_scraper](../src/lead_scraper/) behind FastAPI on Fly.io/Railway/Render.
- New edge function `generate-leads` calls that HTTP endpoint with a shared secret + user context.
- **Pros:** reuses Python code as-is; richer scoring (config-driven `LeadQualityScorer`) lives unchanged.
- **Cons:** new service to host, monitor, secure; cold starts; extra hop adds latency; one more place to break.

### Option 3 — Browser → SerpAPI direct
- Rejected. Would leak `SERPAPI_API_KEY` to the client. Same reason the CRM already proxies AI calls.

**Recommendation: Option 1.** Matches the CRM's existing pattern, no new infra. The Python repo becomes the spec / reference, not the runtime. If `LeadQualityScorer` proves valuable, port that too — it's pure logic, no I/O.

## User decisions (2026-05-18)

### UX surfaces
- **Form** for the deterministic path: city, category, limit, plus any field we add later.
- **Chat with the agent** for ad-hoc / conversational lead requests. Two surfaces, one backend.
- Form ships first (smaller, predictable). Chat is a follow-up surface (see Phase 2.4b).

### Staging-first data flow
SerpAPI returns a broader list than the user asked for. Capture all of it, hand the user only what they asked for. Promotes a 1-search-per-click cost into a many-leads-per-search yield.

```
Click "Generate Leads" (limit=10)
  └─ edge function calls SerpAPI → ~20 raw results
      ├─ ALL 20 → INSERT into public.lead_candidates  (staging)
      └─ TOP 10 by lead_score → INSERT into public.leads  (active register)
```

- New table `public.lead_candidates` mirrors the scraper-extended `leads` schema + `status enum('candidate','promoted','dismissed')`, `promoted_lead_id uuid references leads(id)`, `seen_in_search_at`.
- Candidates can be promoted later from a "Staging" / "Candidates" tab without spending another SerpAPI call. Critical given the 250/month budget.
- Dedupe is now two-step: candidate-side (don't re-insert a place_id we've seen), lead-side (don't double-promote).

### Authorization
- Admin-only. Match the existing pattern at [initial_schema.sql:141-148](../../WorkLogicly-CRM/supabase/migrations/20240523000000_initial_schema.sql): `profiles.role in ('system_admin','admin')`.
- Enforce in three places: button hidden in UI if non-admin, edge function rejects non-admin JWTs, RLS on `lead_candidates` and `lead_generation_audit` restricts write to admin.

### Quotas
- **Per-click cap:** 10–20 leads (user said "10, 20"). Default 10, hard server-side cap 20.
- **SerpAPI monthly budget: 250 searches/month** — the real constraint. Roughly 8/day. Drives the rest of the cost design.

### Budget-protection design (from the 250/month constraint)
Without these, the button will exhaust the SerpAPI plan in a few days of clicking:

1. **Search cache.** Before hitting SerpAPI, check `lead_generation_audit` for an entry with the same `(normalized_city, normalized_category)` in the last N days (default 14). If found, return candidates from `lead_candidates` for that pair instead of spending a search. Configurable per-pair "force refresh."
2. **Monthly usage counter.** Edge function reads SerpAPI's account endpoint OR a local counter from `lead_generation_audit` filtered to current month. Reject calls when usage ≥ a configurable soft threshold (default 230) and surface a clear message.
3. **Usage meter in UI.** Show "Searches used this month: 47 / 250" near the button. Cheap, prevents surprise.
4. **Promote-without-search path.** "Promote candidate to lead" action on the Staging tab does NOT call SerpAPI. Most growth comes from this path after the first scrape of a (city, category) pair.
5. **Single SerpAPI call per click in v1.** No pagination. Limit 10–20 fits in one page. Reconsider pagination only if budget allows.

## User decisions (2026-05-18, round 2)

- **Sales users CAN see candidates triggered by others.** ~~Broaden RLS on `lead_candidates`~~ — **superseded by round 4 below.**
- **Search cache window:** 14 days as default. The knob lives in `Deno.env.GENERATE_LEADS_CACHE_DAYS` so it can be tuned in production without a redeploy.
- **Rate limit:** revise default to **3/min** (was 1/min). Per-click cap (20) + monthly cap (250) are the real protection; 3/min is friendly without being reckless.
- **Chat surface:** **Path 2** — full OmniAgents tool-loop reasoning. ~~The agent must run as a hosted service~~ — **superseded by round 4: mirror Copy Agent pattern (local WebSocket, no host).** Phase 1 D5/D6 still hard-blockers.

## User decisions (2026-05-18, round 4)

- **No agent hosting service.** Mirror the Copy Agent pattern: OmniAgents serves WebSocket locally, CRM browser connects directly. Details in [Chat architecture — mirror the Copy Agent pattern](#chat-architecture--mirror-the-copy-agent-pattern-no-hosting-needed) above.
- **No token budget per chat session for now.** Note for the future: long agent loops can burn LLM dollars; revisit when usage data exists. Not blocking v1.
- **Staging Candidates tab is admin/system_admin only.** Sales users see only `public.leads`. This **overrides** the earlier round-3 decision to widen `lead_candidates` SELECT to all authenticated users. RLS reverts: only admin/system_admin can SELECT/INSERT/UPDATE; only system_admin can DELETE. Matches the pattern of "leads are everyone-visible, but scraping internals are admin-only."

## User decisions (2026-05-18, round 5)

### Custom UI/UX, not a port
- **The Copy Agent dashboard's *visual* design is NOT used.** Different colors, modules, type system, layout. The CRM has its own aesthetic — dark/light variants, `rounded-[2.5rem]`, `font-black uppercase tracking-widest`, blue-600 accents, lucide-react icons.
- **What we port from Copy Agent: the logic layer only.** That means:
  - [agent-rpc.ts](../../Copy%20Agent/dashboard/src/lib/agent-rpc.ts) → port as-is (pure JSON-RPC 2.0 builders + parser, no visuals).
  - [useAgentWebSocket.ts](../../Copy%20Agent/dashboard/src/hooks/useAgentWebSocket.ts) → port as-is (connection lifecycle, message state, tool-activity state, approval flow).
  - Copy Agent's [components/chat/*.tsx](../../Copy%20Agent/dashboard/src/components/chat/) and [ChatPanel.tsx](../../Copy%20Agent/dashboard/src/components/layout/ChatPanel.tsx) are **structural references only** — read them to understand what props/state each component needs, then rebuild visually in CRM's design language. Do NOT copy-paste their JSX/Tailwind classes.

### Tool approval policy
- **Only SerpAPI-consuming tools require human approval.** Everything else auto-approves transparently — no friction, no popup. The agent's `request_lead_generation` is the one tool that requires explicit approval because each call costs a SerpAPI search (or, if cache hit, doesn't — but the user doesn't know that until after the call).
- **Approval prompt must show what's about to happen** — city, category, limit, an indicator like "1 SerpAPI search will be used (or 0 if cache-hit)". User can deny, approve once, or approve-always for the session.
- **Even with approval gated, the agent emits a tool-trace event the moment it decides to call the tool** — the chat shows "Searching leads: plumbers in McAllen…" alongside the approval prompt. Lets the user see the agent's intent in plain language while deciding.

### Tool-call streaming / agent trace UX
The CRM chat must render a live trace of the agent's actions, not just the final assistant message. Specifically:
- When the agent emits `tool_called`, render a status line in the chat near where the tool call sits in the conversation, e.g. "Searching leads: plumbers in McAllen (limit 15)…" with a spinner.
- When `tool_result` arrives, the same row updates to a completed state: "Searched leads: plumbers in McAllen → 18 candidates, 15 promoted, 3 already known."
- Errors show in red with the message.
- This pattern matches Copy Agent's [ToolActivity.tsx](../../Copy%20Agent/dashboard/src/components/chat/ToolActivity.tsx) **functionally**, but visually it's custom to the CRM. Industry terms: "agent trace", "execution trace", "tool-use events", "tool-call stream".

### Agent permissions on the leads table — insert-only
- **The agent must NOT be able to UPDATE or DELETE rows in `public.leads`.** No editing existing leads, no removing them. Insert only.
- **Read access from the agent is probably not needed.** Defer until a concrete use case appears (e.g., the agent wants to dedupe against existing leads — but the edge function already does that on `external_id`).
- **How this is enforced:** by tool surface, not by RLS. The agent's `request_lead_generation` tool POSTs to `generate-leads`, which does upsert-with-ignore-on-conflict. The agent has no other CRM tools, so it physically cannot call update/delete endpoints. The edge function itself never updates or deletes leads. This is a tighter and clearer guarantee than relying on the admin's JWT to be insufficiently scoped.
- For staging candidates, same principle: the agent only triggers the candidates-insert path that's already inside `generate-leads`. No separate "edit candidate" or "delete candidate" tool. Promotion/dismissal of candidates is admin-only via the CRM UI, not the agent.

## OmniAgents server invocation — confirmed

From the omniagents-basic skill ([SKILL.md:160-170](../../Copy%20Agent/omniagents-basic/SKILL.md)):

- **WebSocket server mode:** `omniagents run -c agent.yml --mode server --port 9494` — exposes JSON-RPC 2.0 at `/ws`. This is the invocation the CRM browser connects to.
- **`--session-id ID`:** resumes a previous session. Implies sessions are persisted somewhere on disk — likely under `~/.omniagents/sessions/` (TBD; verify in Phase 1).
- **`--approvals skip`:** disables tool approval prompts entirely. **Not** what we want — we still need the SerpAPI tool to be gated. We achieve auto-approval for *other* tools via `safe_tool_names` in [agent.yml](../agents/rgv_lead_scraper/agent.yml).

## User decisions (2026-05-18, round 6)

### Chat panel form factor
- **Right-side drawer**, matching the pattern of existing modal overlays in the CRM (e.g. the Register Lead modal at [LeadsView.tsx:464](../../WorkLogicly-CRM/components/LeadsView.tsx)).
- Persistent across CRM navigation. State lives at app-level (lifted into [App.tsx](../../WorkLogicly-CRM/App.tsx) or a context provider so the panel survives route changes).
- Connection (WebSocket) and message state both persist across navigation — don't tear down the WebSocket on route change.

### Chat history (deferred — not v1)
- Future feature: a sidebar list of previous chats inside the drawer. Click an item to load that conversation.
- Use OmniAgents' built-in session mechanism (`--session-id`). The agent already persists sessions; the CRM will:
  - On chat creation: generate a session id, pass it to the WebSocket on connect, record it in a Supabase table `agent_chat_sessions` (id, user_id, title, last_message_preview, created_at, last_used_at) for display.
  - On opening a past chat: pass that session id when reconnecting; OmniAgents replays the history.
- **Open question for Phase 1:** confirm what JSON-RPC method (if any) the OmniAgents WebSocket exposes for *listing* sessions and *loading* their full message history. The voice-mode docs show `list_sessions` and `get_session_info` ([voice-mode.md:177-183](../../Copy%20Agent/omniagents-basic/references/voice-mode.md)) — text mode may have equivalents or we may need to read session files off disk.
- Build this as a follow-up after v1 chat ships. Visual: a small sidebar within the drawer (collapsed by default), titled by the first user message of each conversation. Match CRM theme.

## Chat architecture — mirror the Copy Agent pattern (no hosting needed)

Reference implementation lives at `/Users/josias/Desktop/CODE/Copy Agent/` and its dashboard at `dashboard/src/`.

### How Copy Agent does it
- **OmniAgents itself exposes a WebSocket server.** Default `ws://localhost:9494/ws` (per [agent-rpc.ts:342](../../Copy%20Agent/dashboard/src/lib/agent-rpc.ts)). Configurable via `NEXT_PUBLIC_AGENT_WS_URL`.
- **Browser connects directly** via WebSocket using JSON-RPC 2.0 — no proxy, no FastAPI shim, no edge function in the middle.
- **Protocol** (from [agent-rpc.ts](../../Copy%20Agent/dashboard/src/lib/agent-rpc.ts)):
  - Outbound: `start_run { prompt }`, `get_agent_info`, `client_response { request_id, ok, result: { approved, always_approve } }`
  - Inbound: `run_started`, `tool_called`, `tool_result`, `client_request`, `message_output`, `run_end`
- **The agent runs on the user's machine.** This is a personal/local-use model, not a multi-tenant SaaS. For Lead-Scraper that's fine: only admins use this, and admins can run the agent locally before clicking around the CRM.
- **Tool approval is in-band.** When the agent wants to call a gated tool, it emits `client_request`; the UI surfaces an Approve/Deny button (with "always approve" option); user response goes back as `client_response`.

### What this means for our plan
- **No FastAPI service.** Delete Phase 2.4c entirely.
- **No `chat-with-agent` edge function.** Delete from Phase 2.4d.
- **No HMAC handshake.** Browser → WebSocket → local OmniAgents.
- **Agent writes through the same `generate-leads` edge function the form uses.** When the agent decides to scrape, it calls a tool that POSTs to `https://<project>.supabase.co/functions/v1/generate-leads` with the admin's JWT (which the chat panel passes at session start time). Same admin gate, same budget, same audit, same staging two-stage write. No duplicate logic, no special agent path.
- **Local-run trust model.** The agent runs on the admin's machine; the admin's JWT lives in the agent's environment for the session. If the admin isn't logged in, the chat panel says "log in first." Simple.

### What the agent tool looks like
- Replace [tools/lead_tools.py:run_pipeline](../agents/rgv_lead_scraper/tools/lead_tools.py) with a thin wrapper `request_lead_generation(city, category, limit)` that:
  - Does NOT touch SerpAPI directly anymore.
  - Calls the CRM's `generate-leads` edge function with the admin's JWT (from env, set by the chat panel via a startup parameter or a local config file).
  - Returns `{ leads_promoted, candidates_total, source: 'serpapi'|'cache', monthly_usage }`.
- Update [instructions.md](../agents/rgv_lead_scraper/instructions.md) so the agent knows there's one tool, it scrapes via the CRM, and budget consumption happens at the CRM layer.

The local Python `lead_scraper` CLI (`lead-scraper run`) keeps working for non-CRM batch use. The agent path and form path converge at `generate-leads`.

### Why D5/D6 still matter (Phase 1 hard-blockers stand)
- **D5 (nested asyncio):** the OmniAgents WebSocket server runs in its own event loop. Any tool that calls `asyncio.run(...)` inside that loop will crash. Must fix.
- **D6 (safe-agent gating):** if the scraping tool requires per-call user approval, every chat turn becomes "click yes" — defeats the chat UX. Mark the new `request_lead_generation` tool as auto-approved when invoked from a chat session OR keep the approval but default the UI to `always_approve: true` for admins (matches Copy Agent's pattern).
