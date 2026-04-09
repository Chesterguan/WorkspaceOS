import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, verify_api_key
from app.models.draft import Draft
from app.models.project import Project
from app.models.sync import SyncRun
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectStatsItem,
    ProjectStatsResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


async def _resolve_user_id(user_id: Optional[uuid.UUID], db: AsyncSession) -> uuid.UUID:
    """Return the provided user_id, or fall back to the first user in the DB."""
    if user_id is not None:
        return user_id
    from app.models.user import User
    result = await db.execute(select(User).order_by(User.created_at.asc()).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No users exist in the database. Provide a user_id or run the seed script.",
        )
    return user.id


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> Project:
    # Prefer explicit body.user_id, then JWT user, then DB fallback
    effective_user_id = body.user_id
    if effective_user_id is None and jwt_user_id:
        effective_user_id = uuid.UUID(jwt_user_id)
    resolved_user_id = await _resolve_user_id(effective_user_id, db)

    # Enforce unique slug per user
    existing = await db.execute(
        select(Project).where(
            Project.user_id == resolved_user_id,
            Project.slug == body.slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A project with slug '{body.slug}' already exists for this user.",
        )

    data = body.model_dump()
    data['user_id'] = resolved_user_id
    project = Project(**data)
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


@router.get("/stats", response_model=ProjectStatsResponse)
async def get_projects_stats(
    user_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> ProjectStatsResponse:
    """
    Return draft counts and last sync timestamps for all projects in one query.
    Used by the project cards on the dashboard to show activity indicators.
    """
    # Draft counts per project (root drafts only, no version children)
    draft_query = (
        select(Draft.project_id, func.count(Draft.id).label("draft_count"))
        .where(Draft.parent_draft_id.is_(None))
        .group_by(Draft.project_id)
    )
    draft_result = await db.execute(draft_query)
    draft_counts: dict = {row.project_id: row.draft_count for row in draft_result.all()}

    # Last completed sync run per project
    sync_query = (
        select(SyncRun.project_id, func.max(SyncRun.completed_at).label("last_sync_at"))
        .where(SyncRun.status == "completed")
        .group_by(SyncRun.project_id)
    )
    sync_result = await db.execute(sync_query)
    last_syncs: dict = {row.project_id: row.last_sync_at for row in sync_result.all()}

    # All project IDs in scope
    proj_query = select(Project.id)
    if user_id:
        proj_query = proj_query.where(Project.user_id == user_id)
    elif jwt_user_id:
        proj_query = proj_query.where(Project.user_id == uuid.UUID(jwt_user_id))
    proj_result = await db.execute(proj_query)
    project_ids = [row[0] for row in proj_result.all()]

    stats = [
        ProjectStatsItem(
            project_id=pid,
            draft_count=draft_counts.get(pid, 0),
            last_sync_at=last_syncs.get(pid),
        )
        for pid in project_ids
    ]
    return ProjectStatsResponse(stats=stats)


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    user_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> List[Project]:
    query = select(Project).order_by(Project.created_at.desc())
    if user_id:
        # Explicit user_id query param takes priority
        query = query.where(Project.user_id == user_id)
    elif jwt_user_id:
        # JWT auth: auto-scope to the authenticated user's projects
        query = query.where(Project.user_id == uuid.UUID(jwt_user_id))
    # API key auth with no user_id param: return all (admin/script mode)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    user_id: Optional[str] = Depends(get_optional_user_id),
) -> Project:
    query = select(Project).where(Project.id == project_id)
    if user_id:
        query = query.where(Project.user_id == uuid.UUID(user_id))
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    user_id: Optional[str] = Depends(get_optional_user_id),
) -> Project:
    query = select(Project).where(Project.id == project_id)
    if user_id:
        query = query.where(Project.user_id == uuid.UUID(user_id))
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    user_id: Optional[str] = Depends(get_optional_user_id),
) -> None:
    query = select(Project).where(Project.id == project_id)
    if user_id:
        query = query.where(Project.user_id == uuid.UUID(user_id))
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await db.delete(project)
    await db.flush()
