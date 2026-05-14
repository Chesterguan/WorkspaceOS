"""zotero_sync ingest_source — read-only mirror of a Zotero library.

Pulls library items from Zotero's REST API and creates one
`paper_reference` knowledge node per item. Intentional scope cuts:

  - Read-only. No write-back to Zotero — that's their app's job.
  - Top-level items only (no children: notes, attachments, snapshots).
    The user already has a citation manager; we just want the
    paper-shaped breadcrumbs available to the rest of WorkspaceOS
    (research roundtable retrieval, paper pipeline citations,
    worklog mentions).
  - No tag mirroring yet — Zotero tags don't map cleanly to our
    typed taxonomy. v2: add a `tag: research-roundtable` filter.

Config:
    api_key:       Zotero API key (zotero.org/settings/keys)
    library_id:    user id (numeric) or group id
    library_type:  "user" or "group"   (default "user")
    items_limit:   max items per tick  (default 100, ceiling 100)

Missing creds = graceful no-op + warn-level event.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.capabilities.base import IngestContext, IngestSource

logger = logging.getLogger(__name__)


class ZoteroSync(IngestSource):
    """Read-only mirror of a Zotero library into the knowledge graph."""

    label = "zotero-sync"
    default_poll_interval_seconds = 6 * 60 * 60   # 6h — citations don't change fast

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        api_key = config.get("api_key") or ""
        library_id = str(config.get("library_id") or "").strip()
        library_type = (config.get("library_type") or "user").strip().lower()
        if library_type not in ("user", "group"):
            ctx.log("warn", f"zotero-sync: invalid library_type {library_type!r}")
            return 0
        if not api_key or not library_id:
            ctx.log("warn", "Zotero sync paused — set API key and library ID in Settings to enable.")
            return 0
        items_limit = min(int(config.get("items_limit") or 100), 100)

        url = (
            f"https://api.zotero.org/{'users' if library_type == 'user' else 'groups'}"
            f"/{library_id}/items/top"
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "Zotero-API-Key": api_key,
                        "Zotero-API-Version": "3",
                        "Accept": "application/json",
                    },
                    params={"limit": items_limit, "format": "json"},
                )
            if resp.status_code == 403:
                ctx.log("error", "zotero-sync: 403 — check api_key + library access")
                return 0
            if resp.status_code != 200:
                ctx.log("warn", f"zotero-sync: {resp.status_code} — {resp.text[:120]}")
                return 0
            items = resp.json() or []
        except httpx.HTTPError as exc:
            ctx.log("error", f"zotero-sync: network error — {exc}")
            return 0

        ingested = 0
        for item in items:
            try:
                key = item.get("key")
                data = item.get("data") or {}
                if not key or data.get("itemType") in ("note", "attachment"):
                    continue
                title = data.get("title") or "Untitled reference"
                first_author = _first_author(data.get("creators") or [])
                year = _extract_year(data.get("date"))
                doi = data.get("DOI") or ""
                url_field = data.get("url") or ""
                publication = data.get("publicationTitle") or data.get("journalAbbreviation") or ""

                content_lines = [
                    f"Author: {first_author}" if first_author else "",
                    f"Year: {year}" if year else "",
                    f"Venue: {publication}" if publication else "",
                    f"DOI: {doi}" if doi else "",
                    f"URL: {url_field}" if url_field else "",
                ]
                content = "\n".join(line for line in content_lines if line)

                inserted = await ctx.upsert_node(
                    node_type="paper_reference",
                    title=title[:160],
                    content=content,
                    external_id=f"zotero:{key}",
                    metadata={
                        "zotero_key": key,
                        "first_author": first_author,
                        "year": year,
                        "doi": doi,
                        "url": url_field,
                        "publication": publication,
                        "item_type": data.get("itemType"),
                    },
                )
                if inserted:
                    ingested += 1
            except Exception as exc:
                logger.warning("zotero-sync: skip item %s — %s",
                               item.get("key", "?"), exc)
                continue

        if ingested:
            ctx.log("success", f"zotero-sync: pulled {ingested} new references")
        else:
            logger.debug("zotero-sync: no new items this tick")
        return ingested


def _first_author(creators: List[Dict[str, Any]]) -> Optional[str]:
    for c in creators:
        if c.get("creatorType") in ("author", "editor", "contributor"):
            return (c.get("name")
                    or " ".join(filter(None, [c.get("firstName"), c.get("lastName")]))
                    or None)
    return None


def _extract_year(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    # Zotero dates are free-form ("2023", "March 2023", "2023-04-12"); grab 4 digits.
    import re
    m = re.search(r"\b(19|20)\d{2}\b", raw)
    return int(m.group(0)) if m else None
