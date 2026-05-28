"""One-off: re-embed every KnowledgeNode using the local AI client.

Run after L-1 fix landed. Required because mixing local + cloud
embeddings in the same pgvector column makes cosine similarity
meaningless.

Usage (inside the backend container):
    PYTHONPATH=/app python scripts/reembed_knowledge_nodes.py [--batch-size N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeNode
from app.services.ai_client import get_local_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reembed")


async def _process_batch(db: AsyncSession, nodes: List[KnowledgeNode], dry_run: bool) -> int:
    ai = get_local_client()
    updated = 0
    for node in nodes:
        embed_text = f"{node.title}\n\n{node.content or ''}"[:8000]
        try:
            vec = await ai.embed(embed_text)
        except Exception:
            log.exception("embed failed for node %s; skipping", node.id)
            continue
        if not dry_run:
            node.embedding = vec
        updated += 1
    if not dry_run:
        await db.commit()
    return updated


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(KnowledgeNode).where(KnowledgeNode.archived == False))
        all_nodes = list(result.scalars().all())
        log.info("found %d nodes to re-embed", len(all_nodes))

        for i in range(0, len(all_nodes), args.batch_size):
            batch = all_nodes[i:i + args.batch_size]
            updated = await _process_batch(db, batch, args.dry_run)
            total += updated
            log.info("batch %d-%d: %d updated", i, i + len(batch), updated)

    log.info("done. updated %d nodes (dry_run=%s)", total, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
