# Capability extension setup

Each capability extension lives under `config/extensions/<id>/`. Most
ingest sources require credentials (API keys, library IDs, etc.).
Until v0.2.3 lands the UI-based config editor, configuration is done
by editing the extension's `manifest.yaml` directly.

This guide indexes the per-extension setup instructions. Follow the
guide for whichever extensions you want to enable. **Default state:
all extensions ship with blank credentials** — they load fine but
the ingest runner skips with a warn-level event until you fill in
the config.

| Extension | Setup guide | What it does |
|---|---|---|
| `local-files-watcher` | [local-files.md](local-files.md) | Watch a host directory; new files become `file_ingested` KG nodes. |
| `macos-mail` | [macos-mail.md](macos-mail.md) | Host-side AppleScript bridge → Apple Mail + Outlook for Mac items into the bench. |
| `benchling` | [benchling.md](benchling.md) | Read-only sync of Benchling notebook entries as `benchling_entry` nodes. |
| `zotero` | [zotero.md](zotero.md) | Read-only sync of Zotero library items as `paper_reference` nodes. |

## How to verify an extension is working

1. **Boot logs** — `docker compose logs backend | grep "capability scheduled"` should list each enabled capability's scheduling line.
2. **Settings → Capabilities tab** — each capability shows a `runtime ready` or `declared` badge. Runtime-ready means the framework has a handler; declared means it's a schema-only reservation (e.g. `macos_mail`).
3. **Bench TUI log** (right side of `/bench`) — capabilities emit `success` / `warn` / `error` events. If you mis-typed a key, you'll see a warn here within a minute.
4. **Knowledge surface** — ingested items become nodes. Filter by node type to see the latest.

## Where settings live

Editing `manifest.yaml` is the v0.2.2 way. v0.2.3 (next milestone) adds
a **Settings → Configure** modal on the Capabilities tab so you can
edit values in the UI, with values encrypted in the DB and overriding
the manifest at runtime. Until then, after editing a manifest:

```bash
docker compose restart backend
```

Live changes during dev: `docker compose logs -f backend` to watch
the runner emit events as it picks up the new config.

## Don't have credentials yet?

For each external service, the guide includes the link to the API
key / token page. None of these require paid tiers — every shipped
ingest source works on the free / personal tier of its provider.

If you don't have an account: skip that extension. The framework boots
fine with zero ingest sources active. `local-files-watcher` works
entirely offline against a directory on your host machine — it's the
zero-friction option to see the ingest pipeline in action.
