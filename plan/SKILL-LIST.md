# Agent Skill List

Catalog of named, structured procedures the **RGV Lead Scraper** agent should
follow so it never stalls between tool calls. Each skill is a self-contained
recipe — trigger phrases, tools used, ordered steps, failure handling — so the
agent has a clear path for every common situation instead of free-associating
its way to silence.

**How this gets used:** once a skill is approved here, port it into
[`agents/rgv_lead_scraper/instructions.md`](../agents/rgv_lead_scraper/instructions.md)
as a numbered section (or pull into a loadable skill file if the project moves
to a skills directory). This file is the design surface; `instructions.md` is
the runtime surface.

**Statuses:**
- `proposed` — drafted here, not yet in instructions.md
- `active` — present in instructions.md and live
- `deferred` — recognized as needed but not prioritized

---

## 1. `scrape-new-leads` — fresh Google Maps search → CRM

**Status:** `active` (mostly — codify the failure branches)
**Trigger phrases:** "find 10 plumbers in McAllen", "scrape HVAC companies in Edinburg", "get me 5 landscapers in Mission".
**Tools used:** `request_lead_generation`.
**Mutates CRM:** yes (gated by user approval).

**Steps:**
1. Extract `city`, `category`, `limit` from the user's message. Default `limit=10` if absent; cap at 20.
2. State the action verbatim: "I'll search Google Maps for {limit} {category} in {city}. This may use 1 paid SerpAPI search unless the same query was cached in the last 14 days."
3. Wait for the approval gate (the host raises `ui.request_tool_approval`).
4. Call `request_lead_generation(city, category, limit)` exactly once.
5. On success, summarize from the envelope: `{candidates_total} found, {leads_promoted} added to leads, {duplicates} already in CRM, source: {fresh search | cache}`.
6. End the turn. Do not chain another tool unless the user asks.

**Failure branches:**
- Tool returns `{ok: false, error: "auth_required"}` → switch to skill 5 (`handle-auth-failure`).
- Tool returns 429 (rate-limit) → tell user "Hit per-minute rate limit — try again in 60s" and stop.
- Tool returns 429 with `budget exhausted` → switch to skill 6 (`handle-budget-exhausted`).
- Any other error → paraphrase the message, suggest skill 2 (`review-staged-candidates`) as the free alternative.

**Known pitfalls:**
- Do NOT call `request_lead_generation` more than once per turn — each call may cost a paid search.
- Do NOT silently fall back to a different city/category if the user's request was unambiguous.

---

## 2. `review-staged-candidates` — read-only staging inspection

**Status:** `active` (codify the filter mapping)
**Trigger phrases:** "what candidates do we have", "show staged leads", "list HVAC candidates in McAllen", "any plumbers without websites?".
**Tools used:** `list_lead_candidates`.
**Mutates CRM:** no.

**Steps:**
1. Parse filter intent from the message. Map natural-language predicates to tool args:
   - "no website" / "without a website" → `website_is_null=true`
   - "rated X or higher" → `min_rating=X`
   - "fewer than N reviews" → `max_review_count=N-1`
   - "in McAllen" → `city="McAllen"`
   - "plumbers" → `category="plumbers"`
2. Call `list_lead_candidates(...)` once with the parsed filters and `limit` ≤ 20 (default 10).
3. Present results as a numbered list. **Always include each row's `id` (UUID)** — it's required for skill 3.
4. End the turn with the suggestion: "Reply `promote #N` (or list multiple) and I'll add them to your leads."

**Failure branches:**
- Empty result set → say so explicitly: "No candidates match those filters." Suggest skill 1 to scrape fresh.
- `auth_required` → skill 5.

**Known pitfalls:**
- Do NOT drop the `id` from the presentation just because it's ugly — skill 3 depends on it being in conversation history.
- Do NOT auto-chain to a promote. Listing is its own complete turn.

---

## 3. `promote-from-staging` — list → select → promote

**Status:** `active` (the procedure that broke before instructions.md fix; codify it)
**Trigger phrases:** "promote #1", "promote Miravalle Construction", "add the top 3 to leads", "promote the no-website ones".
**Tools used:** (optionally `list_lead_candidates`), then `promote_lead_candidates`.
**Mutates CRM:** yes (gated by user approval).

**Steps:**
1. Resolve the user's selection to concrete UUIDs:
   - If the prior turn already produced a `list_lead_candidates` result, map "#N" / business names to UUIDs from that result.
   - Otherwise, call `list_lead_candidates` first with whatever filter narrows it down (e.g. by business name).
2. If you cannot confidently map the selection to UUIDs, ask one clarifying question. Do NOT guess.
3. Call `promote_lead_candidates(candidate_ids=[...])` once, batching all requested IDs into a single call.
4. Summarize from the envelope: `{total_succeeded}/{total_requested} promoted. {failed} failed: {reasons}`.
5. End the turn.

**Failure branches:**
- Selection ambiguous ("promote the McAllen one" but result has 3 McAllen rows) → ask which one. Do not guess.
- `auth_required` → skill 5.
- Any individual ID returns `already_existed: true` → mention it ("Miravalle was already a lead — no duplicate created").

**Known pitfalls — load-bearing:**
- NEVER invent a `candidate_id`. If it's not in conversation history and not returnable from `list_lead_candidates`, stop and ask.
- ONE `promote_lead_candidates` call per turn, batched. Do not loop one-ID-per-call (defeats the gather/semaphore).
- The cross-turn `function_call`/`reasoning` reload is the OmniAgents bug that originally killed this flow. If the agent goes silent here, see `findings.md` "Phase 3 trigger" — the workaround is wiping `~/.omniagents/sessions/default/rgv_lead_scraper/sessions.db`; the fix is Phase 3.

---

## 4. `clarify-vague-request` — ask one targeted question

**Status:** `active` (already documented, codify as a skill for consistency)
**Trigger phrases:** "find me some leads", "more leads", "HVAC", "what's in McAllen?".
**Tools used:** none — this is a turn that explicitly does NOT call a tool.
**Mutates CRM:** no.

**Steps:**
1. Identify exactly which field is missing: `city`, `category`, or both.
2. Ask one question that surfaces the missing field. Examples:
   - "Which city — McAllen, Edinburg, Mission, Brownsville?"
   - "What category — plumbers, HVAC, landscapers, construction?"
   - Both missing → "Which city and category should we search?"
3. End the turn. Do not chain a scrape.

**Failure branches:**
- User answers vaguely again ("any city") → suggest a default ("I'll use McAllen unless you tell me otherwise — okay?") and wait.

**Known pitfalls:**
- Don't ask MORE than one question per turn — clarification fatigue.
- Don't default-fill missing fields silently. That was the P1.4 finding (F-1/F-2).

---

## 5. `handle-auth-failure` — JWT expired or refresh token gone

**Status:** `proposed`
**Trigger:** any tool returns `{ok: false, error: "auth_required"}` or the `_LOGIN_HINT` payload.
**Tools used:** none — this is recovery messaging.
**Mutates CRM:** no.

**Steps:**
1. Stop. Do NOT retry the failed tool. Do NOT call any other CRM tool.
2. Tell the user exactly what to do:
   > "CRM credentials are expired. Run **`worklogicly-agent login`** in a terminal (or `/Users/josias/Desktop/CODE/Lead-Scraper/.venv/bin/worklogicly-agent login` if the CLI isn't on PATH), then say 'retry' and I'll re-run what you asked."
3. Remember (within the chat session) what the user was trying to do so you can resume on "retry".
4. End the turn.

**Failure branches:**
- User says "retry" but auth is still missing → repeat step 2 with the same message.
- User says "retry" and auth works → re-run the original skill that failed (1, 2, or 3).

**Known pitfalls:**
- Do NOT call `get_settings_summary` repeatedly to "check" auth — the failed tool's response is authoritative.
- Do NOT tell the user to restart the agent server; auth is read from disk per request.

---

## 6. `handle-budget-exhausted` — monthly SerpAPI cap reached

**Status:** `proposed`
**Trigger:** `request_lead_generation` returns 429 with a budget-exhausted message (hard cap 250/month).
**Tools used:** can suggest skill 2 (`review-staged-candidates`) as the SerpAPI-free alternative.
**Mutates CRM:** no.

**Steps:**
1. Tell the user the budget is exhausted and resets on the 1st of the month.
2. Offer the free alternative: "I can still review what's already staged in your candidates — want me to list them?"
3. If user says yes → switch to skill 2.
4. End the turn.

**Known pitfalls:**
- Do NOT keep trying `request_lead_generation` "just in case" — the cap is server-enforced and unconditional.
- Do NOT suggest "force_refresh" — that just makes the failure louder.

---

## 7. `explain-dedupe` — user asks why a lead isn't showing up

**Status:** `proposed`
**Trigger phrases:** "why didn't X appear?", "I searched for Y but only got 5 leads", "where's the duplicate?".
**Tools used:** `list_lead_candidates` (to inspect staging) — optionally.
**Mutates CRM:** no.

**Steps:**
1. Explain the dedupe model in one sentence: "The CRM dedupes by `external_id` (Google Maps place_id). If a business was already in your `leads` or `lead_candidates` table from a prior scrape, the new scrape ignored it instead of creating a duplicate."
2. Offer to look: "I can list staged candidates filtered by business name if you want to confirm."
3. If user accepts → call `list_lead_candidates(category=..., city=...)` and search the returned names locally before presenting.
4. End the turn.

**Known pitfalls:**
- Do NOT promise to "force a re-add" — there's no tool for that. The CRM is upsert-with-ignore-on-conflict by design.

---

## 8. `sequential-multi-target` — multiple cities or categories in one request

**Status:** `proposed`
**Trigger phrases:** "scrape plumbers in McAllen and Edinburg", "find HVAC and electricians in Mission".
**Tools used:** `request_lead_generation` (one call per (city, category) pair, sequential across turns).
**Mutates CRM:** yes (each call gated).

**Steps:**
1. Enumerate the (city, category) pairs from the request. List them back to the user: "I'll run 2 searches: plumbers in McAllen, plumbers in Edinburg. Each may use 1 SerpAPI search."
2. Run the FIRST pair via skill 1 (`scrape-new-leads`).
3. After it returns, in the SAME turn or the next, ask: "Continue to next: {pair 2}?" — wait for confirmation.
4. On confirmation, run the next pair. Repeat until done.
5. After the last pair, give a combined summary.

**Failure branches:**
- Budget exhausted mid-sequence → skill 6, abort remaining pairs.
- User says stop → stop immediately, summarize what was done.

**Known pitfalls:**
- Do NOT batch multiple pairs into a single `request_lead_generation` call — the tool doesn't support it.
- Do NOT proceed to pair N+1 without per-pair user confirmation (each costs money).

---

## 9. `refuse-out-of-scope` — edit/delete/non-CRM requests

**Status:** `proposed`
**Trigger phrases:** "delete Bello Construction", "change Miravalle's phone number", "merge these two leads", "send an email to...".
**Tools used:** none.
**Mutates CRM:** no.

**Steps:**
1. State plainly what you can't do: "I can't edit, update, delete, or merge existing leads — there's no tool that exposes those operations to me. That's an admin-only manual action in the CRM UI."
2. Offer the closest thing you CAN do: "I can scrape fresh leads or promote from staging — anything along those lines?"
3. End the turn.

**Known pitfalls:**
- Do NOT pretend to attempt the action. Saying "I'll try..." then doing nothing is worse than refusing upfront.
- Do NOT call `list_lead_candidates` to "find" a lead for an action you can't perform.

---

## Skill-selection decision table

Use this when the user's intent is ambiguous between two skills:

| User says... | Skill |
|---|---|
| Names a city + category + count | 1 — scrape-new-leads |
| Just "find me leads" / one of the two fields missing | 4 — clarify-vague-request |
| "Show / list / what candidates" | 2 — review-staged-candidates |
| "Promote / add to leads / pick #N" | 3 — promote-from-staging |
| Tool returned auth_required | 5 — handle-auth-failure |
| Tool returned budget exhausted | 6 — handle-budget-exhausted |
| "Why didn't X appear / show up" | 7 — explain-dedupe |
| Multiple cities or categories | 8 — sequential-multi-target |
| Edit / delete / merge / non-CRM | 9 — refuse-out-of-scope |

---

## Implementation order (recommended)

1. **Skills 1, 2, 3** — port into `instructions.md` as numbered sections. These three together solve the failures we've actually seen (silent-after-promote, refused-to-promote, vague-list-no-IDs). Do this first.
2. **Skill 5** — auth failure recovery. High-frequency once JWTs start expiring.
3. **Skill 4** — clarify-vague-request is already partially in `instructions.md`; bring it up to the same format.
4. **Skills 6, 7, 8, 9** — codify after the first batch is proven in chat.

---

## Open questions

- **Skill file format vs inline instructions.** Should each skill become a standalone `agents/rgv_lead_scraper/skills/<name>.md` loaded into context, or stay as numbered sections in `instructions.md`? Standalone scales better (one skill = one file, easy to test in isolation) but inline is simpler to ship.

**Answer** You're right some of these 'skills' don't need to be skills they can you just be put directly in the `instructions.md` file. The first 3 skills are legit skills that do need to be their own files. I misread the question but either way what I answered is true. Some of these skills don't need to be skills. 

- **Phase 3 interaction.** If Phase 3 lands (filter-predicate direct promote), skill 3 (`promote-from-staging`) becomes secondary — the natural flow becomes "scrape with filters, done." Skill 3 stays for the cases where filters under-match. Worth re-reading this list after Phase 3 is decided.

I think we should ship phase 3 but if it becomes a hundful we'll revert to the current version of the agent that we have.

- **Per-skill telemetry.** Should `instructions.md` ask the agent to announce the skill name at turn start ("Using skill: scrape-new-leads")? Helps debug stalls but is verbose for users.

**Answer** No but we're going to add a agent skill trail similar to the tool call trail. Also we need to improve the UI/UX of that call trail. We'll work on that later.
