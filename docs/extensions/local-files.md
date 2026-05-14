# Setting up the local-files extension

Watches a directory on your host machine and emits one
`file_ingested` knowledge node per new file. Polls every 30 seconds.
Zero external service required — runs entirely offline.

## 1. Pick a directory to watch

Anything on your machine. Common choices:

- A `notes/` folder where you keep markdown daily journals.
- A build output folder for a project.
- A synced cloud drive folder (`~/Dropbox/Lab Notes/`, `~/Documents/`,
  `~/iCloud Drive/…`). The local-files watcher picks up sync changes
  the same way it picks up new files.

## 2. Set `WORKSPACE_HOST_PATH` in `.env`

```bash
# In WorkspaceOS/.env
WORKSPACE_HOST_PATH=/Users/you/notes
```

This is bind-mounted as `/projects/` (read-only) inside the backend
container. The watcher walks `/projects/` recursively.

## 3. Restart the backend

```bash
docker compose down
docker compose up -d
```

(`restart` doesn't reload env_file / volume mounts. `down` + `up`
does.)

## 4. Verify

Bench TUI log within ~30 seconds:

```
HH:MM  [info]  capability scheduled: local-files-watcher:local_files every 30s
HH:MM  [info]  local-files: ingested notes/today.md
```

Drop a new file into your watched directory:

```bash
echo "Watcher test." > ~/notes/test.md
```

Within 30 seconds you'll see a new `local-files: ingested test.md`
event + a `file_ingested` node appear in the Knowledge surface.

## Tuning

In `config/extensions/local-files-watcher/manifest.yaml`:

```yaml
capabilities:
  - kind: ingest_source
    name: local_files
    config:
      watch_path: /projects        # don't change — bind-mount target
      poll_interval_seconds: 30    # tick cadence
      max_files_per_tick: 100      # cap per tick to avoid floods
      max_size_mb: 1.0             # skip large binaries
```

## Skipped by default

- Dot-prefixed directories (`.git`, `.next`, `.venv`, etc.).
- `node_modules`, `__pycache__`, `dist`, `build`, `.idea`, `.vscode`.
- `.pyc` / `.pyo` / `.DS_Store` / `.log` files.
- Anything dot-prefixed at the file level.
- Anything larger than `max_size_mb`.

These guards keep the runner cheap on fresh repos with `git` history
or `node_modules`.

## Cost

Free, local. No network, no API.
