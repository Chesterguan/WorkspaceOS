#!/usr/bin/env bash
# WorkspaceOS Outlook Bridge — installer
#
# Prompts for backend URL + login, obtains a JWT via /auth/login, writes
# a 0600 config file at ~/.workspaceos-bridge.json, copies the bridge
# into a stable user-owned location, and generates a launchd plist that
# fires it every 30 minutes.
#
# Why the copy? If the repo lives on an external volume
# (`/Volumes/...`), launchd's python3 is denied access by macOS TCC — we
# saw this first-hand: ~150 logged failures with "Operation not
# permitted". Copying bridge.py + sync.applescript into
# ~/Library/Application Support/ sidesteps TCC entirely because anything
# under $HOME/Library is readable by user processes by default.
#
# Safe to re-run — overwrites the config + plist + installed files.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_BRIDGE_PY="$SCRIPT_DIR/bridge.py"
SRC_APPLESCRIPT="$SCRIPT_DIR/sync.applescript"

if [[ ! -f "$SRC_BRIDGE_PY" || ! -f "$SRC_APPLESCRIPT" ]]; then
  echo "ERR: bridge.py or sync.applescript missing in $SCRIPT_DIR" >&2
  exit 1
fi

# Installed location — stable, user-owned, no TCC issues
INSTALL_DIR="$HOME/Library/Application Support/workspaceos-bridge"
INSTALLED_BRIDGE_PY="$INSTALL_DIR/bridge.py"
INSTALLED_APPLESCRIPT="$INSTALL_DIR/sync.applescript"

CONFIG_PATH="$HOME/.workspaceos-bridge.json"
PLIST_LABEL="com.workspaceos.outlookbridge"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_PATH="$HOME/Library/Logs/workspaceos-bridge.log"
INTERVAL_SEC=21600  # 6 hours

# Resolve an absolute python3 path up-front. Baking the resolved path
# into the plist makes failures obvious (`file not found`) instead of
# silent misbehaviour if $PATH differs under launchd.
PYTHON3="$(command -v python3 || true)"
if [[ -z "$PYTHON3" ]]; then
  echo "ERR: python3 not found on PATH" >&2
  exit 1
fi

echo "=============================================="
echo " WorkspaceOS Outlook Bridge — installer"
echo "=============================================="
echo "  python3: $PYTHON3"
echo "  install dir: $INSTALL_DIR"
echo

# ── Prompt for backend + creds ────────────────────────────────────────────

default_base="http://localhost:8989/api/v1"
read -r -p "API base URL [$default_base]: " API_BASE
API_BASE="${API_BASE:-$default_base}"

default_key="dev-secret-key"
read -r -p "API key [$default_key]: " API_KEY
API_KEY="${API_KEY:-$default_key}"

read -r -p "Backend email: " EMAIL
# Silence the password prompt
read -r -s -p "Backend password: " PASSWORD
echo

# ── Login to obtain JWT ───────────────────────────────────────────────────

echo
echo "→ Logging in to $API_BASE …"
LOGIN_JSON="$(
  "$PYTHON3" - <<PY
import json, sys, urllib.request, urllib.error
payload = json.dumps({"email": "$EMAIL", "password": "$PASSWORD"}).encode()
req = urllib.request.Request(
    "$API_BASE/auth/login",
    data=payload, method="POST",
    headers={"Content-Type": "application/json", "X-API-Key": "$API_KEY"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        sys.stdout.write(r.read().decode())
except urllib.error.HTTPError as e:
    sys.stderr.write(f"login failed: HTTP {e.code}: {e.read().decode()[:300]}\n")
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f"login failed: {e}\n")
    sys.exit(1)
PY
)" || { echo "  login failed (see error above)"; exit 1; }

ACCESS_TOKEN="$(
  "$PYTHON3" -c 'import sys,json; print(json.loads(sys.stdin.read()).get("access_token",""))' <<<"$LOGIN_JSON"
)"
REFRESH_TOKEN="$(
  "$PYTHON3" -c 'import sys,json; print(json.loads(sys.stdin.read()).get("refresh_token",""))' <<<"$LOGIN_JSON"
)"

if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "ERR: /auth/login did not return an access_token" >&2
  exit 1
fi
echo "  ok"

# ── Copy bridge files into a TCC-friendly location ───────────────────────

echo "→ Installing bridge into $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp "$SRC_BRIDGE_PY" "$INSTALLED_BRIDGE_PY"
cp "$SRC_APPLESCRIPT" "$INSTALLED_APPLESCRIPT"
chmod 755 "$INSTALLED_BRIDGE_PY"
chmod 644 "$INSTALLED_APPLESCRIPT"

# ── Write config (0600) ───────────────────────────────────────────────────

echo "→ Writing $CONFIG_PATH"
umask 077
cat > "$CONFIG_PATH" <<EOF
{
  "api_base": "$API_BASE",
  "api_key": "$API_KEY",
  "access_token": "$ACCESS_TOKEN",
  "refresh_token": "$REFRESH_TOKEN"
}
EOF
chmod 600 "$CONFIG_PATH"

# ── Write launchd plist ───────────────────────────────────────────────────

echo "→ Writing launchd plist at $PLIST_PATH"
mkdir -p "$(dirname "$PLIST_PATH")"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$PLIST_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON3</string>
    <string>$INSTALLED_BRIDGE_PY</string>
  </array>
  <key>StartInterval</key>
  <integer>$INTERVAL_SEC</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_PATH</string>
  <key>StandardErrorPath</key>
  <string>$LOG_PATH</string>
</dict>
</plist>
EOF

# ── Load into launchd ─────────────────────────────────────────────────────

echo "→ Loading job into launchd"
# bootout first to make re-installs idempotent; ignore failure if not loaded
launchctl bootout "gui/$UID/$PLIST_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST_PATH"

echo
echo "Installed. The bridge will run immediately and then every $((INTERVAL_SEC / 3600))h."
echo "Logs:   tail -f $LOG_PATH"
echo "Uninstall:  ./uninstall.sh"
echo
echo "Note: to update the bridge after editing files in the repo, just"
echo "re-run install.sh — it copies the fresh versions into place."
