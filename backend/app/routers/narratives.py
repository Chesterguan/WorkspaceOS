import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, require_owned_project, verify_api_key
from app.models.narrative import Narrative
from app.schemas.narrative import NarrativeResponse, NarrativeUpdate
from app.services import narrative_service

router = APIRouter(prefix="/projects/{project_id}/narrative", tags=["narratives"])


@router.get("", response_model=NarrativeResponse)
async def get_narrative(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> Narrative:
    await require_owned_project(project_id, db, jwt_user_id)
    return await narrative_service.get_or_create(project_id, db)


@router.put("", response_model=NarrativeResponse)
async def replace_narrative(
    project_id: uuid.UUID,
    body: NarrativeUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> Narrative:
    await require_owned_project(project_id, db, jwt_user_id)
    return await narrative_service.upsert(project_id, body, db)


@router.patch("", response_model=NarrativeResponse)
async def patch_narrative(
    project_id: uuid.UUID,
    body: NarrativeUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> Narrative:
    await require_owned_project(project_id, db, jwt_user_id)
    return await narrative_service.upsert(project_id, body, db)
