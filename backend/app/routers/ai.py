import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.draft import Draft
from app.models.project import Project
from app.models.sync import SyncRun
from app.schemas.ai import (
    DashboardAnalyticsResponse,
    DashboardSummaryResponse,
    GenerateRequest,
    GenerateResponse,
    PortfolioGenerateRequest,
    PortfolioGenerateResponse,
    SummaryRequest,
)
from app.services.ai_generation import (
    generate_draft,
    generate_evolution_summary,
    generate_portfolio_draft,
)

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


@router.post("/portfolio/generate", response_model=PortfolioGenerateResponse)
async def generate_portfolio(
    body: PortfolioGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PortfolioGenerateResponse:
    """
    Generate a combined social post covering multiple projects.
    The draft is saved under the first project in the list.
    """
    if len(body.project_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least 2 project_ids are required for a portfolio post.",
        )
    if len(body.project_ids) > 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At most 5 project_ids are allowed per portfolio post.",
        )

    try:
        content, draft_id, project_names = await generate_portfolio_draft(
            project_ids=body.project_ids,
            platform=body.platform,
            theme=body.theme,
            additional_context=body.additional_context,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return PortfolioGenerateResponse(
        content=content,
        platform=body.platform,
        draft_id=draft_id,
        projects_included=project_names,
    )


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> DashboardSummaryResponse:
    """
    Return cross-project stats and recent activity for the dashboard.
    """
    # Total counts
    project_count_result = await db.execute(select(func.count()).select_from(Project))
    total_projects: int = project_count_result.scalar_one()

    draft_count_result = await db.execute(select(func.count()).select_from(Draft))
    total_drafts: int = draft_count_result.scalar_one()

    sync_count_result = await db.execute(
        select(func.count()).select_from(SyncRun).where(SyncRun.status == "completed")
    )
    total_syncs: int = sync_count_result.scalar_one()

    # Recent activity: last 10 completed sync runs with project names
    recent_runs_result = await db.execute(
        select(SyncRun, Project.name)
        .join(Project, Project.id == SyncRun.project_id)
        .where(SyncRun.status == "completed")
        .order_by(SyncRun.completed_at.desc())
        .limit(10)
    )
    recent_activity = []
    for run, project_name in recent_runs_result.all():
        recent_activity.append({
            "type": "sync",
            "project_name": project_name,
            "project_id": str(run.project_id),
            "sync_run_id": str(run.id),
            "commits_fetched": run.commits_fetched,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        })

    return DashboardSummaryResponse(
        total_projects=total_projects,
        total_drafts=total_drafts,
        total_syncs=total_syncs,
        recent_activity=recent_activity,
    )


@router.get("/dashboard/analytics", response_model=DashboardAnalyticsResponse)
async def dashboard_analytics(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> DashboardAnalyticsResponse:
    """Return 12 weeks of activity data for dashboard charts."""
    weeks_back = 12

    # Commits per week
    commits_result = await db.execute(text("""
        SELECT date_trunc('week', committed_at)::date AS week_start,
               COUNT(*) AS cnt
        FROM github_commits
        WHERE committed_at >= now() - interval '12 weeks'
        GROUP BY week_start
        ORDER BY week_start
    """))

    # Papers per week (blog_posts tagged 'paper')
    papers_result = await db.execute(text("""
        SELECT date_trunc('week', created_at)::date AS week_start,
               COUNT(*) AS cnt
        FROM blog_posts
        WHERE created_at >= now() - interval '12 weeks'
          AND tags @> ARRAY['paper']::text[]
        GROUP BY week_start
        ORDER BY week_start
    """))

    # Drafts per week
    drafts_result = await db.execute(text("""
        SELECT date_trunc('week', created_at)::date AS week_start,
               COUNT(*) AS cnt
        FROM drafts
        WHERE created_at >= now() - interval '12 weeks'
        GROUP BY week_start
        ORDER BY week_start
    """))

    # Memory entries per week
    memory_result = await db.execute(text("""
        SELECT date_trunc('week', created_at)::date AS week_start,
               COUNT(*) AS cnt
        FROM memory_entries
        WHERE created_at >= now() - interval '12 weeks'
        GROUP BY week_start
        ORDER BY week_start
    """))

    # Build lookup dicts: ISO date string -> count
    commits_map = {str(row[0]): row[1] for row in commits_result.all()}
    papers_map = {str(row[0]): row[1] for row in papers_result.all()}
    drafts_map = {str(row[0]): row[1] for row in drafts_result.all()}
    memory_map = {str(row[0]): row[1] for row in memory_result.all()}

    # Find the Monday of the current week (UTC) and walk back 12 weeks,
    # filling zeros for any week with no activity so the chart always has 12 points.
    now = datetime.utcnow()
    current_monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    weeks = []
    totals: dict = {"commits": 0, "papers": 0, "drafts": 0, "memory": 0}

    for i in range(weeks_back - 1, -1, -1):
        week_start = current_monday - timedelta(weeks=i)
        week_str = week_start.strftime("%Y-%m-%d")

        c = commits_map.get(week_str, 0)
        p = papers_map.get(week_str, 0)
        d = drafts_map.get(week_str, 0)
        m = memory_map.get(week_str, 0)

        weeks.append({"week": week_str, "commits": c, "papers": p, "drafts": d, "memory": m})
        totals["commits"] += c
        totals["papers"] += p
        totals["drafts"] += d
        totals["memory"] += m

    return DashboardAnalyticsResponse(weeks=weeks, totals=totals)


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
