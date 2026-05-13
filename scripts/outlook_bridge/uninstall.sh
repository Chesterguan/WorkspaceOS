#!/usr/bin/env bash
# Uninstall the Outlook Mac bridge: unload launchd job, remove plist,
# remove the copy in ~/Library/Application Support.
#
# Keeps ~/.workspaceos-bridge.json so a later reinstall doesn't need
# you to re-enter your password. Delete it manually for a clean slate.

set -euo pipefail

PLIST_LABEL="com.workspaceos.outlookbridge"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
INSTALL_DIR="$HOME/Library/Application Support/workspaceos-bridge"

launchctl bootout "gui/$UID/$PLIST_LABEL" 2>/dev/null || true
rm -f "$PLIST_PATH"
rm -rf "$INSTALL_DIR"

echo "Uninstalled. Config kept at ~/.workspaceos-bridge.json — delete it"
echo "manually if you want a clean slate."
