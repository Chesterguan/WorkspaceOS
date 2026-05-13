# Outlook for Mac → WorkspaceOS bridge

A tiny host-side helper that queries **Outlook for Mac** via AppleScript
and POSTs recent calendar events + Inbox messages into the WorkspaceOS
backend's `/skills/local-ingest/items` endpoint.

Runs entirely locally — no Microsoft Graph, no Azure app registration,
no IT involvement. If you're already signed in to Outlook for Mac, the
bridge uses that session.

Teams chat is **not supported** (Teams for Mac has no meaningful
AppleScript surface). Teams *meetings* still show up because they're
on your Outlook calendar.

## Install

```bash
cd scripts/outlook_bridge
./install.sh
```

The installer prompts for:
- API base URL (default `http://localhost:8989/api/v1`)
- API key (default `dev-secret-key`)
- Your backend email + password

It logs in via `/auth/login`, writes `~/.workspaceos-bridge.json`
(chmod 600), and loads a launchd agent that runs `bridge.py` every
30 minutes.

## Check that it's working

```bash
# Force a manual run
/usr/bin/python3 scripts/outlook_bridge/bridge.py

# Watch the log
tail -f ~/Library/Logs/workspaceos-bridge.log
```

Each ingested item shows up in the project's **Activity Feed** as
`ingest.mac_outlook`. Low-confidence classifications land in the
auto-created **Inbox** project.

## Uninstall

```bash
./uninstall.sh
```

Removes the launchd agent. The config file at
`~/.workspaceos-bridge.json` is left in place for easy reinstalls.
Delete it by hand to start over cleanly.

## Files

| File                  | Role                                              |
| --------------------- | ------------------------------------------------- |
| `sync.applescript`    | Queries Outlook Mac, emits NDJSON to stdout.      |
| `bridge.py`           | Runs osascript, POSTs items, handles refresh.     |
| `install.sh`          | Interactive setup + launchd plist generation.    |
| `uninstall.sh`        | Unload + remove the launchd agent.                |
