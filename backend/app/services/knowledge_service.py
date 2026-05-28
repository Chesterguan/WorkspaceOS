"""Knowledge query API. Reuses _hybrid_search.

See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md
"""
import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.services._hybrid_search import (
    reciprocal_rank_fusion_ids, rerank_passages,
)
from app.services.ai_client import get_cloud_client, get_local_client

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeHit:
    node: KnowledgeNode
    score: float


async def query_embedding(query: str) -> List[float]:
    """Embed a query for knowledge search.

    Embeddings are foundation ops — must stay local. See
    docs/privacy/known-leaks.md#l-1.
    """
    return await get_local_client().embed(query)


def _scope_clauses(
    user_id: uuid.UUID,
    project_id: Optional[uuid.UUID],
    node_types: Optional[List[str]],
    include_archived: bool,
):
    """Return a list of SQLAlchemy where-clause expressions to apply to a select on KnowledgeNode."""
    clauses = [KnowledgeNode.user_id == user_id]
    if project_id is not None:
        clauses.append(KnowledgeNode.project_id == project_id)
    if node_types:
        clauses.append(KnowledgeNode.node_type.in_(node_types))
    if not include_archived:
        clauses.append(KnowledgeNode.archived.is_(False))
    return clauses


async def _vector_candidates(
    db: AsyncSession,
    embedding: List[float],
    clauses: List,
    limit: int,
) -> List[uuid.UUID]:
    if not embedding:
        return []
    stmt = (
        select(KnowledgeNode.id)
        .where(*clauses, KnowledgeNode.embedding.isnot(None))
        .order_by(KnowledgeNode.embedding.op("<=>")(embedding))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [r[0] for r in rows]


async def _bm25_candidates(
    db: AsyncSession,
    query: str,
    clauses: List,
    limit: int,
) -> List[uuid.UUID]:
    tsquery = func.plainto_tsquery("english", query)
    stmt = (
        select(KnowledgeNode.id)
        .where(*clauses, KnowledgeNode.search_vector.op("@@")(tsquery))
        .order_by(func.ts_rank(KnowledgeNode.search_vector, tsquery).desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [r[0] for r in rows]


async def search_knowledge(
    user_id: uuid.UUID,
    query: str,
    db: AsyncSession,
    project_id: Optional[uuid.UUID] = None,
    node_types: Optional[List[str]] = None,
    limit: int = 10,
    include_archived: bool = False,
    rerank: bool = True,
) -> List[KnowledgeHit]:
    """Hybrid knowledge search: pgvector + BM25 + RRF + FlashRank rerank.

    User-scoped. Optional project filter. Defaults exclude archived nodes.
    Falls back to BM25-only if embedding fails (Gemini embed endpoint intermittent).
    """
    clauses = _scope_clauses(user_id, project_id, node_types, include_archived)
    fetch = limit * 2

    try:
        embedding = await query_embedding(query)
    except Exception:
        logger.exception("embed failed during knowledge search; using BM25 only")
        embedding = []

    vec_ids = await _vector_candidates(db, embedding, clauses, fetch)
    bm_ids = await _bm25_candidates(db, query, clauses, fetch)

    if vec_ids and bm_ids:
        fused = reciprocal_rank_fusion_ids([vec_ids, bm_ids])
    else:
        fused = list(vec_ids) or list(bm_ids)
    if not fused:
        return []

    nodes_by_id = {
        n.id: n for n in (await db.execute(
            select(KnowledgeNode).where(KnowledgeNode.id.in_(fused[:fetch]))
        )).scalars().all()
    }
    candidates: List[KnowledgeNode] = [nodes_by_id[nid] for nid in fused if nid in nodes_by_id]

    if rerank and len(candidates) > limit:
        passages = [{"id": str(c.id), "text": f"{c.title}\n{c.content}"} for c in candidates[:limit * 3]]
        new_order = await rerank_passages(query, passages, top_k=limit)
        ordered_map = {str(c.id): c for c in candidates}
        candidates = [ordered_map[rid] for rid in new_order if rid in ordered_map]

    return [KnowledgeHit(node=n, score=1.0 - i * 0.01) for i, n in enumerate(candidates[:limit])]


async def list_recent_nodes(
    user_id: uuid.UUID,
    db: AsyncSession,
    project_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    include_archived: bool = False,
) -> List[KnowledgeNode]:
    """Most recent nodes for the user, optionally filtered by project."""
    clauses = _scope_clauses(user_id, project_id, None, include_archived)
    stmt = (
        select(KnowledgeNode)
        .where(*clauses)
        .order_by(KnowledgeNode.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_node_with_neighbors(
    node_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    depth: int = 1,
) -> Tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
    """BFS out from `node_id` up to `depth` hops. Returns (nodes, edges) all user-scoped."""
    visited: set = {node_id}
    frontier: set = {node_id}
    all_edges: List[KnowledgeEdge] = []

    for _ in range(depth):
        if not frontier:
            break
        edges = (await db.execute(
            select(KnowledgeEdge).where(
                KnowledgeEdge.user_id == user_id,
                (KnowledgeEdge.source_node_id.in_(frontier))
                | (KnowledgeEdge.target_node_id.in_(frontier)),
            )
        )).scalars().all()
        all_edges.extend(edges)
        next_frontier: set = set()
        for e in edges:
            for nid in (e.source_node_id, e.target_node_id):
                if nid not in visited:
                    next_frontier.add(nid)
                    visited.add(nid)
        frontier = next_frontier

    nodes = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id.in_(visited),
            KnowledgeNode.user_id == user_id,
        )
    )).scalars().all()
    return list(nodes), list(all_edges)
