#!/bin/bash
# run-agent.sh — launchd entry point for the lead-scraper OmniAgents server.
#
# Why a wrapper script (instead of letting launchd exec omniagents directly):
#   1. We need to source ~/.worklogicly/agent.env so CRM_BASE_URL and
#      SUPABASE_ANON_KEY land in process env. launchd's EnvironmentVariables
#      key takes literal values — it cannot source a file.
#   2. We want PYTHONPATH=src and the right working directory regardless of
#      launchd's defaults.
#   3. Logging shape is easier to control from a script.

set -euo pipefail

REPO="/Users/josias/Desktop/CODE/Lead-Scraper"
ENV_FILE="${WORKLOGICLY_AGENT_ENV:-$HOME/.worklogicly/agent.env}"
PORT="${WORKLOGICLY_AGENT_PORT:-9494}"

cd "$REPO"

if [[ -f "$ENV_FILE" ]]; then
  # Load CRM_BASE_URL + SUPABASE_ANON_KEY (and anything else the user added).
  # Token keys are read by the agent process directly from $ENV_FILE — they
  # don't need to be in process env.
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -z "${CRM_BASE_URL:-}" || -z "${SUPABASE_ANON_KEY:-}" ]]; then
  echo "ERROR: CRM_BASE_URL and SUPABASE_ANON_KEY must be set in $ENV_FILE" >&2
  exit 78  # EX_CONFIG
fi

export PYTHONPATH="src"
export AGENT_MODE="${AGENT_MODE:-local}"

exec "$REPO/.venv/bin/omniagents" run \
  -c agents/rgv_lead_scraper/agent.yml \
  --mode server \
  --port "$PORT" \
  --approvals require \
  --on-reject continue
