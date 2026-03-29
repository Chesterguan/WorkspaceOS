"""
Agentic AI router: multi-round draft generation, theme extraction,
memory consolidation, and feedback recording.
"""
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.ai_feedback import AIFeedback
from app.models.project import Project
from app.models.sync import SyncRun
from app.schemas.ai_feedback import AIFeedbackCreate, AIFeedbackResponse, FeedbackSummaryResponse
from app.services.agentic_generation import agentic_generate_draft
from app.services.consolidation_service import consolidate_memory
from app.services.extraction_service import extract_sync_themes
from app.services.feedback_service import get_preference_summary, record_feedback

router = APIRouter(prefix="/projects", tags=["agentic"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


class AgenticGenerateBody(BaseModel):
    platform: str
    sync_run_id: Optional[uuid.UUID] = None
    max_rounds: int = 2


class AgenticGenerateResponse(BaseModel):
    content: str
    draft_id: uuid.UUID
    loop_trace: List[dict]


@router.post(
    "/{project_id}/generate/agentic",
    response_model=AgenticGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_agentic(
    project_id: uuid.UUID,
    body: AgenticGenerateBody,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> AgenticGenerateResponse:
    """
    Run multi-round agentic draft generation with AI self-review.
    Returns the final content, the persisted draft ID, and a trace of each round.
    """
    await _require_project(project_id, db)

    try:
        content, draft_id, loop_trace = await agentic_generate_draft(
            project_id=project_id,
            platform=body.platform,
            sync_run_id=body.sync_run_id,
            db=db,
            max_rounds=body.max_rounds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Template error: {exc}",
        )

    return AgenticGenerateResponse(content=content, draft_id=draft_id, loop_trace=loop_trace)


# ---------------------------------------------------------------------------
# Theme extraction
# ---------------------------------------------------------------------------

class ExtractionResponse(BaseModel):
    sync_run_id: uuid.UUID
    themes: List[str]
    message: str


@router.post(
    "/{project_id}/sync/{sync_run_id}/extract",
    response_model=ExtractionResponse,
)
async def extract_themes(
    project_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ExtractionResponse:
    """
    Extract structured themes from a sync run's commits and releases using AI.
    Stores results on sync_runs.themes_extracted and creates memory entries.
    """
    await _require_project(project_id, db)

    # Verify the sync run belongs to this project
    sync_result = await db.execute(
        select(SyncRun).where(SyncRun.id == sync_run_id, SyncRun.project_id == project_id)
    )
    sync_run = sync_result.scalar_one_or_none()
    if sync_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync run not found")

    try:
        await extract_sync_themes(sync_run_id=sync_run_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Re-fetch to return the stored themes
    await db.refresh(sync_run)
    themes_data = sync_run.themes_extracted or {}
    themes = themes_data.get("themes", [])

    return ExtractionResponse(
        sync_run_id=sync_run_id,
        themes=themes,
        message=f"Extracted {len(themes)} theme(s) from sync run.",
    )


# ---------------------------------------------------------------------------
# Memory consolidation
# ---------------------------------------------------------------------------

class ConsolidationResponse(BaseModel):
    project_id: uuid.UUID
    memory_entry_id: uuid.UUID
    summary_preview: str
    message: str


@router.post(
    "/{project_id}/memory/consolidate",
    response_model=ConsolidationResponse,
)
async def consolidate_project_memory(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ConsolidationResponse:
    """
    Synthesise all memory entries for the project into a single consolidated
    summary entry that improves future AI generation quality.
    """
    await _require_project(project_id, db)

    try:
        entry = await consolidate_memory(project_id=project_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return ConsolidationResponse(
        project_id=project_id,
        memory_entry_id=entry.id,
        summary_preview=entry.content[:300],
        message="Memory consolidation complete.",
    )


# ---------------------------------------------------------------------------
# Feedback recording
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/drafts/{draft_id}/feedback",
    response_model=AIFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: AIFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> AIFeedback:
    """Record human feedback on an AI-generated draft."""
    await _require_project(project_id, db)

    try:
        feedback = await record_feedback(
            draft_id=draft_id,
            project_id=project_id,
            outcome=body.outcome,
            final_content=body.final_content,
            notes=body.user_notes,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return feedback


# ---------------------------------------------------------------------------
# Feedback summary
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}/feedback/summary",
    response_model=FeedbackSummaryResponse,
)
async def feedback_summary(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> FeedbackSummaryResponse:
    """
    Return aggregated feedback statistics and a prose preference summary
    for the project, suitable for display or prompt injection.
    """
    await _require_project(project_id, db)

    # Aggregate raw counts
    result = await db.execute(
        select(AIFeedback).where(AIFeedback.project_id == project_id)
    )
    feedbacks = list(result.scalars().all())

    total = len(feedbacks)
    approved = sum(1 for f in feedbacks if f.outcome == "approved")
    rejected = sum(1 for f in feedbacks if f.outcome == "rejected")
    heavily_edited = sum(1 for f in feedbacks if f.outcome == "heavily_edited")
    approval_rate = approved / total if total > 0 else 0.0

    edit_distances = [f.edit_distance for f in feedbacks if f.edit_distance is not None]
    avg_edit: Optional[float] = (
        sum(edit_distances) / len(edit_distances) if edit_distances else None
    )

    prose = await get_preference_summary(project_id, db)

    return FeedbackSummaryResponse(
        project_id=project_id,
        total_feedbacks=total,
        approved_count=approved,
        rejected_count=rejected,
        heavily_edited_count=heavily_edited,
        approval_rate=round(approval_rate, 4),
        average_edit_distance=avg_edit,
        summary_prose=prose,
    )
