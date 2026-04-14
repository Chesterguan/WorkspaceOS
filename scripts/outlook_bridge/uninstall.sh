#!/usr/bin/env bash
# Uninstall the Outlook Mac bridge: unload launchd job, remove plist.
# Keeps ~/.projectscribe-bridge.json so a later reinstall doesn't need
# you to re-enter your password.

set -euo pipefail

PLIST_LABEL="com.projectscribe.outlookbridge"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

launchctl bootout "gui/$UID/$PLIST_LABEL" 2>/dev/null || true
rm -f "$PLIST_PATH"

echo "Uninstalled. Config kept at ~/.projectscribe-bridge.json — delete it"
echo "manually if you want a clean slate."
