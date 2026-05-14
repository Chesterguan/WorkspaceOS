"""benchling_import ingest_source — read-only sync of Benchling data.

Pulls from Benchling into the knowledge graph as typed nodes:

  - Notebook entries  →  `benchling_entry` nodes  (default; daily lab log)
  - DNA sequences     →  `construct` nodes        (v0.2.6 — plasmid registry)
  - Custom entities   →  `strain` nodes           (v0.2.6 — opt-in via
                                                   `custom_entity_schemas`)

Intentional scope choices:

  - Read-only. No write-back. Benchling stays source of truth.
  - Body content stays in Benchling — we link with web URL + display_id,
    not mirror the full document.
  - The user picks which entity types to ingest in config; the default
    is `entries` only to preserve pre-v0.2.6 behavior on upgrade.
  - Custom entities are schema-driven in Benchling; the user must
    list the schema IDs (or names — substring match) they want pulled
    as `strain` nodes. Without that list we skip custom entities,
    because pulling every schema's entities would smush incompatible
    shapes into one node type.

Config (in the extension's manifest.yaml, overridable in Settings):
    api_key:        Benchling API token
    tenant:         <subdomain>.benchling.com  (no scheme, no path)
    entity_types:   list of:
                      - "entries"           (notebook entries → benchling_entry)
                      - "dna_sequences"     (plasmids → construct)
                      - "custom_entities"   (strains etc → strain)
                    default: ["entries"]
    custom_entity_schemas: list of schema name substrings to include
                           when entity_types contains "custom_entities".
                           Case-insensitive. Empty = include all (use
                           with care; expect mixed shapes).
    days_back:      14    (default 14)
    page_size:      50    (default 50, max 100)

Missing creds = graceful no-op + warn-level event so the bench TUI
log surfaces the misconfiguration.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.capabilities.base import IngestContext, IngestSource

logger = logging.getLogger(__name__)


# Default entity types when user doesn't override. Stays as just
# "entries" so upgrading from pre-v0.2.6 doesn't suddenly start
# pulling thousands of plasmid records.
_DEFAULT_ENTITY_TYPES = ["entries"]


class BenchlingImport(IngestSource):
    """Daily-ish pull of notebook entries + (optionally) constructs /
    strains from a Benchling tenant."""

    label = "benchling-import"
    default_poll_interval_seconds = 6 * 60 * 60  # 6h — Benchling data isn't real-time

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        api_key = config.get("api_key") or ""
        tenant = (config.get("tenant") or "").strip().rstrip("/")
        if not api_key or not tenant:
            ctx.log("warn", "Benchling import paused — set API key and tenant in Settings to enable.")
            return 0

        entity_types = config.get("entity_types") or _DEFAULT_ENTITY_TYPES
        if not isinstance(entity_types, list):
            entity_types = _DEFAULT_ENTITY_TYPES
        entity_types = [str(et).lower() for et in entity_types]

        days_back = int(config.get("days_back") or 14)
        page_size = min(int(config.get("page_size") or 50), 100)
        custom_entity_schemas = config.get("custom_entity_schemas") or []
        if not isinstance(custom_entity_schemas, list):
            custom_entity_schemas = []
        custom_entity_schemas = [str(s).lower() for s in custom_entity_schemas]

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

        total = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            if "entries" in entity_types:
                total += await self._ingest_entries(
                    client, ctx, tenant, api_key, cutoff, page_size,
                )
            if "dna_sequences" in entity_types:
                total += await self._ingest_dna_sequences(
                    client, ctx, tenant, api_key, cutoff, page_size,
                )
            if "custom_entities" in entity_types:
                total += await self._ingest_custom_entities(
                    client, ctx, tenant, api_key, cutoff, page_size,
                    schema_substrings=custom_entity_schemas,
                )

        if total:
            ctx.log("success", f"benchling-import: pulled {total} new items this tick")
        else:
            logger.debug("benchling-import: no new items this tick")
        return total

    # ── notebook entries → benchling_entry node ────────────────────────

    async def _ingest_entries(
        self,
        client: httpx.AsyncClient,
        ctx: IngestContext,
        tenant: str,
        api_key: str,
        cutoff: str,
        page_size: int,
    ) -> int:
        try:
            resp = await client.get(
                f"https://{tenant}/api/v2/entries",
                headers={"Accept": "application/json"},
                auth=(api_key, ""),
                params={"modifiedAt": f">={cutoff}", "pageSize": page_size},
            )
        except httpx.HTTPError as exc:
            ctx.log("error", f"benchling-import (entries): network error — {exc}")
            return 0
        if resp.status_code == 401:
            ctx.log("error", "benchling-import (entries): 401 — check api_key")
            return 0
        if resp.status_code != 200:
            ctx.log(
                "warn",
                f"benchling-import (entries): {resp.status_code} — {resp.text[:120]}",
            )
            return 0
        entries = (resp.json() or {}).get("entries") or []

        ingested = 0
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
                if await ctx.upsert_node(
                    node_type="benchling_entry",
                    title=title[:160],
                    content="\n".join(line for line in content_lines if line),
                    external_id=f"benchling:entry:{entry_id}",
                    metadata={
                        "benchling_id": entry_id,
                        "display_id": display_id,
                        "url": web_url,
                        "modified_at": modified,
                        "kind": "entry",
                    },
                ):
                    ingested += 1
            except Exception as exc:
                logger.warning(
                    "benchling-import (entries): skip %s — %s",
                    entry.get("id", "?"), exc,
                )
                continue
        if ingested:
            ctx.log("info", f"benchling-import: +{ingested} notebook entries")
        return ingested

    # ── DNA sequences → construct node ────────────────────────────────

    async def _ingest_dna_sequences(
        self,
        client: httpx.AsyncClient,
        ctx: IngestContext,
        tenant: str,
        api_key: str,
        cutoff: str,
        page_size: int,
    ) -> int:
        """DNA sequences are Benchling's plasmid/insert registry. Map
        each to a `construct` knowledge node — the bio taxonomy node
        type that's been declared but starved of data."""
        try:
            resp = await client.get(
                f"https://{tenant}/api/v2/dna-sequences",
                headers={"Accept": "application/json"},
                auth=(api_key, ""),
                params={"modifiedAt": f">={cutoff}", "pageSize": page_size},
            )
        except httpx.HTTPError as exc:
            ctx.log("error", f"benchling-import (dna): network error — {exc}")
            return 0
        if resp.status_code == 401:
            ctx.log("error", "benchling-import (dna): 401 — check api_key")
            return 0
        if resp.status_code != 200:
            ctx.log(
                "warn",
                f"benchling-import (dna): {resp.status_code} — {resp.text[:120]}",
            )
            return 0
        items = (resp.json() or {}).get("dnaSequences") or []

        ingested = 0
        for seq in items:
            try:
                seq_id = seq.get("id")
                if not seq_id:
                    continue
                name = seq.get("name") or seq.get("registryId") or "Unnamed sequence"
                display_id = seq.get("registryId") or seq.get("entityRegistryId")
                length = seq.get("length")
                circular = seq.get("isCircular")
                author = (seq.get("creator") or {}).get("name")
                modified = seq.get("modifiedAt") or ""
                schema = (seq.get("schema") or {}).get("name")
                folder_id = seq.get("folderId")
                web_url = seq.get("webURL") or f"https://{tenant}/{seq_id}/edit"

                content_lines = [
                    f"Registry ID: {display_id}" if display_id else "",
                    f"Length: {length} bp" if length else "",
                    f"Topology: {'circular' if circular else 'linear'}" if circular is not None else "",
                    f"Schema: {schema}" if schema else "",
                    f"Author: {author}" if author else "",
                    f"Last modified: {modified}",
                    f"URL: {web_url}",
                ]
                if await ctx.upsert_node(
                    node_type="construct",
                    title=name[:160],
                    content="\n".join(line for line in content_lines if line),
                    external_id=f"benchling:dna:{seq_id}",
                    metadata={
                        "benchling_id": seq_id,
                        "display_id": display_id,
                        "registry_id": display_id,
                        "length_bp": length,
                        "circular": circular,
                        "schema": schema,
                        "folder_id": folder_id,
                        "url": web_url,
                        "modified_at": modified,
                        "kind": "dna_sequence",
                    },
                ):
                    ingested += 1
            except Exception as exc:
                logger.warning(
                    "benchling-import (dna): skip %s — %s",
                    seq.get("id", "?"), exc,
                )
                continue
        if ingested:
            ctx.log("info", f"benchling-import: +{ingested} DNA constructs")
        return ingested

    # ── custom entities → strain node ─────────────────────────────────

    async def _ingest_custom_entities(
        self,
        client: httpx.AsyncClient,
        ctx: IngestContext,
        tenant: str,
        api_key: str,
        cutoff: str,
        page_size: int,
        *,
        schema_substrings: List[str],
    ) -> int:
        """Custom entities are schema-driven (Strain / Bacterium / Plant /
        whatever the lab has defined). We map them all to `strain`
        nodes when the schema name matches a configured substring.
        Without a substring filter we skip — Benchling Registry has too
        many incompatible shapes to one-size-fits-all."""
        if not schema_substrings:
            logger.debug(
                "benchling-import (custom): no custom_entity_schemas filter set; skipping"
            )
            return 0

        try:
            resp = await client.get(
                f"https://{tenant}/api/v2/custom-entities",
                headers={"Accept": "application/json"},
                auth=(api_key, ""),
                params={"modifiedAt": f">={cutoff}", "pageSize": page_size},
            )
        except httpx.HTTPError as exc:
            ctx.log("error", f"benchling-import (custom): network error — {exc}")
            return 0
        if resp.status_code == 401:
            ctx.log("error", "benchling-import (custom): 401 — check api_key")
            return 0
        if resp.status_code != 200:
            ctx.log(
                "warn",
                f"benchling-import (custom): {resp.status_code} — {resp.text[:120]}",
            )
            return 0
        items = (resp.json() or {}).get("customEntities") or []

        ingested = 0
        for ent in items:
            try:
                ent_id = ent.get("id")
                if not ent_id:
                    continue
                schema = ((ent.get("schema") or {}).get("name") or "").lower()
                if not any(sub in schema for sub in schema_substrings):
                    continue  # not a schema the user opted into
                name = ent.get("name") or ent.get("registryId") or "Unnamed entity"
                display_id = ent.get("registryId") or ent.get("entityRegistryId")
                author = (ent.get("creator") or {}).get("name")
                modified = ent.get("modifiedAt") or ""
                folder_id = ent.get("folderId")
                web_url = ent.get("webURL") or f"https://{tenant}/{ent_id}/edit"

                # Flatten fields → human-readable lines. Benchling
                # returns fields as {key: {value, type, ...}}; we
                # surface key + value text only.
                fields = ent.get("fields") or {}
                field_lines: List[str] = []
                for key, fdef in fields.items():
                    if not isinstance(fdef, dict):
                        continue
                    val = fdef.get("displayValue") or fdef.get("value")
                    if val is None or val == "":
                        continue
                    field_lines.append(f"{key}: {val}")

                content_lines = [
                    f"Registry ID: {display_id}" if display_id else "",
                    f"Schema: {schema}" if schema else "",
                    f"Author: {author}" if author else "",
                    f"Last modified: {modified}",
                    f"URL: {web_url}",
                ]
                if field_lines:
                    content_lines.append("")
                    content_lines.append("Fields:")
                    content_lines.extend(f"  {line}" for line in field_lines)

                if await ctx.upsert_node(
                    node_type="strain",
                    title=name[:160],
                    content="\n".join(line for line in content_lines if line),
                    external_id=f"benchling:custom:{ent_id}",
                    metadata={
                        "benchling_id": ent_id,
                        "display_id": display_id,
                        "registry_id": display_id,
                        "schema": schema,
                        "folder_id": folder_id,
                        "url": web_url,
                        "modified_at": modified,
                        "kind": "custom_entity",
                    },
                ):
                    ingested += 1
            except Exception as exc:
                logger.warning(
                    "benchling-import (custom): skip %s — %s",
                    ent.get("id", "?"), exc,
                )
                continue
        if ingested:
            ctx.log("info", f"benchling-import: +{ingested} strains / custom entities")
        return ingested
