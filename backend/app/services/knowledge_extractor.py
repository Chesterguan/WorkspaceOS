"""Knowledge extractor — pulls structured nodes from roundtable turns.

See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


_CLASSIFIER_SYSTEM = (
    "You are a precision classifier. Reply with exactly one word: YES or NO. "
    "Nothing else."
)
_CLASSIFIER_TEMPLATE = (
    "Does this conversation turn contain extractable knowledge?\n"
    "Extractable = states a decision, claim, hypothesis, question to revisit, "
    "rejection, blocker, or insight.\n"
    "NOT extractable = greeting, acknowledgment, restating provided context, "
    "pure question with no answer.\n\n"
    "USER: {user}\n\nAI: {ai}\n\n"
    "Reply YES or NO."
)


async def _classify_extractable(ai: Any, user: str, ai_response: str) -> bool:
    """Stage 1: cheap YES/NO check. Anything that doesn't normalize to YES → False."""
    try:
        raw = await ai.complete(
            _CLASSIFIER_SYSTEM,
            _CLASSIFIER_TEMPLATE.format(user=user[:1500], ai=ai_response[:3000]),
        )
    except Exception:
        logger.exception("knowledge classifier failed")
        return False
    token = (raw or "").strip().rstrip(".").upper()
    return token == "YES"


import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from app.models.knowledge import NODE_TYPES, EDGE_TYPES


@dataclass
class ExtractedNode:
    node_type: str
    title: str
    content: str
    confidence: float = 0.7


@dataclass
class ExtractionResult:
    nodes: List[ExtractedNode] = field(default_factory=list)
    edges_within_turn: List[Dict[str, Any]] = field(default_factory=list)


_EXTRACTION_SYSTEM = (
    "You extract structured knowledge from conversation turns. "
    "Output ONLY valid JSON, no prose, no fences. "
    "Schema:\n"
    '{"nodes":[{"node_type":"<one of: claim|decision|question|hypothesis|rejection|blocker|insight>",'
    '"title":"<=120 chars","content":"1-3 sentences","confidence":0..1,'
    '"rationale":"why this type"}],'
    '"edges_within_turn":[{"from_idx":int,"to_idx":int,'
    '"edge_type":"<one of: supports|contradicts|refines|follows_up|depends_on|derives_from|rejects|related_to>"}]}'
    "\nIf nothing meaningful, return {\"nodes\":[],\"edges_within_turn\":[]}."
)


def _build_extraction_user(user: str, ai_response: str, kind: str,
                           recent_turns: List[Dict[str, str]]) -> str:
    history = ""
    if recent_turns:
        lines = [f"{t['role'].upper()}: {t['content'][:400]}" for t in recent_turns[-5:]]
        history = "## Recent context\n" + "\n".join(lines) + "\n\n"
    bias = (
        "This is a Co-Founder roundtable; expect more decisions/rejections/insights."
        if kind == "cofounder"
        else "This is an academic Research roundtable; expect more claims/hypotheses/questions."
    )
    return (
        f"{history}{bias}\n\n"
        f"## Current turn\nUSER: {user[:2000]}\n\nAI: {ai_response[:4000]}\n\n"
        "Extract any extractable nodes per the schema."
    )


def _strip_json_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s


async def _extract_structured(
    ai: Any, user: str, ai_response: str, conversation_kind: str,
    recent_turns: List[Dict[str, str]],
) -> ExtractionResult:
    """Stage 2. JSON parse failure → empty result, never raises."""
    try:
        raw = await ai.complete(
            _EXTRACTION_SYSTEM,
            _build_extraction_user(user, ai_response, conversation_kind, recent_turns),
        )
    except Exception:
        logger.exception("knowledge structured extraction failed")
        return ExtractionResult()

    try:
        data = json.loads(_strip_json_fences(raw))
    except (ValueError, TypeError):
        logger.warning("knowledge extractor: non-JSON output, dropping. raw=%r", raw[:300])
        return ExtractionResult()

    nodes: List[ExtractedNode] = []
    for n in data.get("nodes", []):
        if not isinstance(n, dict):
            continue
        nt = n.get("node_type")
        if nt not in NODE_TYPES:
            continue
        title = (n.get("title") or "")[:160].strip()
        content = (n.get("content") or "").strip()
        if not title or not content:
            continue
        nodes.append(ExtractedNode(
            node_type=nt, title=title, content=content,
            confidence=float(n.get("confidence", 0.7)),
        ))

    edges: List[Dict[str, Any]] = []
    for e in data.get("edges_within_turn", []):
        if not isinstance(e, dict):
            continue
        et = e.get("edge_type")
        if et not in EDGE_TYPES:
            continue
        try:
            from_idx = int(e["from_idx"])
            to_idx = int(e["to_idx"])
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= from_idx < len(nodes) and 0 <= to_idx < len(nodes) and from_idx != to_idx:
            edges.append({"from_idx": from_idx, "to_idx": to_idx, "edge_type": et})

    return ExtractionResult(nodes=nodes, edges_within_turn=edges)


# ---------------------------------------------------------------------------
# Dedup decision logic
# ---------------------------------------------------------------------------

# Similarity thresholds — can be moved to settings later if tuning is needed
DEDUP_HIGH = 0.92  # at/above → merge
DEDUP_LOW = 0.80   # at/above → create with linking edge


@dataclass
class DedupAction:
    kind: str  # "merge" | "create_with_edge" | "create"
    edge_type: Optional[str] = None


def _decide_dedup_action(best_score: Optional[float], same_type: bool) -> DedupAction:
    if best_score is None:
        return DedupAction(kind="create")
    if best_score >= DEDUP_HIGH:
        return DedupAction(kind="merge")
    if best_score >= DEDUP_LOW:
        return DedupAction(
            kind="create_with_edge",
            edge_type="refines" if same_type else "related_to",
        )
    return DedupAction(kind="create")


# ---------------------------------------------------------------------------
# Persistence orchestrator
# ---------------------------------------------------------------------------

import uuid as _uuid_module
from typing import Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.models.chat import ChatMessage
from app.services.ai_client import get_cloud_client


async def _embed(text_to_embed: str) -> List[float]:
    """Wrap ai_client embed for easier mocking in tests."""
    ai = get_cloud_client()
    return await ai.embed(text_to_embed)


async def _find_nearest(
    db: AsyncSession,
    user_id: _uuid_module.UUID,
    embedding: List[float],
    node_type: str,
    k: int = 3,
) -> List[Tuple[KnowledgeNode, float]]:
    """Return up to k existing nodes for this user ranked by cosine similarity.
    Same node_type gets a small bias boost in the final sort."""
    if not embedding:
        return []
    sql = text("""
        SELECT id, 1 - (embedding <=> CAST(:emb AS vector)) AS sim
        FROM knowledge_nodes
        WHERE user_id = :uid AND embedding IS NOT NULL AND archived = false
        ORDER BY embedding <=> CAST(:emb AS vector)
        LIMIT :k
    """)
    rows = (await db.execute(sql, {"emb": str(embedding), "uid": str(user_id), "k": k})).all()
    if not rows:
        return []
    ids = [r.id for r in rows]
    nodes = {n.id: n for n in (
        await db.execute(select(KnowledgeNode).where(KnowledgeNode.id.in_(ids)))
    ).scalars().all()}
    out: List[Tuple[KnowledgeNode, float]] = []
    for r in rows:
        node = nodes.get(r.id)
        if node is not None:
            out.append((node, float(r.sim)))
    out.sort(key=lambda x: (x[1] + (0.02 if x[0].node_type == node_type else 0.0)), reverse=True)
    return out


def _make_source_ref(ai_message: ChatMessage) -> dict:
    return {
        "kind": "chat_message",
        "id": str(ai_message.id),
        "excerpt": (ai_message.content or "")[:200],
    }


async def extract_from_chat_turn(
    user_id: _uuid_module.UUID,
    project_id: Optional[_uuid_module.UUID],
    user_message: ChatMessage,
    ai_message: ChatMessage,
    conversation_kind: str,
    db: AsyncSession,
) -> None:
    """End-to-end per-turn extraction. Best-effort; any failure → rollback + log."""
    try:
        ai = get_cloud_client()

        if not await _classify_extractable(ai, user_message.content or "", ai_message.content or ""):
            return

        result = await _extract_structured(
            ai, user_message.content or "", ai_message.content or "",
            conversation_kind, recent_turns=[],
        )
        if not result.nodes:
            return

        persisted: List[Optional[KnowledgeNode]] = []  # index-aligned with result.nodes (None for merged)
        for extracted in result.nodes:
            try:
                embed_text = f"{extracted.title}\n\n{extracted.content}"
                embedding = await _embed(embed_text)
            except Exception:
                logger.exception("embed failed; skipping node")
                persisted.append(None)
                continue

            neighbors = await _find_nearest(db, user_id, embedding, extracted.node_type)
            best = neighbors[0] if neighbors else None
            action = _decide_dedup_action(
                best_score=best[1] if best else None,
                same_type=(best is not None and best[0].node_type == extracted.node_type),
            )

            if action.kind == "merge" and best is not None:
                existing = best[0]
                existing.source_refs = (existing.source_refs or []) + [_make_source_ref(ai_message)]
                meta = dict(existing.metadata_ or {})
                meta["reinforcement_count"] = int(meta.get("reinforcement_count", 1)) + 1
                existing.metadata_ = meta
                persisted.append(existing)
                continue

            node = KnowledgeNode(
                user_id=user_id, project_id=project_id,
                node_type=extracted.node_type, title=extracted.title,
                content=extracted.content, embedding=embedding,
                source_refs=[_make_source_ref(ai_message)],
                metadata_={
                    "confidence": extracted.confidence,
                    "extraction_model": "gemini_flash",
                    "conversation_kind": conversation_kind,
                },
                created_by="auto_extractor",
            )
            db.add(node)
            await db.flush()  # populate node.id

            if action.kind == "create_with_edge" and best is not None and action.edge_type:
                db.add(KnowledgeEdge(
                    user_id=user_id, source_node_id=node.id,
                    target_node_id=best[0].id, edge_type=action.edge_type, weight=0.5,
                    source_refs=[_make_source_ref(ai_message)],
                    created_by="auto_extractor",
                ))
            persisted.append(node)

        # Within-turn edges from extractor JSON
        for edge in result.edges_within_turn:
            src = persisted[edge["from_idx"]]
            tgt = persisted[edge["to_idx"]]
            if src is None or tgt is None or src.id == tgt.id:
                continue
            db.add(KnowledgeEdge(
                user_id=user_id, source_node_id=src.id, target_node_id=tgt.id,
                edge_type=edge["edge_type"], weight=1.0,
                source_refs=[_make_source_ref(ai_message)], created_by="auto_extractor",
            ))

        await db.commit()
    except Exception:
        logger.exception("knowledge extractor failed; rolling back")
        try:
            await db.rollback()
        except Exception:
            logger.exception("rollback also failed; abandoning session")
