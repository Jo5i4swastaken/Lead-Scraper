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
#
# IMPORTANT: install-launchd.sh COPIES this script to ~/.worklogicly/. The
# plist's ProgramArguments point at that copy, not at this one. Reason:
# macOS TCC silently degrades launchd-spawned processes whose executable
# lives under ~/Desktop, ~/Documents, or ~/Downloads — Python startup
# crashes with ``OSError: failed to make path absolute`` in getpath. The
# repo lives in ~/Desktop, so we stage the wrapper outside of it. Edit the
# in-repo copy and re-run install-launchd.sh to sync.

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

# Resolve the upstream Homebrew Python instead of going through the venv's
# python symlink. Under launchd with KeepAlive=true, Python 3.14's getpath
# bootstrap crashes ("OSError: failed to make path absolute") when invoked
# via the venv's python symlink chain. Calling the brew interpreter directly
# and pointing PYTHONPATH at the venv's site-packages sidesteps that bug.
# Reading ``home`` from pyvenv.cfg keeps this stable across ``brew upgrade``
# inside the same Python minor version.
PY_NAME="$(readlink "$REPO/.venv/bin/python")"                                            # e.g. python3.14
PY_HOME="$(sed -nE 's/^home[[:space:]]*=[[:space:]]*//p' "$REPO/.venv/pyvenv.cfg")"      # e.g. /opt/homebrew/opt/python@3.14/bin
PYTHON_BIN="$PY_HOME/$PY_NAME"
VENV_SITE_PACKAGES="$REPO/.venv/lib/$PY_NAME/site-packages"

# `agents` is on PYTHONPATH so the `rgv_lead_scraper` package (which lives
# at agents/rgv_lead_scraper/) resolves as a plain filesystem import. The
# editable .pth in $VENV_SITE_PACKAGES is NOT processed when site-packages
# is on PYTHONPATH (.pth files only execute via site.py for real site
# directories), so we can't rely on the editable install to expose it.
# Without this, OmniAgents' tool discovery fails to import
# rgv_lead_scraper.tools.lead_tools and silently drops the four lead-gen
# tools — leaving only the `read_file` / `list_directory` builtins
# registered, even though agent.yml still loads.
export PYTHONPATH="src:agents:$VENV_SITE_PACKAGES"
export AGENT_MODE="${AGENT_MODE:-local}"

exec "$PYTHON_BIN" -m omniagents run \
  -c agents/rgv_lead_scraper/agent.yml \
  --mode server \
  --port "$PORT" \
  --approvals require \
  --on-reject continue
