import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.memory import MemoryEntry
from app.models.project import Project
from app.schemas.memory import MemoryEntryCreate, MemoryEntryResponse, MemorySearchRequest
from app.services import memory_service

router = APIRouter(prefix="/projects/{project_id}/memory", tags=["memory"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("", response_model=list[MemoryEntryResponse])
async def list_memory(
    project_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> list[MemoryEntry]:
    await _require_project(project_id, db)
    return await memory_service.get_recent_entries(project_id, limit, db)


@router.post("", response_model=MemoryEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory_entry(
    project_id: uuid.UUID,
    body: MemoryEntryCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> MemoryEntry:
    await _require_project(project_id, db)
    return await memory_service.add_entry(
        project_id=project_id,
        entry_type=body.entry_type,
        content=body.content,
        source_ref=body.source_ref,
        db=db,
    )


@router.post("/search", response_model=list[MemoryEntryResponse])
async def search_memory(
    project_id: uuid.UUID,
    body: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> list[MemoryEntry]:
    """Semantic search over memory entries using pgvector cosine similarity."""
    await _require_project(project_id, db)
    return await memory_service.search_memory(
        project_id=project_id,
        query=body.query,
        limit=body.limit,
        db=db,
    )
