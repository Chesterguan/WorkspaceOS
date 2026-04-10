"""
Posting module router: manage post schedules and post records per project.
Recording a post also transitions the linked draft to 'published'.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, require_owned_project, verify_api_key
from app.models.draft import Draft
from app.models.posting import PostRecord, PostSchedule
from app.schemas.posting import (
    PostRecordCreate,
    PostRecordResponse,
    PostScheduleCreate,
    PostScheduleResponse,
    PostScheduleUpdate,
)

router = APIRouter(prefix="/projects", tags=["posting"])


# ---------------------------------------------------------------------------
# PostSchedule endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/post-schedules",
    response_model=PostScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_post_schedule(
    project_id: uuid.UUID,
    body: PostScheduleCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> PostSchedule:
    await require_owned_project(project_id, db, jwt_user_id)

    # Verify the referenced draft belongs to this project
    draft_result = await db.execute(
        select(Draft).where(Draft.id == body.draft_id, Draft.project_id == project_id)
    )
    if draft_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found in this project",
        )

    schedule = PostSchedule(
        draft_id=body.draft_id,
        project_id=project_id,
        platform=body.platform,
        scheduled_for=body.scheduled_for,
        status=body.status,
        notes=body.notes,
    )
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    return schedule


@router.get("/{project_id}/post-schedules", response_model=List[PostScheduleResponse])
async def list_post_schedules(
    project_id: uuid.UUID,
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> List[PostSchedule]:
    await require_owned_project(project_id, db, jwt_user_id)

    query = (
        select(PostSchedule)
        .where(PostSchedule.project_id == project_id)
        .order_by(PostSchedule.scheduled_for.asc())
    )
    if from_date:
        query = query.where(PostSchedule.scheduled_for >= from_date)
    if to_date:
        query = query.where(PostSchedule.scheduled_for <= to_date)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.patch("/{project_id}/post-schedules/{schedule_id}", response_model=PostScheduleResponse)
async def update_post_schedule(
    project_id: uuid.UUID,
    schedule_id: uuid.UUID,
    body: PostScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> PostSchedule:
    await require_owned_project(project_id, db, jwt_user_id)

    result = await db.execute(
        select(PostSchedule).where(
            PostSchedule.id == schedule_id,
            PostSchedule.project_id == project_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post schedule not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)

    await db.flush()
    await db.refresh(schedule)
    return schedule


@router.delete(
    "/{project_id}/post-schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_post_schedule(
    project_id: uuid.UUID,
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> None:
    await require_owned_project(project_id, db, jwt_user_id)

    result = await db.execute(
        select(PostSchedule).where(
            PostSchedule.id == schedule_id,
            PostSchedule.project_id == project_id,
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post schedule not found")

    await db.delete(schedule)
    await db.flush()


# ---------------------------------------------------------------------------
# PostRecord endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/post-records",
    response_model=PostRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_post_record(
    project_id: uuid.UUID,
    body: PostRecordCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> PostRecord:
    await require_owned_project(project_id, db, jwt_user_id)

    # Verify draft belongs to this project and update its status to 'published'
    draft_result = await db.execute(
        select(Draft).where(Draft.id == body.draft_id, Draft.project_id == project_id)
    )
    draft = draft_result.scalar_one_or_none()
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found in this project",
        )

    # Transition the draft to published state
    draft.status = "published"
    await db.flush()

    record = PostRecord(
        draft_id=body.draft_id,
        project_id=project_id,
        platform=body.platform,
        posted_at=body.posted_at,
        post_url=body.post_url,
        notes=body.notes,
        post_type=body.post_type,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


@router.get("/{project_id}/post-records", response_model=List[PostRecordResponse])
async def list_post_records(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> List[PostRecord]:
    await require_owned_project(project_id, db, jwt_user_id)

    result = await db.execute(
        select(PostRecord)
        .where(PostRecord.project_id == project_id)
        .order_by(PostRecord.posted_at.desc())
    )
    return list(result.scalars().all())


@router.delete(
    "/{project_id}/post-records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_post_record(
    project_id: uuid.UUID,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> None:
    await require_owned_project(project_id, db, jwt_user_id)

    result = await db.execute(
        select(PostRecord).where(
            PostRecord.id == record_id,
            PostRecord.project_id == project_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post record not found")

    await db.delete(record)
    await db.flush()
