import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.project import Project
from app.models.sync import GitHubCommit, GitHubRelease, SyncRun
from app.schemas.sync import GitHubCommitResponse, GitHubReleaseResponse, SyncRunResponse
from app.services.github_sync import run_sync

router = APIRouter(prefix="/projects/{project_id}/sync", tags=["sync"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=SyncRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> SyncRun:
    """
    Trigger a GitHub sync for a project.  Runs synchronously within the request
    so the caller gets immediate results. For large repos consider moving to a
    background task queue.
    """
    await _require_project(project_id, db)
    sync_run = await run_sync(project_id, db)
    return sync_run


@router.get("", response_model=list[SyncRunResponse])
async def list_sync_runs(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> list[SyncRun]:
    await _require_project(project_id, db)
    result = await db.execute(
        select(SyncRun)
        .where(SyncRun.project_id == project_id)
        .order_by(SyncRun.triggered_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


@router.get("/{sync_run_id}", response_model=SyncRunResponse)
async def get_sync_run(
    project_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> SyncRun:
    result = await db.execute(
        select(SyncRun).where(
            SyncRun.id == sync_run_id,
            SyncRun.project_id == project_id,
        )
    )
    sync_run = result.scalar_one_or_none()
    if sync_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync run not found")
    return sync_run


@router.get("/{sync_run_id}/commits", response_model=list[GitHubCommitResponse])
async def list_sync_commits(
    project_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> list[GitHubCommit]:
    result = await db.execute(
        select(GitHubCommit)
        .where(
            GitHubCommit.sync_run_id == sync_run_id,
            GitHubCommit.project_id == project_id,
        )
        .order_by(GitHubCommit.committed_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{sync_run_id}/releases", response_model=list[GitHubReleaseResponse])
async def list_sync_releases(
    project_id: uuid.UUID,
    sync_run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> list[GitHubRelease]:
    result = await db.execute(
        select(GitHubRelease)
        .where(
            GitHubRelease.sync_run_id == sync_run_id,
            GitHubRelease.project_id == project_id,
        )
        .order_by(GitHubRelease.published_at.desc())
    )
    return list(result.scalars().all())
