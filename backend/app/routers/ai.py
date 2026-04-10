import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, require_owned_project, verify_api_key
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


@router.post("/projects/{project_id}/generate", response_model=GenerateResponse)
async def generate_content(
    project_id: uuid.UUID,
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> GenerateResponse:
    """
    Generate a platform-specific content draft using the project's narrative,
    memory, and most recent sync data.
    """
    await require_owned_project(project_id, db, jwt_user_id)

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
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
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

    # Verify the caller owns every project in the list (JWT users only).
    if jwt_user_id:
        try:
            owner_uuid = uuid.UUID(jwt_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user id in token",
            )
        owned_rows = await db.execute(
            select(Project.id).where(
                Project.id.in_(body.project_ids),
                Project.user_id == owner_uuid,
            )
        )
        owned_ids = {row[0] for row in owned_rows.all()}
        missing = [pid for pid in body.project_ids if pid not in owned_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project(s) not found or not accessible: {missing}",
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
    user_id: Optional[str] = Depends(get_optional_user_id),
) -> DashboardSummaryResponse:
    """
    Return cross-project stats and recent activity for the dashboard.

    When JWT auth is used, results are scoped to the authenticated user's
    projects. API key auth (admin/scripts) sees everything.
    """
    # Resolve the user's project IDs for scoping (None = show all)
    user_project_ids: Optional[list] = None
    if user_id:
        pid_result = await db.execute(
            select(Project.id).where(Project.user_id == user_id)
        )
        user_project_ids = [row[0] for row in pid_result.all()]

    # Total counts
    if user_project_ids is not None:
        total_projects = len(user_project_ids)
        draft_count_result = await db.execute(
            select(func.count()).select_from(Draft).where(Draft.project_id.in_(user_project_ids))
        )
        total_drafts: int = draft_count_result.scalar_one()
        sync_count_result = await db.execute(
            select(func.count()).select_from(SyncRun).where(
                SyncRun.status == "completed",
                SyncRun.project_id.in_(user_project_ids),
            )
        )
        total_syncs: int = sync_count_result.scalar_one()
    else:
        project_count_result = await db.execute(select(func.count()).select_from(Project))
        total_projects = project_count_result.scalar_one()
        draft_count_result = await db.execute(select(func.count()).select_from(Draft))
        total_drafts = draft_count_result.scalar_one()
        sync_count_result = await db.execute(
            select(func.count()).select_from(SyncRun).where(SyncRun.status == "completed")
        )
        total_syncs = sync_count_result.scalar_one()

    # Recent activity: last 10 completed sync runs with project names
    recent_query = (
        select(SyncRun, Project.name)
        .join(Project, Project.id == SyncRun.project_id)
        .where(SyncRun.status == "completed")
        .order_by(SyncRun.completed_at.desc())
        .limit(10)
    )
    if user_project_ids is not None:
        recent_query = recent_query.where(SyncRun.project_id.in_(user_project_ids))
    recent_runs_result = await db.execute(recent_query)

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
    user_id: Optional[str] = Depends(get_optional_user_id),
) -> DashboardAnalyticsResponse:
    """Return 12 weeks of activity data for dashboard charts.

    When JWT auth is used, results are scoped to the authenticated user's
    projects. API key auth (admin/scripts) sees everything.
    """
    weeks_back = 12

    # Resolve project scoping
    user_project_ids: Optional[list] = None
    if user_id:
        pid_result = await db.execute(
            select(Project.id).where(Project.user_id == user_id)
        )
        user_project_ids = [row[0] for row in pid_result.all()]
        # Authenticated user has no projects → nothing to query; return empty chart.
        if not user_project_ids:
            return DashboardAnalyticsResponse(
                weeks=[
                    {
                        "week": (
                            datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
                        ).replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d"),
                        "commits": 0, "papers": 0, "drafts": 0, "memory": 0,
                    }
                    for _ in range(weeks_back)
                ],
                totals={"commits": 0, "papers": 0, "drafts": 0, "memory": 0},
            )

    # Build raw SQL queries with a parameterized project_id list. Using
    # ``bindparam(expanding=True)`` means the caller's UUID list is bound as
    # real SQL parameters rather than string-interpolated, eliminating any
    # future SQL-injection risk if the source of ``user_project_ids`` changes.
    scope_clause = "AND project_id IN :pids" if user_project_ids is not None else ""
    params = {"pids": user_project_ids} if user_project_ids is not None else {}

    def _stmt(sql: str):
        stmt = text(sql)
        if user_project_ids is not None:
            stmt = stmt.bindparams(bindparam("pids", expanding=True))
        return stmt

    # Commits per week
    commits_result = await db.execute(
        _stmt(f"""
            SELECT date_trunc('week', committed_at)::date AS week_start,
                   COUNT(*) AS cnt
            FROM github_commits
            WHERE committed_at >= now() - interval '12 weeks'
            {scope_clause}
            GROUP BY week_start
            ORDER BY week_start
        """),
        params,
    )

    # Papers per week (blog_posts tagged 'paper')
    papers_result = await db.execute(
        _stmt(f"""
            SELECT date_trunc('week', created_at)::date AS week_start,
                   COUNT(*) AS cnt
            FROM blog_posts
            WHERE created_at >= now() - interval '12 weeks'
              AND tags @> ARRAY['paper']::text[]
            {scope_clause}
            GROUP BY week_start
            ORDER BY week_start
        """),
        params,
    )

    # Drafts per week
    drafts_result = await db.execute(
        _stmt(f"""
            SELECT date_trunc('week', created_at)::date AS week_start,
                   COUNT(*) AS cnt
            FROM drafts
            WHERE created_at >= now() - interval '12 weeks'
            {scope_clause}
            GROUP BY week_start
            ORDER BY week_start
        """),
        params,
    )

    # Memory entries per week
    memory_result = await db.execute(
        _stmt(f"""
            SELECT date_trunc('week', created_at)::date AS week_start,
                   COUNT(*) AS cnt
            FROM memory_entries
            WHERE created_at >= now() - interval '12 weeks'
            {scope_clause}
            GROUP BY week_start
            ORDER BY week_start
        """),
        params,
    )

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
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> GenerateResponse:
    """
    Generate an evolution summary for a completed sync run and persist it
    on the SyncRun record.

    The sync run's owning project must belong to the caller; otherwise this
    endpoint would allow any authenticated user to enumerate and regenerate
    summaries for other users' projects by guessing sync_run UUIDs.
    """
    # Resolve sync_run → project, then enforce ownership.
    sr_result = await db.execute(
        select(SyncRun.project_id).where(SyncRun.id == body.sync_run_id)
    )
    sr_row = sr_result.one_or_none()
    if sr_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync run not found")
    await require_owned_project(sr_row[0], db, jwt_user_id)

    try:
        summary = await generate_evolution_summary(body.sync_run_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return GenerateResponse(
        content=summary,
        platform="evolution_summary",
        draft_id=None,
    )
