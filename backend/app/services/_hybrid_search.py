"""Generic primitives for hybrid retrieval pipelines.

Used by both memory_service (over memory_entries) and knowledge_service
(over knowledge_nodes). The two services share fusion + reranking logic
but do their own per-table SQL — that's the right boundary because
each table has different scoping rules (memory: project-scoped with
optional cross-project allowlist; knowledge: user-scoped with optional
project filter).
"""
import asyncio
import logging
from typing import Dict, Hashable, List, Sequence, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def reciprocal_rank_fusion_ids(
    ranked_lists: Sequence[Sequence[Hashable]],
    k: int = 60,
) -> List[Hashable]:
    """RRF fusion over opaque IDs. Returns deduplicated, score-sorted IDs.

    Each input list is a ranked list of IDs (best first). The result is the
    fusion of all lists by reciprocal rank.
    """
    scores: Dict[Hashable, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rank + k)
    return sorted(scores.keys(), key=lambda i: scores[i], reverse=True)


# Lazy reranker singleton
_reranker = None  # None = not tried, False = tried and failed


def _get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from flashrank import Ranker
            _reranker = Ranker()
        except Exception:
            logger.warning("FlashRank unavailable; reranking will be a no-op")
            _reranker = False
    return _reranker if _reranker is not False else None


async def rerank_passages(
    query: str,
    passages: List[dict],  # [{"id": <opaque str>, "text": <str>}, ...]
    top_k: int,
) -> List[str]:
    """Rerank `passages` and return the IDs (as strings) in new order, top-K."""
    if not passages:
        return []
    reranker = _get_reranker()
    if reranker is None:
        return [p["id"] for p in passages[:top_k]]

    from flashrank import RerankRequest
    request = RerankRequest(query=query, passages=passages)
    loop = asyncio.get_running_loop()
    try:
        reranked = await loop.run_in_executor(None, reranker.rerank, request)
    except Exception:
        logger.exception("FlashRank rerank failed; returning original order")
        return [p["id"] for p in passages[:top_k]]

    out: List[str] = []
    for r in reranked[:top_k]:
        rid = r["id"] if isinstance(r, dict) else getattr(r, "id", None)
        if rid is not None:
            out.append(str(rid))
    return out
