import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.project import Project
from app.schemas.ai import GenerateRequest, GenerateResponse, SummaryRequest
from app.services.ai_generation import generate_draft, generate_evolution_summary

router = APIRouter(tags=["ai"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/projects/{project_id}/generate", response_model=GenerateResponse)
async def generate_content(
    project_id: uuid.UUID,
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> GenerateResponse:
    """
    Generate a platform-specific content draft using the project's narrative,
    memory, and most recent sync data.
    """
    await _require_project(project_id, db)

    try:
        content, draft_id = await generate_draft(
            project_id=project_id,
            platform=body.platform,
            sync_run_id=body.sync_run_id,
            db=db,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return GenerateResponse(content=content, platform=body.platform, draft_id=draft_id)


@router.post("/generate/summary", response_model=GenerateResponse)
async def generate_summary(
    body: SummaryRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> GenerateResponse:
    """
    Generate an evolution summary for a completed sync run and persist it
    on the SyncRun record.
    """
    try:
        summary = await generate_evolution_summary(body.sync_run_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return GenerateResponse(
        content=summary,
        platform="evolution_summary",
        draft_id=None,
    )
