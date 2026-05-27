#!/bin/bash
# install-launchd.sh — install the lead-scraper agent as a macOS LaunchAgent.
#
# After running, the OmniAgents server starts at every login on port 9494 and
# restarts automatically if it crashes. Logs go to ~/Library/Logs/.
#
# Prereqs: you've already run `worklogicly-agent login` and ~/.worklogicly/
# agent.env contains CRM_BASE_URL + SUPABASE_ANON_KEY + the refresh token.

set -euo pipefail

LABEL="com.worklogicly.lead-agent"
REPO="/Users/josias/Desktop/CODE/Lead-Scraper"
SRC_PLIST="$REPO/scripts/$LABEL.plist"
DST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SRC_RUN_SCRIPT="$REPO/scripts/run-agent.sh"
# Stage the wrapper outside ~/Desktop. macOS TCC degrades launchd processes
# whose executable lives under ~/Desktop, and Python 3.14 startup crashes
# in getpath when launched that way.
DST_RUN_SCRIPT="$HOME/.worklogicly/run-agent.sh"

if [[ ! -f "$SRC_PLIST" ]]; then
  echo "ERROR: $SRC_PLIST not found" >&2
  exit 1
fi

if [[ ! -f "$SRC_RUN_SCRIPT" ]]; then
  echo "ERROR: $SRC_RUN_SCRIPT not found" >&2
  exit 1
fi

if [[ ! -f "$HOME/.worklogicly/agent.env" ]]; then
  echo "ERROR: ~/.worklogicly/agent.env not found." >&2
  echo "Run \`worklogicly-agent login\` first." >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs" "$HOME/.worklogicly"

echo "Staging wrapper to $DST_RUN_SCRIPT"
cp "$SRC_RUN_SCRIPT" "$DST_RUN_SCRIPT"
chmod +x "$DST_RUN_SCRIPT"

# If a previous version is loaded, unload it cleanly first.
if launchctl print "gui/$UID/$LABEL" >/dev/null 2>&1; then
  echo "Stopping existing $LABEL…"
  launchctl bootout "gui/$UID/$LABEL" || true
fi

echo "Installing plist to $DST_PLIST"
cp "$SRC_PLIST" "$DST_PLIST"

echo "Bootstrapping launchd service…"
launchctl bootstrap "gui/$UID" "$DST_PLIST"
launchctl enable "gui/$UID/$LABEL"
launchctl kickstart -k "gui/$UID/$LABEL" || true

sleep 1

if launchctl print "gui/$UID/$LABEL" >/dev/null 2>&1; then
  echo
  echo "Installed. Status:"
  launchctl print "gui/$UID/$LABEL" | grep -E "state|pid|exit code" | head -5
  echo
  echo "Logs:  ~/Library/Logs/worklogicly-lead-agent.{out,err}.log"
  echo "Stop:  $REPO/scripts/uninstall-launchd.sh"
else
  echo "WARNING: service did not show up in launchctl print. Check logs." >&2
  exit 1
fi
