"""Knowledge extractor — pulls structured nodes from roundtable turns.

See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md

Prompts and the active node/edge type taxonomy live in config/ — see
SurfaceExtractionRefs (stage1/stage2/taxonomy) on the cofounder surface.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.schemas.domain_config import SurfaceExtractionRefs
from app.services.domain_config import get_loader
from app.services.egress_recorder import EgressRecorder

logger = logging.getLogger(__name__)


def _extraction_refs() -> SurfaceExtractionRefs:
    """Return the first surface's extraction refs (only cofounder has them today)."""
    for s in get_loader().get_surfaces():
        if s.extraction:
            return s.extraction
    raise RuntimeError("no surface has extraction configured")


def _allowed_extraction_types() -> tuple:
    """Return (node_type_ids, edge_type_ids) from the extraction surface's taxonomy.

    Returns (None, None) if no taxonomy is configured — treat as "accept anything"
    so a misconfigured surface doesn't silently drop every extraction.
    """
    ext = _extraction_refs()
    if not ext.taxonomy:
        return (None, None)
    tax = get_loader().get_taxonomy_by_path(ext.taxonomy)
    return (tax.node_type_ids, tax.edge_type_ids)


def _allowed_node_types_for_manual() -> Optional[set]:
    """Union of node-type IDs declared by the active surface taxonomy
    AND every installed extension's taxonomy_extra. Looser than
    `_allowed_extraction_types` because manual promotion shouldn't
    block on capability-introduced node types (tool, protocol, ...)
    just because the user hasn't re-run onboarding to merge them
    into the active surface taxonomy yet.

    Returns None when there's no taxonomy anywhere — treat as
    "accept anything" so a misconfigured deploy doesn't soft-brick
    manual promotion.
    """
    types: set = set()
    surface_types, _ = _allowed_extraction_types()
    if surface_types is not None:
        types.update(surface_types)
    try:
        from app.services.extensions import get_all_extensions
        import yaml as _yaml
        for ext in get_all_extensions():
            if not ext.taxonomy_extra:
                continue
            try:
                data = _yaml.safe_load(ext.taxonomy_extra) or {}
            except Exception:
                continue
            for n in (data.get("node_types") or []):
                nid = n.get("id") if isinstance(n, dict) else None
                if nid:
                    types.add(nid)
    except Exception:
        logger.exception("failed to merge extension taxonomies for manual promote")
    return types or None


async def _classify_extractable(ai: Any, user: str, ai_response: str) -> bool:
    """Stage 1: cheap YES/NO check. Anything that doesn't normalize to YES → False."""
    ext = _extraction_refs()
    if not ext.stage1:
        logger.warning("extraction surface missing stage1 prompt; skipping classification")
        return False
    system = get_loader().render_prompt(ext.stage1, taxonomy_path=ext.taxonomy)
    template_ref = ext.stage1.replace("stage1-classifier.txt", "stage1-classifier-template.txt")
    user_prompt = get_loader().render_prompt(
        template_ref,
        taxonomy_path=ext.taxonomy,
        extra_vars={"user": user[:1500], "ai": ai_response[:3000]},
    )
    try:
        async with EgressRecorder(
            surface="knowledge",
            service="knowledge_extractor.classify",
            provider=type(ai).__name__.lower().replace("client", ""),
            model=getattr(ai, "_model", None) or getattr(ai, "chat_model", None),
            user_id=None,
            project_id=None,
        ) as rec:
            rec.field("system_prompt", system)
            rec.field("user_message", user[:1500])
            rec.field("ai_message", ai_response[:3000])
            raw = await ai.complete(system, user_prompt)
    except Exception:
        logger.exception("knowledge classifier failed")
        return False
    token = (raw or "").strip().rstrip(".").upper()
    return token == "YES"


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
    ext = _extraction_refs()
    if not ext.stage2:
        logger.warning("extraction surface missing stage2 prompt; skipping extraction")
        return ExtractionResult()
    system_prompt = get_loader().render_prompt(ext.stage2, taxonomy_path=ext.taxonomy)
    node_types, edge_types = _allowed_extraction_types()

    try:
        extraction_user = _build_extraction_user(user, ai_response, conversation_kind, recent_turns)
        async with EgressRecorder(
            surface="knowledge",
            service="knowledge_extractor.extract",
            provider=type(ai).__name__.lower().replace("client", ""),
            model=getattr(ai, "_model", None) or getattr(ai, "chat_model", None),
            user_id=None,
            project_id=None,
        ) as rec:
            rec.field("system_prompt", system_prompt)
            rec.field("user_message", user[:1500])
            rec.field("ai_message", ai_response[:4000])
            raw = await ai.complete(system_prompt, extraction_user)
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
        if node_types is not None and nt not in node_types:
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
        if edge_types is not None and et not in edge_types:
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
        # Only merge when types match. Cross-type merges silently mutate node
        # type semantics (a "decision" being absorbed by a "claim", etc).
        if same_type:
            return DedupAction(kind="merge")
        # Same content, different type — link them instead of merging.
        return DedupAction(kind="create_with_edge", edge_type="related_to")
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.models.chat import ChatMessage
from app.services.ai_client import get_cloud_client, get_local_client


async def _embed(text_to_embed: str) -> List[float]:
    """Wrap ai_client embed for easier mocking in tests."""
    # Embeddings stay local — same invariant as memory_service.add_entry and
    # knowledge_service.query_embedding. See docs/privacy/known-leaks.md#l-1.
    ai = get_local_client()
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
                # Use a savepoint so a duplicate-edge IntegrityError drops only
                # this edge without rolling back the whole extraction turn.
                async with db.begin_nested() as sp:
                    try:
                        db.add(KnowledgeEdge(
                            user_id=user_id, source_node_id=node.id,
                            target_node_id=best[0].id, edge_type=action.edge_type, weight=0.5,
                            source_refs=[_make_source_ref(ai_message)],
                            created_by="auto_extractor",
                        ))
                        await db.flush()
                    except IntegrityError:
                        await sp.rollback()
                        logger.debug("knowledge edge create failed (likely duplicate); skipping")
            persisted.append(node)

        # Within-turn edges from extractor JSON
        for edge in result.edges_within_turn:
            src = persisted[edge["from_idx"]]
            tgt = persisted[edge["to_idx"]]
            if src is None or tgt is None or src.id == tgt.id:
                continue
            # Use a savepoint so a duplicate-edge IntegrityError drops only
            # this edge without rolling back the whole extraction turn.
            async with db.begin_nested() as sp:
                try:
                    db.add(KnowledgeEdge(
                        user_id=user_id, source_node_id=src.id, target_node_id=tgt.id,
                        edge_type=edge["edge_type"], weight=1.0,
                        source_refs=[_make_source_ref(ai_message)], created_by="auto_extractor",
                    ))
                    await db.flush()
                except IntegrityError:
                    await sp.rollback()
                    logger.debug("knowledge edge create failed (likely duplicate); skipping")

        await db.commit()
        try:
            from app.services.event_stream import emit
            persisted_count = len([n for n in persisted if n is not None])
            if persisted_count > 0:
                emit(
                    "success",
                    "extract",
                    f"+{persisted_count} knowledge node{'s' if persisted_count != 1 else ''}",
                    project_id=str(project_id) if project_id else None,
                    meta={"nodes": persisted_count},
                )
        except Exception:
            logger.exception("event emit failed (non-fatal)")
    except Exception:
        logger.exception("knowledge extractor failed; rolling back")
        try:
            await db.rollback()
        except Exception:
            logger.exception("rollback also failed; abandoning session")


# ---------------------------------------------------------------------------
# Public fire-and-forget entry point (shared by chat_service + research_service)
# ---------------------------------------------------------------------------

from app.schemas.knowledge import SourceRef


async def promote_manual(
    user_id: _uuid_module.UUID,
    project_id: Optional[_uuid_module.UUID],
    source: SourceRef,
    suggested_type: Optional[str],
    title: Optional[str],
    content: Optional[str],
    db: AsyncSession,
) -> KnowledgeNode:
    """Manual promotion. If title/content missing, the caller must supply them — no inference here in v1."""
    if not title or not content:
        raise ValueError("title and content required for manual promotion")
    nt = suggested_type or "insight"
    # Manual promotion accepts any node type declared by either:
    #   - the active surface's taxonomy, or
    #   - any *installed* extension's taxonomy_extra
    # Capabilities (e.g. ingest sources) created in v0.2.6 declare new
    # node types in their bundled taxonomies (tool, protocol, ...).
    # Restricting manual promotion to only the active surface's
    # taxonomy would forbid promoting those types — even though the
    # ingest pipeline freely creates them via upsert_node. Allowing
    # extension-declared types here removes that asymmetry.
    node_types = _allowed_node_types_for_manual()
    if node_types is not None and nt not in node_types:
        raise ValueError(f"node_type must be one of {sorted(node_types)}")

    embedding: List[float]
    try:
        embedding = await _embed(f"{title}\n\n{content}")
    except Exception:
        logger.exception("embed failed during manual promote; storing without")
        embedding = []

    node = KnowledgeNode(
        user_id=user_id, project_id=project_id, node_type=nt,
        title=title.strip()[:160], content=content.strip(),
        embedding=embedding or None,
        source_refs=[source.model_dump(exclude_none=True)],
        metadata_={"extraction_model": "manual"},
        created_by="manual_promote",
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


# Per-user serialization for fire-and-forget extractions.
# Roundtable dispatches N advisor messages in parallel; without serialization
# all N extractions run concurrently, each opening its own session and seeing
# an empty knowledge_nodes table for that user, so dedup misses overlapping
# nodes and the DB ends up with N duplicates of the same insight. Serializing
# per-user lets each task see the previous task's committed nodes.
import asyncio as _asyncio

_user_locks: dict = {}
_user_locks_guard = _asyncio.Lock()


async def _get_user_lock(user_id: _uuid_module.UUID) -> _asyncio.Lock:
    async with _user_locks_guard:
        lock = _user_locks.get(user_id)
        if lock is None:
            lock = _asyncio.Lock()
            _user_locks[user_id] = lock
        return lock


async def bg_extract_from_turn(
    user_id: _uuid_module.UUID,
    project_id: _uuid_module.UUID,
    user_msg_id: _uuid_module.UUID,
    user_msg_content: str,
    ai_msg_id: _uuid_module.UUID,
    ai_msg_content: str,
    conversation_kind: str,
) -> None:
    """Public fire-and-forget entry point. Owns its own DB session.

    Builds lightweight transient ChatMessage instances (not session-attached) since
    extract_from_chat_turn only reads .id and .content from them.

    Serializes per-user so concurrent advisor extractions see each other's
    committed nodes when running their dedup lookup (prevents duplicate-node
    explosion on roundtable replies).
    """
    try:
        lock = await _get_user_lock(user_id)
        async with lock:
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                user_msg = ChatMessage(
                    id=user_msg_id, project_id=project_id,
                    role="user", content=user_msg_content,
                )
                ai_msg = ChatMessage(
                    id=ai_msg_id, project_id=project_id,
                    role="assistant", content=ai_msg_content,
                )
                await extract_from_chat_turn(
                    user_id=user_id, project_id=project_id,
                    user_message=user_msg, ai_message=ai_msg,
                    conversation_kind=conversation_kind, db=bg_db,
                )
    except Exception:
        logger.exception("background knowledge extraction (%s) failed", conversation_kind)
