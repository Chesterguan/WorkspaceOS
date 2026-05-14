# Setting up the Benchling extension

Pulls recent notebook entries from your Benchling tenant into the
knowledge graph as `benchling_entry` nodes. Read-only — your ELN
stays the source of truth. Polls every 6 hours.

## 1. Get your Benchling API key

1. Sign in to your Benchling tenant.
2. Click your avatar (bottom-left) → **Settings**.
3. **API keys** → **Create new API key**.
4. Give it a descriptive name (e.g. `WorkspaceOS sync`). Copy the
   key — Benchling only shows it once.

> **Required permissions:** read access to **Notebook Entries**. The
> default API key scope works.

## 2. Note your tenant subdomain

The part before `.benchling.com` in your URL. For example, if your
Benchling lives at `https://lab.benchling.com/notebook`, your tenant
is `lab.benchling.com`.

## 3. Edit the extension manifest

Open `config/extensions/benchling/manifest.yaml`. Fill in the two
required fields:

```yaml
capabilities:
  - kind: ingest_source
    name: benchling_import
    config:
      api_key: "sk_live_abc123…"          # ← paste the key from step 1
      tenant: "lab.benchling.com"         # ← your subdomain from step 2
      days_back: 14
      page_size: 50
      poll_interval_seconds: 21600        # 6 hours
```

## 4. Restart the backend

```bash
docker compose restart backend
```

## 5. Verify it's working

Within ~30 seconds, watch the bench TUI log (right side of
`http://localhost:4000/bench`) for:

```
HH:MM  [info]  capability scheduled: benchling:benchling_import every 21600s
HH:MM  [success]  benchling-import: pulled N new entries
```

The first tick fires immediately on startup. Subsequent ticks every
6 hours.

Open the **Knowledge** surface and filter by node type
`benchling_entry` — your notebook entries appear as nodes with the
title, author, modified date, and a link back to Benchling.

## Troubleshooting

- **`benchling-import: 401 — check api_key`** → key is wrong or
  revoked. Re-copy from the API keys page.
- **`benchling-import: missing api_key or tenant in config`** → you
  edited the wrong file or didn't restart the backend.
- **`benchling-import: network error`** → tenant subdomain is
  probably wrong. Verify it's just `<sub>.benchling.com` with no
  `https://` and no trailing slash.
- **No entries pulled** → check `days_back`. Default is 14 days. If
  nothing was modified recently, nothing is ingested.

## What's NOT synced today

- Custom entities (Strains, Plasmids, etc.). v0.2.3 candidate.
- Sequences. Probably never — Benchling's API isn't well-suited to
  bulk-pull sequence data, and we'd just be duplicating their UI.
- Body content of notebook entries. The node links back; click
  through to read.
- Tags. v0.2.3 candidate; needs tag → KG edge design.

## Cost

Free. Benchling's API is included in all paid tiers (Academic free
tier included).
