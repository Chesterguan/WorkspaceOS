"""Work Log router — generate, list, update, delete, and export progress reports."""
import base64
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, verify_api_key
from app.models.worklog import WorkLog
from app.schemas.worklog import (
    ExportDocxResponse,
    GenerateWorkLogRequest,
    UpdateWorkLogRequest,
    WorkLogListResponse,
    WorkLogResponse,
)
from app.services.worklog_service import (
    export_to_docx,
    gather_period_data,
    generate_report,
)

router = APIRouter(prefix="/worklog", tags=["worklog"])


@router.post(
    "/generate",
    response_model=WorkLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_worklog(
    body: GenerateWorkLogRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> WorkLog:
    """Gather project data, AI-generate a progress report, and save it."""
    if body.period_type not in ("weekly", "monthly", "quarterly"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_type must be one of: weekly, monthly, quarterly",
        )
    if body.period_end < body.period_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_end must be >= period_start",
        )

    period_data = await gather_period_data(
        body.project_ids, body.period_start, body.period_end, db,
    )

    goals_dicts = None
    if body.goals:
        goals_dicts = [g.model_dump() for g in body.goals]

    content = await generate_report(
        body.period_type,
        period_data,
        goals=goals_dicts,
        additional_instructions=body.additional_instructions,
    )

    # Build title from period and project names
    project_names = list(period_data["project_names"].values())
    title = (
        f"{body.period_type.capitalize()} Report: "
        f"{body.period_start} to {body.period_end} — "
        f"{', '.join(project_names[:3])}"
    )
    if len(project_names) > 3:
        title += f" +{len(project_names) - 3} more"

    log = WorkLog(
        user_id=uuid.UUID(jwt_user_id) if jwt_user_id else None,
        title=title,
        period_type=body.period_type,
        period_start=body.period_start,
        period_end=body.period_end,
        project_ids=body.project_ids,
        content=content,
        goals={"items": goals_dicts} if goals_dicts else None,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


@router.get("", response_model=WorkLogListResponse)
async def list_worklogs(
    period_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> WorkLogListResponse:
    """List saved work logs, newest first."""
    query = select(WorkLog).order_by(WorkLog.created_at.desc())
    count_query = select(func.count()).select_from(WorkLog)

    if jwt_user_id:
        query = query.where(WorkLog.user_id == uuid.UUID(jwt_user_id))
        count_query = count_query.where(WorkLog.user_id == uuid.UUID(jwt_user_id))

    if period_type:
        query = query.where(WorkLog.period_type == period_type)
        count_query = count_query.where(WorkLog.period_type == period_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return WorkLogListResponse(items=items, total=total)


@router.get("/{worklog_id}", response_model=WorkLogResponse)
async def get_worklog(
    worklog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> WorkLog:
    result = await db.execute(select(WorkLog).where(WorkLog.id == worklog_id))
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work log not found")
    return log


@router.put("/{worklog_id}", response_model=WorkLogResponse)
async def update_worklog(
    worklog_id: uuid.UUID,
    body: UpdateWorkLogRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> WorkLog:
    result = await db.execute(select(WorkLog).where(WorkLog.id == worklog_id))
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work log not found")

    if body.title is not None:
        log.title = body.title
    if body.content is not None:
        log.content = body.content
    if body.goals is not None:
        log.goals = {"items": [g.model_dump() for g in body.goals]}

    await db.flush()
    await db.refresh(log)
    return log


@router.delete("/{worklog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worklog(
    worklog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> None:
    result = await db.execute(select(WorkLog).where(WorkLog.id == worklog_id))
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work log not found")
    await db.delete(log)
    await db.flush()


@router.post("/{worklog_id}/export-docx", response_model=ExportDocxResponse)
async def export_worklog_docx(
    worklog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ExportDocxResponse:
    """Re-gather period data and export the work log as a DOCX file (base64)."""
    result = await db.execute(select(WorkLog).where(WorkLog.id == worklog_id))
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work log not found")

    period_data = await gather_period_data(
        log.project_ids, log.period_start, log.period_end, db,
    )

    docx_bytes = export_to_docx(log.content, log.title, period_data)
    encoded = base64.b64encode(docx_bytes).decode("utf-8")

    filename = f"worklog_{log.period_type}_{log.period_start}_{log.period_end}.docx"
    return ExportDocxResponse(docx_base64=encoded, filename=filename)
