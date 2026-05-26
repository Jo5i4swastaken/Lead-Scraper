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
                                │  HTTPS POST + admin JWT (auto-refreshed)
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

The agent reads these from the process environment (or from
`~/.worklogicly/agent.env`, which the `worklogicly-agent login` command
also writes):

| Variable             | Required | Purpose                                                |
|----------------------|----------|--------------------------------------------------------|
| `CRM_BASE_URL`       | yes      | e.g. `https://<project>.supabase.co`                   |
| `SUPABASE_ANON_KEY`  | yes      | Project anon (publishable) key — needed for refresh    |
| `AGENT_MODE`         | no       | `local` (default) or `hosted` (see *Hosted mode* below) |
| `SUPABASE_URL`       | hosted   | Same value as `CRM_BASE_URL`; read by the hosted server |
| `WORKSPACE_ROOT`     | no       | Hosted only — default `/tmp/worklogicly-lead-agent`     |
| `PORT` / `HOST`      | no       | Hosted only — defaults `9494` / `0.0.0.0`               |
| `WORKLOGICLY_AGENT_ENV` | no    | Override path to the token file (default `~/.worklogicly/agent.env`) |

JWTs are no longer pasted by hand. The agent obtains them via the
Supabase **password grant** on first login and then keeps a fresh
access token alive by silently exchanging the refresh token before
each call (and once reactively on any 401).

## First-time setup

```sh
# from the Lead-Scraper repo root, .venv active
pip install -e .

# point the CLI at your CRM (these can also live in your shell rc)
export CRM_BASE_URL="https://<project>.supabase.co"
export SUPABASE_ANON_KEY="<anon-key>"

# interactive login — prompts for email + password, writes
# ~/.worklogicly/agent.env (mode 0600) with the access + refresh pair
worklogicly-agent login

# start the agent server the CRM chat drawer connects to
omniagents run -c agents/rgv_lead_scraper/agent.yml \
               --mode server \
               --port 9494 \
               --approvals require \
               --on-reject continue
```

Then open the CRM, navigate to **Leads**, and click **Chat with agent**.

### Re-authenticate

Run `worklogicly-agent login` again whenever:

- the chat surfaces a tool result that says *"credentials expired"*
  (this means the refresh token itself was revoked — typically after
  password rotation or an explicit logout elsewhere), or
- you switch the CRM you point at by changing `CRM_BASE_URL`.

The new tokens overwrite `~/.worklogicly/agent.env` atomically. There
is no need to restart the agent process; the next tool call will pick
up the rotated pair.

### Auto-start at login (launchd)

To skip the manual `omniagents run …` step every time you log into your
Mac, install the agent as a macOS LaunchAgent:

```sh
./scripts/install-launchd.sh
```

This copies `scripts/com.worklogicly.lead-agent.plist` into
`~/Library/LaunchAgents/`, bootstraps it via `launchctl`, and starts the
server on port 9494. `RunAtLoad=true` + `KeepAlive=true` mean the
process starts at every login and restarts within ~10s if it crashes.

Logs:

```sh
tail -f ~/Library/Logs/worklogicly-lead-agent.out.log
tail -f ~/Library/Logs/worklogicly-lead-agent.err.log
```

Inspect/control the service:

```sh
launchctl print "gui/$UID/com.worklogicly.lead-agent"     # status
launchctl kickstart -k "gui/$UID/com.worklogicly.lead-agent"  # restart
./scripts/uninstall-launchd.sh                                  # remove
```

The plist runs `scripts/run-agent.sh`, which sources
`~/.worklogicly/agent.env` (so `CRM_BASE_URL` and `SUPABASE_ANON_KEY`
land in process env) and execs `omniagents`. Token refresh continues to
work because `TokenStore.save_atomic` preserves the static config keys
in the env file across rewrites.

### Hosted mode (preview)

Local mode is one process per macOS user, talking to one CRM identity. Hosted
mode (step 3 of the deploy plan, foundation only — not yet wired to the CRM
UI) runs the same agent process as a multi-tenant service. Each CRM admin
connects over WebSocket with their Supabase access token; the agent uses
*that* token to call `generate-leads`, so per-user rate limits, RLS, and the
admin gate all apply normally.

```sh
export AGENT_MODE=hosted
export SUPABASE_URL="https://<project>.supabase.co"      # required
export SUPABASE_ANON_KEY="<anon-key>"                    # required
export OPENAI_API_KEY="sk-…"                             # required by the agent
export WORKSPACE_ROOT="/tmp/worklogicly-lead-agent"      # optional, default shown
export PORT=9494                                         # optional, default shown
export HOST=0.0.0.0                                      # optional, default shown
export AGENT_YML="agents/rgv_lead_scraper/agent.yml"     # optional, default shown
worklogicly-agent-server
```

#### Authentication shape

Browsers can't set arbitrary `Authorization:` headers on a WebSocket
handshake, so the access token rides as the second value of the
`Sec-WebSocket-Protocol` header:

```
Sec-WebSocket-Protocol: bearer, <supabase-access-token>
```

The server echoes back `bearer` as the selected subprotocol. For
non-browser tools (wscat, curl-based smoke tests) a `?token=…` query
parameter is accepted as a fallback. Validation hits
`{SUPABASE_URL}/auth/v1/user` — that's authoritative for both signature
and revocation. Results are cached for ~60s keyed by SHA-256 of the
token so rapid messages on the same connection don't hammer GoTrue.

A missing or invalid token closes the WebSocket with close code **4401**
(`Unauthorized` in our private 4xxx range, per RFC 6455 §7.4.2).

#### Known constraint — OmniAgents single-tenancy (0.6.53)

OmniAgents' `AgentService` keeps the "current connection" on a single
instance attribute (`self.channel`). With more than one WebSocket open
concurrently the framework would emit events to the wrong client. The
hosted server mitigates this with a process-wide `asyncio.Lock` that
serialises message dispatch one-at-a-time. This is correct but caps
end-to-end throughput at one in-flight RPC across the whole server.

At our scale (single-digit admins per CRM, request every few seconds,
SerpAPI is the bottleneck anyway) this is invisible. The right
long-term fix is upstream — either an explicit per-connection channel
threaded through tool dispatch, or instantiating a fresh AgentService
per WebSocket. Until then, the constraint is documented in
`server/app.py`.

### Why `pip install -e .`

The agent's `auth/` and `cli/` packages live under
`agents/rgv_lead_scraper/` but are exposed as the installable
`rgv_lead_scraper` package. Without an editable install the
`worklogicly-agent` console script won't be on `$PATH` and
`lead_tools.py` will fall back to a sys.path shim. The shim works but
is intentionally a backstop — prefer the install.

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
- **"Your CRM credentials are missing or expired"** in a tool result —
  the refresh token is gone or has been revoked. Run
  `worklogicly-agent login` again; no agent restart needed.
- **`worklogicly-agent: command not found`** — you haven't run
  `pip install -e .` in this venv, or the venv isn't active.
- **403 / "not authorized"** from `generate-leads` — your JWT belongs to a
  non-admin user. Sign in as `system_admin` or `admin`.
- **429 / rate-limited** — you've called the tool more than three times in
  the last minute. Wait 60 seconds.
- **429 / monthly budget exhausted** — wait until the 1st of next month or
  promote leftover candidates from the CRM Candidates tab (free).
