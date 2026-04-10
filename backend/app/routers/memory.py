import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_db,
    get_optional_user_id,
    parse_jwt_user_uuid,
    require_owned_project,
    verify_api_key,
)
from app.models.memory import MemoryEntry
from app.models.project import Project
from app.schemas.memory import (
    CrossProjectSearchRequest,
    MemoryEntryCreate,
    MemoryEntryResponse,
    MemorySearchRequest,
)
from app.services import memory_service

router = APIRouter(prefix="/projects/{project_id}/memory", tags=["memory"])
global_router = APIRouter(prefix="/memory", tags=["memory"])


async def _resolve_user_project_ids(
    jwt_user_id: Optional[str], db: AsyncSession
) -> Optional[List[uuid.UUID]]:
    """Return the project IDs owned by the JWT user, or None for API key (admin)."""
    if jwt_user_id is None:
        return None
    owner_uuid = parse_jwt_user_uuid(jwt_user_id)
    result = await db.execute(
        select(Project.id).where(Project.user_id == owner_uuid)
    )
    return [row[0] for row in result.all()]


@router.get("", response_model=list[MemoryEntryResponse])
async def list_memory(
    project_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> list[MemoryEntry]:
    await require_owned_project(project_id, db, jwt_user_id)
    return await memory_service.get_recent_entries(project_id, limit, db)


@router.post("", response_model=MemoryEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory_entry(
    project_id: uuid.UUID,
    body: MemoryEntryCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> MemoryEntry:
    await require_owned_project(project_id, db, jwt_user_id)
    return await memory_service.add_entry(
        project_id=project_id,
        entry_type=body.entry_type,
        content=body.content,
        source_ref=body.source_ref,
        db=db,
    )


@router.post(
    "/wiki/refresh",
    status_code=status.HTTP_200_OK,
    summary="Refresh the project wiki summary",
)
async def refresh_wiki(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """Manually trigger wiki summary generation/update."""
    from app.services.memory_service import upsert_wiki_summary

    await require_owned_project(project_id, db, jwt_user_id)
    entry = await upsert_wiki_summary(project_id, db)
    return {
        "id": str(entry.id),
        "content": entry.content,
        "updated_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.post("/search", response_model=list[MemoryEntryResponse])
async def search_memory(
    project_id: uuid.UUID,
    body: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> list[MemoryEntry]:
    """Hybrid search over memory entries (pgvector + BM25 + RRF + reranking)."""
    await require_owned_project(project_id, db, jwt_user_id)
    return await memory_service.search_memory(
        project_id=project_id,
        query=body.query,
        limit=body.limit,
        db=db,
    )


# ---------------------------------------------------------------------------
# Cross-project search (mounted separately at /memory)
# ---------------------------------------------------------------------------
@global_router.post("/search-all", response_model=list[MemoryEntryResponse])
async def search_all_memory(
    body: CrossProjectSearchRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> list[MemoryEntry]:
    """Search memory across ALL projects owned by the authenticated user.

    API-key callers (admin / scripts) see everything.
    """
    allowlist = await _resolve_user_project_ids(jwt_user_id, db)
    # Use a dummy project_id — cross_project=True ignores it and uses the allowlist
    dummy_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    return await memory_service.search_memory(
        project_id=dummy_id,
        query=body.query,
        limit=body.limit,
        db=db,
        cross_project=True,
        project_id_allowlist=allowlist,
    )


@global_router.post("/backfill-embeddings")
async def backfill_embeddings(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """Generate embeddings for all memory entries missing them.

    Admin-only (API key). JWT users are rejected — this is a DB-wide maintenance
    operation and should not be reachable by end users.
    """
    if jwt_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin-only endpoint",
        )
    updated = await memory_service.backfill_embeddings(db)
    return {"updated": updated, "message": f"Backfilled {updated} entries"}
