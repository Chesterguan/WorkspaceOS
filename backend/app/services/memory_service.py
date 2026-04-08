"""
Memory service: hybrid RAG pipeline with pgvector + BM25 + RRF + FlashRank reranking.

Pipeline:
  Query → [BM25 full-text search] ──┐
        → [pgvector cosine search] ─┼→ RRF Fusion → FlashRank Rerank → Top-K
                                     │
        Cross-project flag? ─────────┘

Write path:
  New entry → Ollama context description → Store: original + context + embedding + tsvector
"""
import asyncio
import logging
import uuid
from typing import Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.services.ai_client import get_local_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reranker (lazy-loaded singleton)
# ---------------------------------------------------------------------------
_reranker = None  # None = not tried, False = tried and failed


def _get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from flashrank import Ranker
            _reranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2")
            logger.info("FlashRank reranker loaded")
        except Exception:
            logger.warning("FlashRank reranker unavailable", exc_info=True)
            _reranker = False  # sentinel to stop retrying
    return _reranker if _reranker is not False else None


# ---------------------------------------------------------------------------
# Contextual retrieval: generate context on write
# ---------------------------------------------------------------------------
async def _generate_context_description(content: str, entry_type: str) -> str:
    """Use local AI to generate a context description for the entry.

    Prepended to the content before embedding for better semantic matching.
    """
    ai = get_local_client()
    try:
        ctx = await ai.complete(
            "Generate a 1-2 sentence context description for this text that explains "
            "what it is, why it matters, and what concepts it relates to. Be specific. "
            "Output ONLY the description, no preamble.",
            f"[{entry_type}] {content[:1000]}",
        )
        return ctx.strip()
    except Exception:
        logger.debug("Context generation failed; storing without context")
        return ""


# ---------------------------------------------------------------------------
# Write: add entry with contextual pre-processing
# ---------------------------------------------------------------------------
async def add_entry(
    project_id: uuid.UUID,
    entry_type: str,
    content: str,
    source_ref: Optional[str],
    db: AsyncSession,
) -> MemoryEntry:
    """Create a memory entry with contextual embedding and full-text indexing.

    Pipeline: generate context description → embed (content + context) → store.
    The tsvector column is auto-populated by a DB trigger on insert.
    """
    embedding: Optional[List[float]] = None
    context_description: str = ""

    try:
        ai = get_local_client()
        # Generate context description for better semantic matching
        context_description = await _generate_context_description(content, entry_type)
        # Embed the content WITH context for richer semantic signal
        embed_text = f"{context_description}\n\n{content}" if context_description else content
        embedding = await ai.embed(embed_text)
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
        context_description=context_description or None,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Search: vector (cosine similarity via pgvector)
# ---------------------------------------------------------------------------
async def search_memory_vector(
    project_id: uuid.UUID,
    query: str,
    limit: int,
    db: AsyncSession,
    cross_project: bool = False,
) -> List[MemoryEntry]:
    """Semantic search using pgvector cosine distance (<=>)."""
    ai = get_local_client()
    query_embedding = await ai.embed(query)

    stmt = (
        select(MemoryEntry)
        .where(MemoryEntry.embedding.isnot(None))
        .order_by(MemoryEntry.embedding.op("<=>")(query_embedding))
        .limit(limit)
    )
    if not cross_project:
        stmt = stmt.where(MemoryEntry.project_id == project_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Search: BM25 (full-text via tsvector)
# ---------------------------------------------------------------------------
async def search_memory_bm25(
    project_id: uuid.UUID,
    query: str,
    limit: int,
    db: AsyncSession,
    cross_project: bool = False,
) -> List[MemoryEntry]:
    """Full-text BM25 search using PostgreSQL tsvector."""
    tsquery = func.plainto_tsquery("english", query)

    stmt = (
        select(MemoryEntry)
        .where(MemoryEntry.search_vector.op("@@")(tsquery))
        .order_by(func.ts_rank(MemoryEntry.search_vector, tsquery).desc())
        .limit(limit)
    )
    if not cross_project:
        stmt = stmt.where(MemoryEntry.project_id == project_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Fusion: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------
def reciprocal_rank_fusion(
    ranked_lists: List[List[MemoryEntry]],
    k: int = 60,
) -> List[MemoryEntry]:
    """Fuse multiple ranked result lists using RRF. Returns deduplicated, re-ranked list."""
    scores: Dict[uuid.UUID, float] = {}
    entry_map: Dict[uuid.UUID, MemoryEntry] = {}

    for ranked_list in ranked_lists:
        for rank, entry in enumerate(ranked_list):
            scores[entry.id] = scores.get(entry.id, 0) + 1.0 / (rank + k)
            entry_map[entry.id] = entry

    sorted_ids = sorted(scores.keys(), key=lambda eid: scores[eid], reverse=True)
    return [entry_map[eid] for eid in sorted_ids]


# ---------------------------------------------------------------------------
# Rerank: FlashRank cross-encoder
# ---------------------------------------------------------------------------
async def rerank_results(
    query: str,
    entries: List[MemoryEntry],
    top_k: int = 5,
) -> List[MemoryEntry]:
    """Rerank memory entries using FlashRank cross-encoder."""
    if not entries:
        return entries

    reranker = _get_reranker()
    if reranker is None:
        return entries[:top_k]

    from flashrank import RerankRequest

    passages = [{"id": str(e.id), "text": e.content} for e in entries]
    request = RerankRequest(query=query, passages=passages)

    loop = asyncio.get_running_loop()
    reranked = await loop.run_in_executor(None, reranker.rerank, request)

    entry_map = {str(e.id): e for e in entries}
    result = []
    for r in reranked[:top_k]:
        # FlashRank returns dicts in some versions, objects in others
        rid = r["id"] if isinstance(r, dict) else getattr(r, "id", None)
        if rid and rid in entry_map:
            result.append(entry_map[rid])
    return result


# ---------------------------------------------------------------------------
# Main search: hybrid (vector + BM25 + RRF + rerank)
# ---------------------------------------------------------------------------
async def search_memory(
    project_id: uuid.UUID,
    query: str,
    limit: int,
    db: AsyncSession,
    cross_project: bool = False,
    rerank: bool = True,
) -> List[MemoryEntry]:
    """Hybrid search: pgvector cosine + BM25 full-text, fused with RRF, reranked.

    Pipeline: dual retrieval → RRF fusion → FlashRank reranking → top-K.
    Falls back gracefully if BM25 or reranking unavailable.
    """
    fetch_limit = limit * 2

    # Run both searches
    vector_results = await search_memory_vector(
        project_id, query, fetch_limit, db, cross_project
    )
    bm25_results = await search_memory_bm25(
        project_id, query, fetch_limit, db, cross_project
    )

    # Fuse results
    if vector_results and bm25_results:
        fused = reciprocal_rank_fusion([vector_results, bm25_results])
    elif vector_results:
        fused = vector_results
    else:
        fused = bm25_results

    # Rerank if we have more candidates than needed
    if rerank and len(fused) > limit:
        try:
            return await rerank_results(query, fused[:limit * 3], top_k=limit)
        except Exception:
            logger.debug("Reranking failed; returning RRF-fused results")

    return fused[:limit]


# ---------------------------------------------------------------------------
# Recent entries (unchanged)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Backfill: generate embeddings for entries missing them
# ---------------------------------------------------------------------------
async def backfill_embeddings(
    db: AsyncSession,
    project_id: Optional[uuid.UUID] = None,
    batch_size: int = 50,
) -> int:
    """Generate embeddings for memory entries that have embedding=None.

    Returns the number of entries updated.
    """
    # pgvector Vector column: SQLAlchemy `== None` doesn't generate correct SQL.
    # Use raw SQL to get IDs, then load as ORM objects.
    from sqlalchemy import text as sa_text
    # Use connection directly to bypass ORM session caching
    conn = await db.connection()
    id_rows = await conn.execute(sa_text(
        f"SELECT id FROM memory_entries WHERE embedding IS NULL LIMIT {int(batch_size)}"
    ))
    null_ids = [row[0] for row in id_rows.fetchall()]
    logger.info("backfill_embeddings: found %d entries with NULL embedding", len(null_ids))
    if not null_ids:
        return 0

    result = await db.execute(
        select(MemoryEntry).where(MemoryEntry.id.in_(null_ids))
    )
    entries = list(result.scalars().all())

    if not entries:
        return 0

    ai = get_local_client()
    updated = 0
    for entry in entries:
        try:
            embed_text = entry.content[:8000]  # truncate for embedding model limit
            if entry.context_description:
                embed_text = f"{entry.context_description}\n\n{embed_text}"
            entry.embedding = await ai.embed(embed_text)
            updated += 1
        except Exception:
            logger.debug("Backfill embed failed for entry %s", entry.id)

    await db.flush()
    return updated


# ---------------------------------------------------------------------------
# Wiki: auto-maintained project summary page
# ---------------------------------------------------------------------------

_WIKI_SYSTEM = """You are maintaining a living wiki page for a software project. \
Given the project's recent activity, narrative, and accumulated knowledge, generate \
a comprehensive project summary in markdown.

Sections to include:
## Project Overview — what it does, why, target users
## Tech Stack — languages, frameworks, databases, APIs
## Architecture — key components, data flow
## Key Decisions — important design choices with rationale
## Current Status — what's being worked on now
## Milestones — major releases or turning points

Rules:
- Be factual — only include information supported by the context
- Be concise — each section should be 2-5 sentences
- Use specific details (library names, version numbers, commit patterns)
- If information for a section is unavailable, write "No data available yet"
- Output ONLY the markdown content, no preamble or explanation"""


async def upsert_wiki_summary(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> MemoryEntry:
    """Generate or update the project's wiki summary page."""
    from app.services.ai_client import get_cloud_client
    from app.services.narrative_service import build_context_block, get_or_create

    # 1. Gather context
    context_result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type != "wiki_summary",
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(30)
    )
    recent_entries = list(context_result.scalars().all())

    context_parts: List[str] = []

    try:
        narrative = await get_or_create(project_id, db)
        ctx = build_context_block(narrative)
        narrative_lines: List[str] = []
        if ctx.get("one_liner"):
            narrative_lines.append(f"One-liner: {ctx['one_liner']}")
        if ctx.get("target_audience"):
            narrative_lines.append(f"Target audience: {ctx['target_audience']}")
        if ctx.get("origin_story"):
            narrative_lines.append(f"Origin story: {ctx['origin_story']}")
        if narrative_lines:
            context_parts.append("## Narrative\n" + "\n".join(narrative_lines))
    except Exception:
        logger.debug("Wiki: could not load narrative for project %s", project_id)

    if recent_entries:
        entry_lines: List[str] = []
        for entry in recent_entries:
            preview = entry.content[:300].replace("\n", " ")
            entry_lines.append(f"- [{entry.entry_type}] {preview}")
        context_parts.append("## Recent Memory Entries\n" + "\n".join(entry_lines))

    if not context_parts:
        existing = await db.execute(
            select(MemoryEntry).where(
                MemoryEntry.project_id == project_id,
                MemoryEntry.entry_type == "wiki_summary",
            )
        )
        entry = existing.scalar_one_or_none()
        if entry:
            return entry
        return await add_entry(
            project_id=project_id,
            entry_type="wiki_summary",
            content="## Project Overview\nNo data available yet.",
            source_ref="auto_sync",
            db=db,
        )

    # 2. Call AI
    ai = get_cloud_client()
    user_prompt = (
        "## Project Context\n\n"
        + "\n\n".join(context_parts)
        + "\n\n---\nGenerate the wiki summary now."
    )

    try:
        wiki_content = await ai.complete(system=_WIKI_SYSTEM, user=user_prompt)
    except Exception:
        logger.exception("Wiki: AI generation failed for project %s", project_id)
        wiki_content = "## Project Overview\nWiki generation failed. Will retry on next sync."

    # 3. Upsert
    existing_result = await db.execute(
        select(MemoryEntry).where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type == "wiki_summary",
        )
    )
    existing_entry = existing_result.scalar_one_or_none()

    metadata = {
        "page_type": "project_summary",
        "auto_generated": True,
        "updated_by": "sync",
    }

    if existing_entry:
        existing_entry.content = wiki_content
        existing_entry.metadata_ = metadata
        try:
            ai_local = get_local_client()
            context_desc = await _generate_context_description(wiki_content, "wiki_summary")
            embed_text = f"{context_desc}\n\n{wiki_content}" if context_desc else wiki_content
            existing_entry.embedding = await ai_local.embed(embed_text)
            existing_entry.context_description = context_desc or None
        except Exception:
            logger.debug("Wiki: embedding update failed, keeping old embedding")
        await db.flush()
        await db.refresh(existing_entry)
        logger.info("Wiki: updated summary for project %s", project_id)
        return existing_entry
    else:
        entry = await add_entry(
            project_id=project_id,
            entry_type="wiki_summary",
            content=wiki_content,
            source_ref="auto_sync",
            db=db,
        )
        entry.metadata_ = metadata
        await db.flush()
        await db.refresh(entry)
        logger.info("Wiki: created summary for project %s", project_id)
        return entry
