"""Knowledge layer REST routes — used by /knowledge graph UI."""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, verify_api_key
from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.schemas.knowledge import (
    EdgeCreateRequest, GraphResponse, KnowledgeEdgeOut, KnowledgeNodeOut,
    LinkedEdge, NodeCreateRequest, NodeLinksResponse, NodeUpdateRequest,
    PromoteRequest, SourceRef, allowed_node_types,
)
from app.services import knowledge_extractor, knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _resolve_user_id(auth_user_id: Optional[str]) -> uuid.UUID:
    """Knowledge endpoints are user-scoped. JWT users get their own data;
    API-key (admin) users must specify which user to act as via JWT instead."""
    if not auth_user_id:
        raise HTTPException(
            status_code=400,
            detail="user-scoped endpoint requires JWT authentication",
        )
    try:
        return uuid.UUID(auth_user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="invalid user id from token")


async def _validate_project_ownership(
    project_id: Optional[uuid.UUID],
    user_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Raise 404 if project_id is set but doesn't belong to user_id."""
    if project_id is None:
        return
    from app.models.project import Project
    owns = (await db.execute(
        select(Project.id).where(
            Project.id == project_id,
            Project.user_id == user_id,
        )
    )).scalar_one_or_none()
    if owns is None:
        raise HTTPException(404, "project not found")


@router.get("/nodes", response_model=List[KnowledgeNodeOut])
async def list_nodes(
    project_id: Optional[uuid.UUID] = Query(default=None),
    node_type: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    if node_type is not None:
        allowed = allowed_node_types()
        if allowed is not None and node_type not in allowed:
            raise HTTPException(400, f"node_type must be one of {sorted(allowed)}")

    stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    if project_id is not None:
        stmt = stmt.where(KnowledgeNode.project_id == project_id)
    if node_type is not None:
        stmt = stmt.where(KnowledgeNode.node_type == node_type)
    if not include_archived:
        stmt = stmt.where(KnowledgeNode.archived.is_(False))
    stmt = stmt.order_by(KnowledgeNode.created_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@router.post("/nodes", response_model=KnowledgeNodeOut,
             status_code=status.HTTP_201_CREATED)
async def create_node(
    body: NodeCreateRequest,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    await _validate_project_ownership(body.project_id, user_id, db)
    src = body.source_refs[0] if body.source_refs else SourceRef(kind="manual")
    node = await knowledge_extractor.promote_manual(
        user_id=user_id, project_id=body.project_id, source=src,
        suggested_type=body.node_type, title=body.title, content=body.content, db=db,
    )
    return node


@router.patch("/nodes/{node_id}", response_model=KnowledgeNodeOut)
async def update_node(
    node_id: uuid.UUID,
    body: NodeUpdateRequest,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    updates = body.model_dump(exclude_unset=True)
    if "project_id" in updates:
        await _validate_project_ownership(updates["project_id"], user_id, db)
    node = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id,
        )
    )).scalar_one_or_none()
    if node is None:
        raise HTTPException(404, "node not found")
    for field, val in updates.items():
        setattr(node, field, val)
    await db.commit()
    await db.refresh(node)
    return node


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: uuid.UUID,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    node = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id,
        )
    )).scalar_one_or_none()
    if node is None:
        raise HTTPException(404, "node not found")
    await db.delete(node)
    await db.commit()


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    root: uuid.UUID = Query(...),
    depth: int = Query(default=1, ge=1, le=3),
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    nodes, edges = await knowledge_service.get_node_with_neighbors(
        node_id=root, user_id=user_id, db=db, depth=depth,
    )
    return GraphResponse(
        nodes=[KnowledgeNodeOut.model_validate(n) for n in nodes],
        edges=[KnowledgeEdgeOut.model_validate(e) for e in edges],
    )


@router.get("/edges", response_model=List[KnowledgeEdgeOut])
async def list_edges_for_nodes(
    ids: str = Query(..., description="comma-separated node ids"),
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return all edges where both endpoints are in the supplied node-id list."""
    user_id = _resolve_user_id(auth_user_id)
    try:
        node_ids = [uuid.UUID(s) for s in ids.split(",") if s.strip()]
    except ValueError:
        raise HTTPException(400, "ids must be comma-separated UUIDs")
    if len(node_ids) > 500:
        raise HTTPException(400, "too many ids (max 500)")
    if not node_ids:
        return []
    edges = (await db.execute(
        select(KnowledgeEdge).where(
            KnowledgeEdge.user_id == user_id,
            KnowledgeEdge.source_node_id.in_(node_ids),
            KnowledgeEdge.target_node_id.in_(node_ids),
        )
    )).scalars().all()
    return list(edges)


@router.post("/promote", response_model=KnowledgeNodeOut,
             status_code=status.HTTP_201_CREATED)
async def promote(
    body: PromoteRequest,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    if not body.title or not body.content:
        raise HTTPException(400, "title and content required")
    await _validate_project_ownership(body.project_id, user_id, db)
    node = await knowledge_extractor.promote_manual(
        user_id=user_id, project_id=body.project_id, source=body.source,
        suggested_type=body.suggested_type, title=body.title, content=body.content, db=db,
    )
    return node


# ---------------------------------------------------------------------------
# Edge CRUD
# ---------------------------------------------------------------------------

@router.post("/edges", response_model=KnowledgeEdgeOut,
             status_code=status.HTTP_201_CREATED)
async def create_edge(
    body: EdgeCreateRequest,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a typed edge between two nodes owned by the authenticated user."""
    user_id = _resolve_user_id(auth_user_id)

    # Both nodes must belong to the requesting user.
    src = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == body.source_node_id,
            KnowledgeNode.user_id == user_id,
        )
    )).scalar_one_or_none()
    if src is None:
        raise HTTPException(404, "source node not found")

    tgt = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == body.target_node_id,
            KnowledgeNode.user_id == user_id,
        )
    )).scalar_one_or_none()
    if tgt is None:
        raise HTTPException(404, "target node not found")

    edge = KnowledgeEdge(
        user_id=user_id,
        source_node_id=body.source_node_id,
        target_node_id=body.target_node_id,
        edge_type=body.edge_type,
        created_by="manual",
    )
    db.add(edge)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        # Unique constraint violation → 409 Conflict
        if "uq_knowledge_edges_triple" in str(exc) or "unique" in str(exc).lower():
            raise HTTPException(409, "edge already exists")
        raise
    await db.refresh(edge)
    return edge


@router.delete("/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    edge_id: uuid.UUID,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete an edge by id. Only the owning user may delete."""
    user_id = _resolve_user_id(auth_user_id)
    edge = (await db.execute(
        select(KnowledgeEdge).where(
            KnowledgeEdge.id == edge_id,
            KnowledgeEdge.user_id == user_id,
        )
    )).scalar_one_or_none()
    if edge is None:
        raise HTTPException(404, "edge not found")
    await db.delete(edge)
    await db.commit()


@router.get("/nodes/{node_id}/links", response_model=NodeLinksResponse)
async def get_node_links(
    node_id: uuid.UUID,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return all edges attached to a node, with the linked node embedded.

    Response groups links into `outgoing` (this node is source) and
    `incoming` (this node is target) so the UI can render both directions
    without a second round-trip.
    """
    user_id = _resolve_user_id(auth_user_id)

    # Confirm the node exists and belongs to the user.
    node = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == node_id,
            KnowledgeNode.user_id == user_id,
        )
    )).scalar_one_or_none()
    if node is None:
        raise HTTPException(404, "node not found")

    # Outgoing edges: this node is the source.
    out_edges = (await db.execute(
        select(KnowledgeEdge).where(
            KnowledgeEdge.user_id == user_id,
            KnowledgeEdge.source_node_id == node_id,
        )
    )).scalars().all()

    # Incoming edges: this node is the target.
    in_edges = (await db.execute(
        select(KnowledgeEdge).where(
            KnowledgeEdge.user_id == user_id,
            KnowledgeEdge.target_node_id == node_id,
        )
    )).scalars().all()

    # Collect all referenced node IDs so we can batch-load them.
    target_ids = [e.target_node_id for e in out_edges]
    source_ids = [e.source_node_id for e in in_edges]
    all_ids = list(set(target_ids + source_ids))

    linked_nodes: dict = {}
    if all_ids:
        rows = (await db.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.id.in_(all_ids),
                KnowledgeNode.user_id == user_id,
            )
        )).scalars().all()
        linked_nodes = {n.id: n for n in rows}

    outgoing: List[LinkedEdge] = []
    for e in out_edges:
        n = linked_nodes.get(e.target_node_id)
        if n is not None:
            outgoing.append(LinkedEdge(
                edge=KnowledgeEdgeOut.model_validate(e),
                node=KnowledgeNodeOut.model_validate(n),
                direction="out",
            ))

    incoming: List[LinkedEdge] = []
    for e in in_edges:
        n = linked_nodes.get(e.source_node_id)
        if n is not None:
            incoming.append(LinkedEdge(
                edge=KnowledgeEdgeOut.model_validate(e),
                node=KnowledgeNodeOut.model_validate(n),
                direction="in",
            ))

    return NodeLinksResponse(outgoing=outgoing, incoming=incoming)
