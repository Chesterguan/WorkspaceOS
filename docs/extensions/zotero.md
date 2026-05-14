# Setting up the Zotero extension

Pulls top-level items from your Zotero library into the knowledge
graph as `paper_reference` nodes. Read-only — your library stays in
Zotero. Polls every 6 hours.

## 1. Get your Zotero API key

1. Sign in at [zotero.org](https://www.zotero.org/).
2. Visit [zotero.org/settings/keys](https://www.zotero.org/settings/keys).
3. **Create new private key**.
4. Permissions: **Allow library access** = on. Library: your personal
   library (or a group library, see step 2). **Allow notes access**
   not required.
5. Copy the key. Zotero shows it once.

## 2. Find your library ID

The numeric id that comes after `/users/` or `/groups/` in your
library URLs.

- **User library**: visit [zotero.org/settings/keys](https://www.zotero.org/settings/keys) — the page shows your user id at the top ("Your userID for use in API calls is: `XXXXXXX`").
- **Group library**: open the group in Zotero web → URL is `https://www.zotero.org/groups/<group_id>/<name>`. Use `<group_id>`.

## 3. Edit the extension manifest

Open `config/extensions/zotero/manifest.yaml`. Fill in the three
required fields:

```yaml
capabilities:
  - kind: ingest_source
    name: zotero_sync
    config:
      api_key: "P9abc123…"                # ← from step 1
      library_id: "1234567"               # ← from step 2 (numeric)
      library_type: "user"                # ← "user" or "group"
      items_limit: 100
      poll_interval_seconds: 21600        # 6 hours
```

## 4. Restart the backend

```bash
docker compose restart backend
```

## 5. Verify

Bench TUI log (right side of `/bench`) within ~30 seconds:

```
HH:MM  [info]  capability scheduled: zotero:zotero_sync every 21600s
HH:MM  [success]  zotero-sync: pulled N new references
```

Knowledge surface: filter by `paper_reference` node type. Your
library items appear as nodes with title, first author, year, DOI,
venue.

## Troubleshooting

- **`zotero-sync: 403 — check api_key + library access`** → API key
  doesn't have access to that library. Re-create with library access
  enabled.
- **`zotero-sync: invalid library_type`** → must be exactly `user` or
  `group`.
- **No references pulled** → `items_limit` defaults to 100. If your
  library is larger than that, only the most recent 100 ingest each
  tick. Increase `items_limit` (max 100 per Zotero API tick) or wait
  for subsequent ticks.

## What's NOT synced today

- Notes attached to items. Skipped (`itemType: note`).
- Attachments / PDFs. Skipped — we link to the Zotero item, not store
  the file.
- Tags. v0.2.3 candidate; tag → KG-edge mapping needs design.
- Collections / folder hierarchy. Flat ingest today.

## Cost

Free. Zotero's API is free for personal and group libraries.
