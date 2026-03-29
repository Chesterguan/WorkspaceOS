import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.narrative import Narrative
from app.models.project import Project
from app.schemas.narrative import NarrativeResponse, NarrativeUpdate
from app.services import narrative_service
from sqlalchemy import select

router = APIRouter(prefix="/projects/{project_id}/narrative", tags=["narratives"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("", response_model=NarrativeResponse)
async def get_narrative(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Narrative:
    await _require_project(project_id, db)
    return await narrative_service.get_or_create(project_id, db)


@router.put("", response_model=NarrativeResponse)
async def replace_narrative(
    project_id: uuid.UUID,
    body: NarrativeUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Narrative:
    await _require_project(project_id, db)
    return await narrative_service.upsert(project_id, body, db)


@router.patch("", response_model=NarrativeResponse)
async def patch_narrative(
    project_id: uuid.UUID,
    body: NarrativeUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Narrative:
    await _require_project(project_id, db)
    return await narrative_service.upsert(project_id, body, db)
