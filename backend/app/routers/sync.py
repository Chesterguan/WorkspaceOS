import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.memory import MemoryEntry
from app.models.project import Project
from app.models.sync import GitHubCommit, GitHubRelease, SyncRun
from app.schemas.sync import GitHubCommitResponse, GitHubReleaseResponse, SyncRunResponse
from app.services.github_sync import run_sync


# ---------------------------------------------------------------------------
# Timeline response schemas
# ---------------------------------------------------------------------------
class TimelineEvent(BaseModel):
    model_config = {"from_attributes": True}

    date: str  # ISO date string (YYYY-MM-DD)
    type: str  # "commit", "release", "milestone", "insight", "summary"
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    source_ref: Optional[str] = None


class TimelineMonth(BaseModel):
    month: str  # "2026-03"
    events: List[TimelineEvent]


class TimelineResponse(BaseModel):
    project_id: str
    project_name: str
    total_events: int
    months: List[TimelineMonth]

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


# ---------------------------------------------------------------------------
# Timeline: chronological view of project milestones and key events
# NOTE: Must be registered BEFORE /{sync_run_id} to avoid path conflict.
# ---------------------------------------------------------------------------
@router.get("/timeline", response_model=TimelineResponse)
async def get_project_timeline(
    project_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Build a chronological timeline of project milestones, releases,
    key commits, and AI-extracted insights. Grouped by month."""
    project = await _require_project(project_id, db)

    events: List[TimelineEvent] = []

    # 1. Releases — most important milestones
    release_result = await db.execute(
        select(GitHubRelease)
        .where(GitHubRelease.project_id == project_id)
        .order_by(GitHubRelease.published_at.desc())
        .limit(limit)
    )
    for r in release_result.scalars().all():
        if r.published_at:
            events.append(TimelineEvent(
                date=r.published_at.strftime("%Y-%m-%d"),
                type="release",
                title=f"Release {r.tag_name}" + (f": {r.release_name}" if r.release_name else ""),
                description=(r.body[:300] + "..." if r.body and len(r.body) > 300 else r.body),
                url=r.url,
                source_ref=r.tag_name,
            ))

    # 2. Commits
    commit_result = await db.execute(
        select(GitHubCommit)
        .where(GitHubCommit.project_id == project_id)
        .order_by(GitHubCommit.committed_at.desc())
        .limit(limit)
    )
    for c in commit_result.scalars().all():
        if c.committed_at:
            first_line = c.message.splitlines()[0] if c.message else "(no message)"
            events.append(TimelineEvent(
                date=c.committed_at.strftime("%Y-%m-%d"),
                type="commit",
                title=first_line[:120],
                description=None,
                url=c.url,
                source_ref=c.sha[:7],
            ))

    # 3. AI-extracted insights from memory (commit_summary, consolidated_summary)
    insight_types = ("commit_summary", "consolidated_summary")
    memory_result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type.in_(insight_types),
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
    )
    for m in memory_result.scalars().all():
        event_type = "summary" if m.entry_type == "consolidated_summary" else "insight"
        events.append(TimelineEvent(
            date=m.created_at.strftime("%Y-%m-%d"),
            type=event_type,
            title=m.content[:150] + ("..." if len(m.content) > 150 else ""),
            description=None,
            source_ref=m.source_ref,
        ))

    # Sort all events by date descending
    events.sort(key=lambda e: e.date, reverse=True)

    # Group by month
    months_dict: Dict[str, List[TimelineEvent]] = defaultdict(list)
    for event in events:
        month_key = event.date[:7]  # "2026-03"
        months_dict[month_key].append(event)

    months = [
        TimelineMonth(month=k, events=v)
        for k, v in sorted(months_dict.items(), reverse=True)
    ]

    return {
        "project_id": str(project_id),
        "project_name": project.name,
        "total_events": len(events),
        "months": months,
    }


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
