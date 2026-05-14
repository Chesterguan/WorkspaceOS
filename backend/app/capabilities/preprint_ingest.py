"""preprint_ingest ingest_source — polls bioRxiv / medRxiv for new preprints.

Hits the official api.biorxiv.org REST API (not RSS — RSS is brittle) and
inserts each keyword-matching preprint as a `paper_reference` knowledge node,
the same type Zotero uses. Deduplication is on external_id so re-posting the
same DOI across ticks is a no-op.

Config:
    sources:               subset of ["biorxiv", "medrxiv"] (default ["biorxiv"])
    keywords:              case-insensitive substrings matched against
                           title + abstract + category. Empty list = no matches
                           (intentionally opt-in — don't flood on first run).
    days_back:             how many calendar days back to query per tick (default 7)
    max_per_tick:          cap across all sources (default 50)
    poll_interval_seconds: default 86400 (24 h — preprints don't arrive fast)

Missing / empty keywords = graceful no-op + info-level event.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.capabilities.base import IngestContext, IngestSource

logger = logging.getLogger(__name__)

_BIORXIV_BASE = "https://api.biorxiv.org/details/{source}/{from_date}/{to_date}/{cursor}"
_PAGE_SIZE = 100   # bioRxiv API fixed page size


class PreprintIngest(IngestSource):
    """Poll bioRxiv / medRxiv and insert keyword-matching preprints."""

    label = "preprint-ingest"
    default_poll_interval_seconds = 86400  # 24 h

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        sources: List[str] = list(config.get("sources") or ["biorxiv"])
        keywords: List[str] = [k.lower() for k in (config.get("keywords") or []) if k]
        days_back: int = max(1, int(config.get("days_back") or 7))
        max_per_tick: int = max(1, int(config.get("max_per_tick") or 50))

        if not keywords:
            ctx.log("info", "preprint-ingest: no keywords configured — skipping tick (add keywords in Settings to enable)")
            return 0

        valid_sources = {"biorxiv", "medrxiv"}
        sources = [s for s in sources if s in valid_sources]
        if not sources:
            ctx.log("warn", "preprint-ingest: no valid sources in config (expected biorxiv / medrxiv)")
            return 0

        to_date = date.today()
        from_date = to_date - timedelta(days=days_back)
        from_str = from_date.isoformat()
        to_str = to_date.isoformat()

        total_ingested = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for source in sources:
                if total_ingested >= max_per_tick:
                    break
                remaining = max_per_tick - total_ingested
                ingested = await _poll_source(
                    client=client,
                    source=source,
                    from_str=from_str,
                    to_str=to_str,
                    keywords=keywords,
                    max_items=remaining,
                    ctx=ctx,
                )
                total_ingested += ingested

        if total_ingested:
            ctx.log("success", f"preprint-ingest: pulled {total_ingested} new preprints")
        else:
            logger.debug("preprint-ingest: no new keyword-matching preprints this tick")
        return total_ingested


async def _poll_source(
    *,
    client: httpx.AsyncClient,
    source: str,
    from_str: str,
    to_str: str,
    keywords: List[str],
    max_items: int,
    ctx: IngestContext,
) -> int:
    """Paginate through one source (biorxiv or medrxiv), filter by keywords,
    upsert matching items. Returns count of newly inserted nodes."""
    ingested = 0
    cursor = 0

    while ingested < max_items:
        url = _BIORXIV_BASE.format(
            source=source,
            from_date=from_str,
            to_date=to_str,
            cursor=cursor,
        )
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            ctx.log("error", f"preprint-ingest/{source}: network error — {exc}")
            break

        if resp.status_code == 429:
            # Polite backoff on rate-limit before giving up for this tick.
            logger.warning("preprint-ingest/%s: 429 rate-limited — backing off 10 s", source)
            await asyncio.sleep(10)
            try:
                resp = await client.get(url, headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                ctx.log("error", f"preprint-ingest/{source}: network error after backoff — {exc}")
                break

        if resp.status_code != 200:
            ctx.log("warn", f"preprint-ingest/{source}: HTTP {resp.status_code} — {resp.text[:120]}")
            break

        try:
            payload = resp.json()
        except Exception as exc:
            ctx.log("error", f"preprint-ingest/{source}: bad JSON — {exc}")
            break

        collection: List[Dict[str, Any]] = payload.get("collection") or []
        if not collection:
            # No more pages.
            break

        for item in collection:
            if ingested >= max_items:
                break
            try:
                inserted = await _process_item(item=item, source=source, keywords=keywords, ctx=ctx)
                if inserted:
                    ingested += 1
            except Exception as exc:
                doi = item.get("doi", "?")
                logger.warning("preprint-ingest/%s: skip %s — %s", source, doi, exc)
                continue

        # bioRxiv returns up to 100 per page; if we got fewer we're done.
        if len(collection) < _PAGE_SIZE:
            break

        cursor += _PAGE_SIZE

    return ingested


async def _process_item(
    *,
    item: Dict[str, Any],
    source: str,
    keywords: List[str],
    ctx: IngestContext,
) -> bool:
    """Filter one API item against keywords and upsert if it matches.
    Returns True if a new node was inserted."""
    doi: str = (item.get("doi") or "").strip()
    title: str = (item.get("title") or "").strip()
    abstract: str = (item.get("abstract") or "").strip()
    category: str = (item.get("category") or "").strip()
    item_date: str = (item.get("date") or "").strip()
    version: str = str(item.get("version") or "1")
    authors_raw: str = (item.get("authors") or "").strip()

    if not doi or not title:
        return False

    # Client-side keyword filter: any keyword as substring of title + abstract + category.
    haystack = f"{title} {abstract} {category}".lower()
    if not any(kw in haystack for kw in keywords):
        return False

    first_author = _first_author(authors_raw)
    source_label = "bioRxiv" if source == "biorxiv" else "medRxiv"
    doi_url = f"https://doi.org/{doi}"

    content_parts = [
        f"Author: {first_author}" if first_author else "",
        f"Date: {item_date}" if item_date else "",
        f"Source: {source_label}",
        f"Category: {category}" if category else "",
        f"DOI: {doi}",
        f"URL: {doi_url}",
        "",
        f"Abstract: {abstract}" if abstract else "",
    ]
    content = "\n".join(line for line in content_parts if line is not None)

    external_id = f"preprint:{source}:{doi}"

    return await ctx.upsert_node(
        node_type="paper_reference",
        title=title[:160],
        content=content,
        external_id=external_id,
        metadata={
            "preprint_source": source,
            "doi": doi,
            "first_author": first_author,
            "date": item_date,
            "category": category,
            "version": version,
            "url": doi_url,
        },
    )


def _first_author(authors_raw: str) -> Optional[str]:
    """Split the semicolon-separated authors string and return the first."""
    if not authors_raw:
        return None
    parts = [p.strip() for p in authors_raw.split(";") if p.strip()]
    return parts[0] if parts else None
