import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.draft import Draft
from app.models.project import Project
from app.schemas.draft import DraftCreate, DraftResponse, DraftUpdate
from app.services import draft_service

router = APIRouter(prefix="/projects/{project_id}/drafts", tags=["drafts"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _require_draft(
    project_id: uuid.UUID, draft_id: uuid.UUID, db: AsyncSession
) -> Draft:
    draft = await draft_service.get_draft(draft_id, db)
    if draft is None or draft.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft


@router.post("", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(
    project_id: uuid.UUID,
    body: DraftCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Draft:
    await _require_project(project_id, db)
    return await draft_service.create_draft(project_id, body, db)


@router.get("", response_model=List[DraftResponse])
async def list_drafts(
    project_id: uuid.UUID,
    platform: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[Draft]:
    await _require_project(project_id, db)
    return await draft_service.list_drafts(project_id, db, platform=platform)


@router.get("/{draft_id}", response_model=DraftResponse)
async def get_draft(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Draft:
    return await _require_draft(project_id, draft_id, db)


@router.patch("/{draft_id}", response_model=DraftResponse)
async def update_draft(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Draft:
    draft = await _require_draft(project_id, draft_id, db)
    return await draft_service.update_draft(draft, body, db)


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> None:
    draft = await _require_draft(project_id, draft_id, db)
    await draft_service.delete_draft(draft, db)


@router.post("/{draft_id}/versions", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
async def create_new_version(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Draft:
    """Create a new version of a draft. The body should contain the revised content."""
    await _require_draft(project_id, draft_id, db)
    if not body.content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'content' is required when creating a new version.",
        )
    return await draft_service.save_new_version(
        parent_draft_id=draft_id,
        content=body.content,
        generation_prompt=None,
        db=db,
    )


@router.get("/{draft_id}/versions", response_model=List[DraftResponse])
async def get_version_chain(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[Draft]:
    """Return all versions in the chain for a given draft."""
    await _require_draft(project_id, draft_id, db)
    return await draft_service.get_version_chain(draft_id, db)
