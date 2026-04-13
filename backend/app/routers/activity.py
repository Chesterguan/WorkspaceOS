"""Project activity feed — one endpoint, owner-scoped, cursor-paginated."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_db,
    get_optional_user_id,
    require_owned_project,
    verify_api_key,
)
from app.schemas.activity import ActivityFeedResponse
from app.services.activity_service import list_events

router = APIRouter(prefix="/projects/{project_id}/activity", tags=["activity"])


@router.get("", response_model=ActivityFeedResponse)
async def get_activity_feed(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(
        None,
        description="ISO timestamp from the previous page's `next_cursor`; "
                    "events strictly older than this are returned.",
    ),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> ActivityFeedResponse:
    """
    Return the newest-first activity events for a project. Scoped by
    `require_owned_project` so JWT callers only see their own projects'
    feeds; API-key callers see everything (admin mode).
    """
    await require_owned_project(project_id, db, jwt_user_id)
    payload = await list_events(db, project_id, limit=limit, cursor=cursor)
    return ActivityFeedResponse(**payload)
