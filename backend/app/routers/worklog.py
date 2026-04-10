"""Work Log router — generate, list, update, delete, and export progress reports."""
import base64
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_db,
    get_optional_user_id,
    parse_jwt_user_uuid,
    verify_api_key,
)
from app.models.project import Project
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

    await _verify_owns_all_projects(body.project_ids, jwt_user_id, db)

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
        user_id=parse_jwt_user_uuid(jwt_user_id) if jwt_user_id else None,
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
        owner_uuid = parse_jwt_user_uuid(jwt_user_id)
        query = query.where(WorkLog.user_id == owner_uuid)
        count_query = count_query.where(WorkLog.user_id == owner_uuid)

    if period_type:
        query = query.where(WorkLog.period_type == period_type)
        count_query = count_query.where(WorkLog.period_type == period_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return WorkLogListResponse(items=items, total=total)


async def _verify_owns_all_projects(
    project_ids: list,
    jwt_user_id: Optional[str],
    db: AsyncSession,
) -> None:
    """Raise 404 if the JWT user doesn't own every project in ``project_ids``.

    No-op in API-key (admin) mode. Used before any worklog operation that reads
    from the `projects` table via raw SQL — the service layer has no user scope.
    """
    if not jwt_user_id or not project_ids:
        return
    owner_uuid = parse_jwt_user_uuid(jwt_user_id)
    owned_rows = await db.execute(
        select(Project.id).where(
            Project.id.in_(project_ids),
            Project.user_id == owner_uuid,
        )
    )
    owned_ids = {row[0] for row in owned_rows.all()}
    missing = [pid for pid in project_ids if pid not in owned_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project(s) not found or not accessible: {missing}",
        )


async def _fetch_owned_worklog(
    worklog_id: uuid.UUID,
    db: AsyncSession,
    jwt_user_id: Optional[str],
) -> WorkLog:
    query = select(WorkLog).where(WorkLog.id == worklog_id)
    if jwt_user_id:
        query = query.where(WorkLog.user_id == parse_jwt_user_uuid(jwt_user_id))
    result = await db.execute(query)
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work log not found")
    return log


@router.get("/{worklog_id}", response_model=WorkLogResponse)
async def get_worklog(
    worklog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> WorkLog:
    return await _fetch_owned_worklog(worklog_id, db, jwt_user_id)


@router.put("/{worklog_id}", response_model=WorkLogResponse)
async def update_worklog(
    worklog_id: uuid.UUID,
    body: UpdateWorkLogRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> WorkLog:
    log = await _fetch_owned_worklog(worklog_id, db, jwt_user_id)

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
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> None:
    log = await _fetch_owned_worklog(worklog_id, db, jwt_user_id)
    await db.delete(log)
    await db.flush()


@router.post("/{worklog_id}/export-docx", response_model=ExportDocxResponse)
async def export_worklog_docx(
    worklog_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> ExportDocxResponse:
    """Re-gather period data and export the work log as a DOCX file (base64)."""
    log = await _fetch_owned_worklog(worklog_id, db, jwt_user_id)

    # Projects in a saved log can drift: re-verify ownership before re-querying
    # the underlying commits/drafts/papers, otherwise a user who lost access
    # to a project after the log was created could still pull its current data.
    await _verify_owns_all_projects(log.project_ids or [], jwt_user_id, db)

    period_data = await gather_period_data(
        log.project_ids, log.period_start, log.period_end, db,
    )

    docx_bytes = export_to_docx(log.content, log.title, period_data)
    encoded = base64.b64encode(docx_bytes).decode("utf-8")

    filename = f"worklog_{log.period_type}_{log.period_start}_{log.period_end}.docx"
    return ExportDocxResponse(docx_base64=encoded, filename=filename)
