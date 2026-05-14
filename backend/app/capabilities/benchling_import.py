"""benchling_import ingest_source — read-only sync of notebook entries.

Pulls recently-modified Benchling notebook entries into the knowledge
graph as `benchling_entry` nodes. Intentionally narrow scope:

  - Notebook entries only (not custom entities, sequences, or schemas).
    Those are valuable but they're the kind of data that needs its own
    surface, not a KG-node smush.
  - Read-only. No write-back. The user's source of truth stays in
    Benchling.
  - Title + display_id + author + last_modified date go into the node.
    Body content stays in Benchling (we link, not mirror).

Config (in the extension's manifest.yaml):
    api_key:  Benchling API token (Settings → API Keys in Benchling)
    tenant:   <subdomain>.benchling.com  (no scheme, no path)
    days_back: 14                          (default 14)
    page_size: 50                          (default 50, max 100)

Missing creds = graceful no-op + warn-level event so the bench TUI
log surfaces the misconfiguration.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx

from app.capabilities.base import IngestContext, IngestSource

logger = logging.getLogger(__name__)


class BenchlingImport(IngestSource):
    """Daily-ish pull of notebook entries from a Benchling tenant."""

    label = "benchling-import"
    default_poll_interval_seconds = 6 * 60 * 60   # 6h — Benchling data isn't real-time

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        api_key = config.get("api_key") or ""
        tenant = (config.get("tenant") or "").strip().rstrip("/")
        if not api_key or not tenant:
            ctx.log("warn", "Benchling import paused — set API key and tenant in Settings to enable.")
            return 0
        days_back = int(config.get("days_back") or 14)
        page_size = min(int(config.get("page_size") or 50), 100)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        url = f"https://{tenant}/api/v2/entries"
        ingested = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    url,
                    headers={"Accept": "application/json"},
                    auth=(api_key, ""),
                    params={
                        "modifiedAt": f">={cutoff}",
                        "pageSize": page_size,
                    },
                )
            if resp.status_code == 401:
                ctx.log("error", "benchling-import: 401 — check api_key")
                return 0
            if resp.status_code != 200:
                ctx.log("warn", f"benchling-import: {resp.status_code} — {resp.text[:120]}")
                return 0
            data = resp.json()
            entries = data.get("entries") or []
        except httpx.HTTPError as exc:
            ctx.log("error", f"benchling-import: network error — {exc}")
            return 0

        for entry in entries:
            try:
                entry_id = entry.get("id")
                if not entry_id:
                    continue
                title = entry.get("name") or entry.get("displayId") or "Untitled entry"
                display_id = entry.get("displayId")
                author = (entry.get("creator") or {}).get("name")
                modified = entry.get("modifiedAt") or ""
                web_url = entry.get("webURL") or f"https://{tenant}/notebook/{entry_id}"

                content_lines = [
                    f"Display ID: {display_id}" if display_id else "",
                    f"Author: {author}" if author else "",
                    f"Last modified: {modified}",
                    f"URL: {web_url}",
                ]
                content = "\n".join(line for line in content_lines if line)

                inserted = await ctx.upsert_node(
                    node_type="benchling_entry",
                    title=title[:160],
                    content=content,
                    external_id=f"benchling:{entry_id}",
                    metadata={
                        "benchling_id": entry_id,
                        "display_id": display_id,
                        "url": web_url,
                        "modified_at": modified,
                    },
                )
                if inserted:
                    ingested += 1
            except Exception as exc:
                logger.warning("benchling-import: skip entry %s — %s",
                               entry.get("id", "?"), exc)
                continue

        if ingested:
            ctx.log("success", f"benchling-import: pulled {ingested} new entries")
        else:
            logger.debug("benchling-import: no new entries this tick")
        return ingested
