"""Base contracts for capability plugins.

`IngestContext` is what a runner uses to talk back to the host —
emit events into the bench TUI log + insert knowledge nodes scoped
to the user. Runners do NOT touch the DB directly; they call
`ctx.upsert_node(...)` and the context handles session + dedup.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeNode
from app.services.event_stream import emit

logger = logging.getLogger(__name__)


class IngestContext:
    """Runner-facing API. One context per runner per scheduling tick."""

    def __init__(self, user_id: uuid.UUID, source: str):
        self.user_id = user_id
        # `source` shows up in the bench TUI log to identify which
        # capability produced the event.
        self.source = source

    def log(
        self,
        level: str,
        summary: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a line into the bench's TUI log. Best-effort; safe to
        call many times — the event ring buffer caps at 200."""
        emit(level, self.source, summary, meta=meta)

    async def upsert_node(
        self,
        *,
        node_type: str,
        title: str,
        content: str,
        external_id: str,
        project_id: Optional[uuid.UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Insert a knowledge node, deduplicating on (user_id, external_id).

        Returns True if a new node was inserted, False if a node with the
        same external_id already exists for this user. `external_id` lives
        in metadata['external_id'] — we don't add a column to keep the
        migration footprint zero. For light-traffic ingest sources this
        scan is cheap; high-throughput runners would index it.
        """
        metadata = dict(metadata or {})
        metadata["external_id"] = external_id
        metadata["capability_source"] = self.source

        async with AsyncSessionLocal() as db:
            try:
                existing = await db.execute(
                    select(KnowledgeNode).where(
                        KnowledgeNode.user_id == self.user_id,
                        KnowledgeNode.metadata_["external_id"].astext == external_id,
                    ).limit(1)
                )
                if existing.scalar_one_or_none() is not None:
                    return False

                # `created_by` is VARCHAR(40) — keep it short. The full
                # source label is preserved in metadata + source_refs for
                # provenance.
                node = KnowledgeNode(
                    user_id=self.user_id,
                    project_id=project_id,
                    node_type=node_type,
                    title=title[:160],
                    content=content,
                    source_refs=[{"kind": "capability", "source": self.source,
                                  "external_id": external_id}],
                    metadata_=metadata,
                    created_by="capability",
                )
                db.add(node)
                await db.commit()
                return True
            except Exception:
                await db.rollback()
                logger.exception("upsert_node failed for %s/%s", self.source, external_id)
                raise


class IngestSource:
    """Base class for `kind: ingest_source` capability plugins.

    Subclasses implement `run` and return the number of *new* items
    ingested this tick. The runner uses the return value for logging
    only — the source itself decides what "ingested" means.

    `config` is the kind-specific config block from the extension's
    manifest. Validation is up to the subclass; treat missing fields
    as "skip the tick" rather than raise.
    """

    #: human-readable label, surfaced in the bench TUI log
    label: str = "ingest"
    #: how often the runner should fire, in seconds. Subclasses can
    #: override; manifest config can also override per-instance.
    default_poll_interval_seconds: int = 60

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        raise NotImplementedError
