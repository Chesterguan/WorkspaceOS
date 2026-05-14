# Setting up the macOS Mail extension

Runs a small AppleScript bridge on your Mac that reads Apple Mail
and Outlook for Mac, then POSTs items into the WorkspaceOS backend
every 6 hours. macOS only.

Unlike the other ingest sources, **this runs on your host machine,
not in the Docker container** — Mail.app isn't accessible from
inside Docker (macOS TCC restrictions). So the "extension" itself is
a manifest declaring the capability + an installer that sets up a
launchd job on your Mac.

## 1. Make sure WorkspaceOS is running

The bridge POSTs to `http://localhost:9000/api/v1/skills/local-ingest/items`.
Bring up the stack first:

```bash
docker compose up -d
```

## 2. Run the bridge installer

```bash
cd scripts/outlook_bridge
./install.sh
```

The installer prompts for:

1. **API base URL** (default `http://localhost:8989/api/v1` for the
   ProjectScribe main stack; for this WorkspaceOS deployment, use
   `http://localhost:9000/api/v1`).
2. **API key** (default `dev-secret-key`).
3. **Your WorkspaceOS email + password** (whatever you registered
   with). The installer obtains a JWT via `/auth/login` and stores it
   in `~/.workspaceos-bridge.json` at chmod 600.

Then it copies `bridge.py` + `sync.applescript` to
`~/Library/Application Support/workspaceos-bridge/` and installs a
launchd plist (`com.workspaceos.outlookbridge`) that fires the bridge
every 6 hours.

## 3. Verify

- Logs: `tail -f ~/Library/Logs/workspaceos-bridge.log`
- WorkspaceOS Activity: the items appear in the project's Activity
  Feed tagged `ingest.mac_outlook` (or `ingest.mac_mail` for Apple
  Mail items).
- Low-confidence classifications land in an auto-created **Inbox**
  project.

## 4. macOS permissions on first run

The first launchd-triggered execution may show a TCC prompt asking
to grant Mail / Outlook automation access to `python3`. Click
**Allow**. After that, the bridge runs silently every 6 hours.

If you missed the prompt: **System Settings → Privacy & Security →
Automation** → ensure your python3 has access to Mail and Outlook.

## Tuning

Bridge constants live at the top of `scripts/outlook_bridge/sync.applescript`:

```applescript
set mailDays to 3                  -- how far back to look
set mailPerAccountMax to 25         -- per-account hard cap
```

Edit + re-run `./install.sh` to redeploy.

## Uninstall

```bash
cd scripts/outlook_bridge
./uninstall.sh
```

Removes the launchd job and the `~/Library/Application Support/workspaceos-bridge/`
copy. Leaves `~/.workspaceos-bridge.json` so a later reinstall doesn't
need your password.

## Why a host-side bridge (and not in-container)

Mail.app and Outlook for Mac are only accessible via AppleScript on
the host. Docker for Mac runs in a VM that can't reach the host's
TCC-protected apps. Two reasonable approaches:

1. **Microsoft Graph API for Outlook** — requires Microsoft Graph
   app registration with admin consent, which most corporate tenants
   block.
2. **Host-side AppleScript bridge** — what this extension does. No
   admin consent, no cloud roundtrip, works against any Apple
   ID / Microsoft account already signed into the user's local
   Mail.app or Outlook for Mac.

The bridge approach was chosen specifically to work in corporate
environments where #1 is blocked.

## Cost

Free.
