"""Action button handlers.

An action button renders on a specific target item (chat_message,
knowledge_node, draft, paper). Clicking it POSTs to
`/capabilities/actions/<name>/invoke` with `{target_id, payload}`. The
registered handler does the work and returns a small response the
frontend renders as a toast / SWR mutate / route push.

Target-type validation lives in the manifest's `target` field. Each
handler still validates that the named target_id actually exists +
belongs to the calling user.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Dict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeNode
from app.services.event_stream import emit

logger = logging.getLogger(__name__)


ActionHandler = Callable[
    [Dict[str, Any], AsyncSession, uuid.UUID],
    Awaitable[Dict[str, Any]],
]


async def _mark_as_decision(
    payload: Dict[str, Any],
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Dict[str, Any]:
    """Re-type a knowledge node as `decision`.

    The taxonomy auto-extractor sometimes classifies a clear decision as
    a generic claim or insight; this action lets the user fix that with
    a click instead of editing JSON. Useful for re-grading via the bench.
    """
    target_id = _parse_uuid(payload.get("target_id"))
    node = await _get_user_node(db, user_id, target_id)
    if node is None:
        return {"ok": False, "error": "Node not found or not yours"}

    if node.node_type == "decision":
        return {"ok": True, "toast": "Already a decision."}

    prior = node.node_type
    await db.execute(
        update(KnowledgeNode)
        .where(KnowledgeNode.id == target_id)
        .values(node_type="decision")
    )
    await db.commit()
    emit("success", "action-button",
         f"Node retyped: {prior} → decision",
         meta={"node_id": str(target_id), "title": node.title[:60]})
    return {"ok": True, "toast": f"Marked “{node.title[:40]}” as a decision."}


async def _archive_node(
    payload: Dict[str, Any],
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Dict[str, Any]:
    """Soft-delete a knowledge node.

    Archived nodes stay in the DB but the graph view filters them out.
    Keeps the surface clean without losing provenance — important for
    nodes that came from a capability ingest source.
    """
    target_id = _parse_uuid(payload.get("target_id"))
    node = await _get_user_node(db, user_id, target_id)
    if node is None:
        return {"ok": False, "error": "Node not found or not yours"}

    if node.archived:
        return {"ok": True, "toast": "Already archived."}

    await db.execute(
        update(KnowledgeNode)
        .where(KnowledgeNode.id == target_id)
        .values(archived=True)
    )
    await db.commit()
    emit("info", "action-button",
         f"Node archived: {node.title[:60]}",
         meta={"node_id": str(target_id)})
    return {"ok": True, "toast": f"Archived “{node.title[:40]}”."}


# name → handler. Frontend POSTs to /capabilities/actions/<name>/invoke.
ACTION_HANDLERS: Dict[str, ActionHandler] = {
    "mark_as_decision": _mark_as_decision,
    "archive_node": _archive_node,
}


def list_handlers() -> list[str]:
    return sorted(ACTION_HANDLERS.keys())


# ── Helpers ────────────────────────────────────────────────────────────


def _parse_uuid(raw: Any) -> uuid.UUID:
    if not raw:
        raise ValueError("target_id is required")
    if isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


async def _get_user_node(
    db: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> KnowledgeNode | None:
    """Load a node only if it belongs to this user — basic IDOR guard."""
    res = await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == node_id,
            KnowledgeNode.user_id == user_id,
        )
    )
    return res.scalar_one_or_none()
