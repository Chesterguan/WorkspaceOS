"""
Memory service: add entries with embeddings, semantic search, and recent retrieval.
"""
import logging
import uuid
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.services.ai_client import get_local_client

logger = logging.getLogger(__name__)


async def add_entry(
    project_id: uuid.UUID,
    entry_type: str,
    content: str,
    source_ref: Optional[str],
    db: AsyncSession,
) -> MemoryEntry:
    """Create a memory entry and attempt to compute + store its embedding vector.

    If embedding fails (e.g. no API key configured, model unavailable), the entry
    is still persisted with embedding=None. It remains useful for text-based
    retrieval even without vector search capability.
    """
    embedding: Optional[List[float]] = None
    try:
        ai = get_local_client()
        embedding = await ai.embed(content)
    except Exception:
        logger.exception(
            "Failed to compute embedding for memory entry (type=%s, project=%s); "
            "storing with embedding=None",
            entry_type,
            project_id,
        )

    entry = MemoryEntry(
        project_id=project_id,
        entry_type=entry_type,
        content=content,
        source_ref=source_ref,
        embedding=embedding,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def search_memory(
    project_id: uuid.UUID,
    query: str,
    limit: int,
    db: AsyncSession,
) -> List[MemoryEntry]:
    """
    Return the most semantically similar memory entries for a query using
    pgvector cosine distance (<=>).  Entries without embeddings are excluded.
    """
    ai = get_local_client()
    query_embedding = await ai.embed(query)

    # Use a raw SQL expression for the pgvector operator since SQLAlchemy's
    # ORM doesn't natively know the <=> operator.
    result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.embedding.isnot(None),
        )
        .order_by(
            MemoryEntry.embedding.op("<=>")(query_embedding)
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_recent_entries(
    project_id: uuid.UUID,
    limit: int,
    db: AsyncSession,
) -> List[MemoryEntry]:
    """Return the most recently created memory entries for a project."""
    result = await db.execute(
        select(MemoryEntry)
        .where(MemoryEntry.project_id == project_id)
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
