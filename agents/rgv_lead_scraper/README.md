# RGV Lead Scraper — Agent

OmniAgents-powered chat assistant the WorkLogicly CRM connects to over a local
WebSocket. The agent has one mutating capability: calling the CRM's
`generate-leads` edge function, which the user approves per call.

## Architecture

```
Browser (CRM AgentChatPanel)
        │
        │  JSON-RPC 2.0 over WebSocket  (ws://localhost:9494/ws)
        ▼
omniagents server  ──► request_lead_generation tool
                                │
                                │  HTTPS POST + admin JWT
                                ▼
            Supabase Edge Function: generate-leads
                                │
                                ▼
                    public.leads / public.lead_candidates
```

The agent never talks to SerpAPI directly. All scraping happens inside the
edge function, where the admin gate, rate limit, monthly budget, and 14-day
search cache live (see P2.2 in `plan/task_plan.md`).

## Prerequisites

- Python 3.11+ with the project's `.venv` activated.
- The CRM is reachable and you can log in as a `system_admin` or `admin` user.
- A `SERPAPI_API_KEY` configured on the **Supabase edge function** (not here).

## Environment variables

The tool reads these from the process environment:

| Variable        | Required | Purpose                                      |
|-----------------|----------|----------------------------------------------|
| `CRM_BASE_URL`  | yes      | e.g. `https://<project>.supabase.co`         |
| `CRM_USER_JWT`  | yes      | Your CRM access token (`supabase.auth.token`)|

Grab the JWT by signing into the CRM and copying it from `localStorage` /
`sessionStorage` (the `supabase.auth.token` key). Rotate it whenever your
session expires.

## Running the agent (WebSocket mode)

The CRM's chat drawer connects to a locally-running OmniAgents server:

```sh
# from the Lead-Scraper repo root, .venv active
PYTHONPATH=src \
CRM_BASE_URL="https://<project>.supabase.co" \
CRM_USER_JWT="eyJhbGciOi..." \
  omniagents run -c agents/rgv_lead_scraper/agent.yml \
                 --mode server \
                 --port 9494 \
                 --approvals require \
                 --on-reject continue
```

Then open the CRM, navigate to **Leads**, and click **Chat with agent**.

### Why `PYTHONPATH=src`

Without it, OmniAgents starts but the `lead_scraper.*` modules fail to import
and **the agent registers with zero tools** — silent failure. P1.4c
documented this; the launch command above includes the fix.

### Approval flow

The agent gates exactly one tool: `request_lead_generation`. The CRM panel
shows an approval card with city/category/limit and a note about SerpAPI cost.
The user can:

- Approve once
- Approve always (auto-approves for the remainder of the chat session — the
  CRM client remembers this and resends `always_approve: true` per run,
  because server-side always-approve is run-scoped)
- Deny

All other tools (`get_settings_summary`, `read_file`, `list_directory`) live
in `safe_agent_options.safe_tool_names` and auto-approve transparently.

### Sessions

OmniAgents persists sessions to `~/.omniagents/sessions/default/rgv_lead_scraper/sessions.db`.
The CRM doesn't currently surface session history; that's the deferred 2.8
work. "New chat" in the CRM panel just disconnects and reconnects, giving you
a fresh server-side session.

## Local CLI mode

The Python CLI is unchanged and still scrapes locally (no CRM):

```sh
lead-scraper run --city McAllen --category plumbers
```

Use this for batch runs that intentionally bypass the CRM budget and audit
rails.

## Troubleshooting

- **"Not connected to the local agent"** in the CRM — the OmniAgents process
  isn't running, or it bound to a port other than 9494. Restart it with the
  command above.
- **"CRM_USER_JWT is not set"** in a tool result — refresh the env vars and
  restart the agent process.
- **403 / "not authorized"** from `generate-leads` — your JWT belongs to a
  non-admin user. Sign in as `system_admin` or `admin`.
- **429 / rate-limited** — you've called the tool more than three times in
  the last minute. Wait 60 seconds.
- **429 / monthly budget exhausted** — wait until the 1st of next month or
  promote leftover candidates from the CRM Candidates tab (free).
