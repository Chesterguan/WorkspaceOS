"""Knowledge layer REST routes — used by /knowledge graph UI."""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, verify_api_key
from app.models.knowledge import KnowledgeEdge, KnowledgeNode, NODE_TYPES
from app.schemas.knowledge import (
    GraphResponse, KnowledgeEdgeOut, KnowledgeNodeOut,
    NodeCreateRequest, NodeUpdateRequest, PromoteRequest, SourceRef,
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
    if node_type is not None and node_type not in NODE_TYPES:
        raise HTTPException(400, f"node_type must be one of {sorted(NODE_TYPES)}")

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
