# OmniAgents session API surface

**Phase:** 1.4c
**Date:** 2026-05-19
**Worktree:** f86f9 (`phase/1.4c-session-api`)
**OmniAgents version:** 0.6.43 (`/opt/homebrew/lib/python3.14/site-packages/omniagents`)
**Status:** complete — all four scope bullets verified empirically against a live `--mode server` instance.

> **Why this doc exists.** Phase 2.4b (CRM chat surface) needs to know exactly how to talk to OmniAgents over the wire, and the deferred Phase 2.8 (chat-history sidebar) needs to know whether a list-sessions API exists or whether the CRM has to maintain its own index. Both are answered here.

Evidence: `plan/p14c_evidence/probe_ws.py` + `plan/p14c_evidence/session_api_probe.log` + `plan/p14c_evidence/server.log`.

---

## 1. WebSocket invocation

```
python3 -m omniagents run -c agents/rgv_lead_scraper/agent.yml \
    --mode server --host 127.0.0.1 --port 9495
```

- **`--mode server`** exists and works. `python3 -m omniagents run --help` lists it as `{server, ink, web}` (web is default).
- **Default port is `8000`, not `9494`.** SKILL.md uses `9494` as a convention; pick any free port via `--port`.
- **WebSocket endpoint: `/ws`.** JSON-RPC 2.0 framing — every request/response carries `jsonrpc: "2.0"`, `id`, and either `method`+`params` or `result`/`error`. Notifications (`run_started`, `tool_called`, `tool_result`, `message_output`, `run_end`, `token`) have no `id`.
- **Auth:** add `--auth-token <secret>` if exposing beyond localhost. Default: no auth.
- **For our agent specifically:** custom tool registration requires `PYTHONPATH=src` (or `pip install -e .`) so the `lead_scraper.*` imports inside `agents/rgv_lead_scraper/tools/lead_tools.py` resolve. Without it, `tools.lead_tools` fails to import and the agent boots without `run_pipeline` / `run_stage`. The session-API probes still work because the session methods live on `AgentService`, not the tool registry — but Phase 2.4b launch instructions need this.

---

## 2. Where sessions persist on disk

`~/.omniagents/sessions/<project_slug>/<agent_slug>/sessions.db` — **a SQLite database, not a directory tree.**

For our agent the path resolves to:
```
~/.omniagents/sessions/default/rgv_lead_scraper/sessions.db
```
At time of probe: 33 sessions, 254 history rows from prior Phase 1.4 / 1.4b runs.

Both `project_slug` and `agent_slug` default to `"default"` if not set, then are normalised to lowercase alnum + `-`/`_` (see `omniagents/core/paths.py:get_sessions_db_path`). The `rgv_lead_scraper` slug comes from the agent name; the `default` project comes from there being no `project.yml`.

### Schema (verified via `sqlite3 ... .schema`)
```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    archived INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    context_json TEXT,
    variables_json TEXT,
    hold INTEGER DEFAULT 0,
    user_id TEXT
);
CREATE TABLE history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    msg_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE audio_metadata (...);  -- voice-mode only
CREATE INDEX idx_history_session_id ON history(session_id, id);
CREATE INDEX idx_sessions_created_at ON sessions(created_at);
```

### Overrides
- `OMNIAGENTS_HOME` → relocate the whole `~/.omniagents` tree.
- `OMNIAGENTS_HISTORY_DB` → point a single agent's session DB at an arbitrary file.

### CLI helpers (don't reinvent)
```
omniagents sessions db-path           # prints the resolved sessions.db path
omniagents sessions list              # list, search, export
```

---

## 3. JSON-RPC methods available in text mode

Probed live against `--mode server` on 9495. Source: `omniagents/core/agents/service.py`.

| Method | Text mode? | Notes |
|---|---|---|
| `get_agent_info` | ✅ | returns `{name, welcome_text}` |
| `start_run` | ✅ | params: `{prompt, session_id?}` |
| `stop_run` | ✅ | params: `{run_id}` |
| `send_user_message` | ✅ | mid-run input |
| `list_sessions` | ✅ | returns `[{id, archived, created_at, message_count, first_message, last_message}]` |
| `get_session_history` | ✅ | params: `{session_id}` → `[{role, content, …}]` |
| `fork_session` | ✅ | |
| `archive_session` | ✅ | |
| `delete_session` | ✅ | |
| `set_session_hold` | ✅ | |
| `export_session` | ✅ | |
| `get_user_history` | ✅ | |
| `client_response` / `tool_approval_response` | ✅ | approval-flow plumbing |
| **`get_session_info`** | **❌** | **`-32601 "Method not found"` in text mode.** Voice/realtime-only — defined at `omniagents/core/rpc/realtime_service.py:241`. |

### 3.1 `list_sessions` return shape (verified)
```jsonc
{
  "id": "probe-c50a6a64",
  "archived": false,
  "created_at": "2026-05-19 14:12:29",
  "message_count": 2,
  "first_message": { "role": "user", "content": "…", "timestamp": "…" },
  "last_message":  { "role": "assistant", "content": [{"text": "PONG", "type": "output_text", ...}], ... }
}
```
Returned ordered by `created_at` (descending, per the `idx_sessions_created_at` index — sort client-side if you need a specific order).

### 3.2 `get_session_history` return shape (verified)
A flat array of message dicts in chronological order:
```jsonc
[
  { "role": "user", "content": "Reply with exactly the word PONG ..." },
  { "id": "msg_…", "role": "assistant", "type": "message", "status": "completed",
    "content": [{ "type": "output_text", "text": "PONG", "annotations": [], "logprobs": [] }] }
]
```
Roles and content shape mirror the OpenAI Responses-API message format. Tool calls and tool results appear inline as additional entries when present.

### 3.3 What the CRM gets from a `start_run` (notification stream)
In chronological order over the same `/ws`:
- `run_started` `{run_id, session_id}`
- 0+ `tool_called` `{tool, args, …}`
- 0+ `client_request` (only for tools not in `safe_tool_names` — currently just `run_pipeline` / `run_stage`)
- 0+ `tool_result`
- 0+ `message_output` (assistant turn text)
- 0+ `token` (streaming deltas — ignore unless we add streaming UI)
- 1 `run_end` `{end_reason: "completed" | …}`

---

## 4. Session resume verified end-to-end

Reconnect with the same `session_id` and the agent has the prior turn's context. Empirical transcript:

```
Probe 2 (run 1): session_id=probe-c50a6a64
  prompt: "Reply with exactly the word PONG and nothing else."
  message_output: PONG
  run_end: completed
[disconnect]

Probe 4 (run 2): session_id=probe-c50a6a64  (FRESH WebSocket)
  prompt: "What was the exact one-word reply you just gave in your previous turn? Quote it."
  message_output: "PONG"
  run_end: completed
```

Between the two runs the session showed `message_count: 2` in `list_sessions` (user prompt + assistant reply). After run 2 it would be 4. **The session_id is the only thing required to resume — no replay payload, no snapshot — full conversational context is restored server-side from the SQLite history.**

---

## 5. Recommended wiring for Phase 2.4b + 2.8

### 2.4b CRM chat surface (active phase)
1. **Browser opens WS** directly to the agent process at `ws://<agent-host>:<port>/ws`. No edge function in the loop for chat.
2. **Generate a fresh `session_id`** (UUID) on "New chat" and pass it in every `start_run`. Persist the mapping `{crm_user_id, session_id, title, created_at}` in a new Supabase table `agent_chat_sessions` (planned in 2.8) so the CRM can scope sessions per-user — OmniAgents itself has no per-user partitioning beyond the `user_id` column we'd have to populate.
3. **Approval flow:** listen for `client_request` with `params.function == "ui.request_tool_approval"` and surface a yes/no UI. Reply via `client_response`. Only `run_pipeline` / `run_stage` gate (confirmed in 1.4b); `get_settings_summary`, `read_file`, `list_directory` auto-approve per `safe_tool_names`.
4. **Status notifications** also arrive as `client_request` but with `params.function == "ui.set_status"` — these are NOT approval gates; filter on `params.function` before showing an approval modal.

### 2.8 Chat-history sidebar (deferred)
- **Primary path: `list_sessions` over WS** — every field the sidebar needs is already there (id, created_at, message_count, first_message preview, last_message preview).
- **Per-session detail: `get_session_history`** — full transcript replay for the selected chat.
- **Per-user scoping** is the CRM's responsibility: store `{crm_user_id, session_id}` in `agent_chat_sessions` and intersect with `list_sessions` results client-side, OR populate the OmniAgents `sessions.user_id` column on `start_run` and filter on it.
- **DO NOT** read `sessions.db` directly from the browser. The DB file is process-local to whatever host runs `omniagents run`, and concurrent access during writes can lock the DB. Always go through JSON-RPC.

### Minimum-viable client (TypeScript sketch)
```ts
const ws = new WebSocket(`ws://${AGENT_HOST}:${AGENT_PORT}/ws`);
let nextId = 0;
const rpc = (method: string, params: object = {}) => {
  const id = String(++nextId);
  ws.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
  return new Promise((resolve) => {
    const handler = (e: MessageEvent) => {
      const msg = JSON.parse(e.data);
      if (msg.id === id) { ws.removeEventListener("message", handler); resolve(msg); }
    };
    ws.addEventListener("message", handler);
  });
};

// New chat
const sessionId = crypto.randomUUID();
await rpc("start_run", { prompt: userText, session_id: sessionId });

// Sidebar
const { result: sessions } = await rpc("list_sessions") as { result: Session[] };

// Open old chat
const { result: history } = await rpc("get_session_history", { session_id: pickedId });

// Continue old chat — reuse the same session_id, that's all
await rpc("start_run", { prompt: newText, session_id: pickedId });
```

---

## 6. Open caveats for downstream phases

1. **Slug binding.** The DB path is keyed on `(project_slug, agent_slug)`. If we ever rename the agent in `agent.yml`, existing sessions will be orphaned at the old path. Lock the slug or set `OMNIAGENTS_HISTORY_DB` to a stable absolute path.
2. **No server-side pagination.** `list_sessions` returns everything. For the 2.8 sidebar, page client-side (or sort + slice). Filter on `archived=false` for the default view.
3. **No server-side rename.** Session "title" doesn't exist in OmniAgents — derive from `first_message` for display, or store a CRM-owned title in `agent_chat_sessions`.
4. **Audit trail.** The CRM `lead_audit_log` table (Phase 2) is the source of truth for who-approved-what. OmniAgents history is the source of truth for what-the-model-said. Don't conflate them.
5. **Single-process write lock.** SQLite under uvicorn is fine for one server, but if we ever run multiple agent processes against the same DB they'll contend. Each (project_slug, agent_slug) gets its own file, so use slugs as the partition.
6. **`get_session_info` references in the deferred 2.8 design are red herrings** — that method is voice/realtime only. Use `list_sessions` + `get_session_history` instead.
