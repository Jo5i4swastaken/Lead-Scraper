#!/bin/bash
# uninstall-launchd.sh — remove the lead-scraper LaunchAgent.

set -euo pipefail

LABEL="com.worklogicly.lead-agent"
DST_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if launchctl print "gui/$UID/$LABEL" >/dev/null 2>&1; then
  echo "Stopping $LABEL…"
  launchctl bootout "gui/$UID/$LABEL" || true
fi

if [[ -f "$DST_PLIST" ]]; then
  echo "Removing $DST_PLIST"
  rm -f "$DST_PLIST"
fi

echo "Done. Logs at ~/Library/Logs/worklogicly-lead-agent.{out,err}.log are NOT removed."
