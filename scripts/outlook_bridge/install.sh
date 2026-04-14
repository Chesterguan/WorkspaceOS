#!/usr/bin/env bash
# ProjectScribe Outlook Bridge — installer
#
# Prompts for backend URL + login, obtains a JWT via /auth/login, writes
# a 0600 config file at ~/.projectscribe-bridge.json, generates a launchd
# plist that fires bridge.py every 30 minutes, loads it.
#
# Safe to re-run — overwrites the config + plist in place.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_PY="$SCRIPT_DIR/bridge.py"

if [[ ! -f "$BRIDGE_PY" ]]; then
  echo "ERR: bridge.py not found next to this installer at $BRIDGE_PY" >&2
  exit 1
fi

CONFIG_PATH="$HOME/.projectscribe-bridge.json"
PLIST_LABEL="com.projectscribe.outlookbridge"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_PATH="$HOME/Library/Logs/projectscribe-bridge.log"
INTERVAL_SEC=1800  # 30 min

echo "=============================================="
echo " ProjectScribe Outlook Bridge — installer"
echo "=============================================="
echo

# ── Prompt for backend + creds ────────────────────────────────────────────

default_base="http://localhost:8989/api/v1"
read -r -p "API base URL [$default_base]: " API_BASE
API_BASE="${API_BASE:-$default_base}"

default_key="dev-secret-key"
read -r -p "API key [$default_key]: " API_KEY
API_KEY="${API_KEY:-$default_key}"

read -r -p "ProjectScribe email: " EMAIL
# Silence the password prompt
read -r -s -p "ProjectScribe password: " PASSWORD
echo

# ── Login to obtain JWT ───────────────────────────────────────────────────

echo
echo "→ Logging in to $API_BASE …"
# Use /usr/bin/python3 (ships with macOS) for the HTTP call rather than
# curl, so we have the same stdlib-only dependency footprint as bridge.py.
LOGIN_JSON="$(
  /usr/bin/python3 - <<PY
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
  /usr/bin/python3 -c 'import sys,json; print(json.loads(sys.stdin.read()).get("access_token",""))' <<<"$LOGIN_JSON"
)"
REFRESH_TOKEN="$(
  /usr/bin/python3 -c 'import sys,json; print(json.loads(sys.stdin.read()).get("refresh_token",""))' <<<"$LOGIN_JSON"
)"

if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "ERR: /auth/login did not return an access_token" >&2
  exit 1
fi
echo "  ok"

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
    <string>/usr/bin/python3</string>
    <string>$BRIDGE_PY</string>
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
echo "Installed. The bridge will run immediately and then every $((INTERVAL_SEC / 60)) minutes."
echo "Logs:   tail -f $LOG_PATH"
echo "Uninstall:  ./uninstall.sh"
