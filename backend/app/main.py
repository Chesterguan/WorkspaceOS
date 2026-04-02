import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ai, drafts, memory, narratives, projects, sync
from app.routers import agentic, blog, chat, github, linkedin, posting, publish, workspace
from app.routers import paper, research
from app.routers.paper import portfolio_paper_router
from app.routers.chat import starters_router as chat_starters_router
from app.routers.research import starters_router as research_starters_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Daily auto-sync: syncs all projects once per day at off-peak hours
# ---------------------------------------------------------------------------
SYNC_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours
SYNC_INITIAL_DELAY_SECONDS = 60  # wait 60s after startup before first check


async def _daily_sync_loop() -> None:
    """Background loop that syncs all projects once per day.

    Runs each project sequentially with a small gap between them to avoid
    hammering the GitHub API. Errors on one project don't stop the others.
    """
    from app.database import AsyncSessionLocal
    from app.models.project import Project
    from app.services.github_sync import run_sync, _last_sync_time
    from sqlalchemy import select

    await asyncio.sleep(SYNC_INITIAL_DELAY_SECONDS)
    logger.info("Auto-sync scheduler started (interval=%ds)", SYNC_INTERVAL_SECONDS)

    min_gap_hours = 23  # skip project if synced within this many hours

    while True:
        try:
            logger.info("Auto-sync: starting daily sync for all projects")
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Project).where(Project.github_repo.isnot(None))
                )
                all_projects = list(result.scalars().all())

            synced = 0
            skipped = 0
            for proj in all_projects:
                try:
                    # Skip if synced recently (prevents duplicate syncs after restart)
                    async with AsyncSessionLocal() as db:
                        from datetime import datetime, timezone
                        last = await _last_sync_time(proj.id, db)
                        if last:
                            hours_ago = (datetime.now(timezone.utc) - last).total_seconds() / 3600
                            if hours_ago < min_gap_hours:
                                skipped += 1
                                continue

                    async with AsyncSessionLocal() as db:
                        sync_run = await asyncio.wait_for(
                            run_sync(proj.id, db), timeout=300
                        )
                        logger.info(
                            "Auto-sync: %s -> %s (commits=%s)",
                            proj.name,
                            sync_run.status,
                            sync_run.commits_fetched,
                        )
                        synced += 1
                except asyncio.TimeoutError:
                    logger.error("Auto-sync: timeout (300s) for project %s", proj.name)
                except Exception:
                    logger.exception("Auto-sync: failed for project %s", proj.name)
                # Small delay between projects to be kind to GitHub API
                await asyncio.sleep(2)

            logger.info(
                "Auto-sync: completed %d/%d projects (%d skipped, synced recently)",
                synced, len(all_projects), skipped,
            )
        except Exception:
            logger.exception("Auto-sync: loop iteration failed")

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown lifecycle for background tasks."""
    sync_task = asyncio.create_task(_daily_sync_loop())
    logger.info("Background auto-sync task scheduled")
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="ProjectScribe",
    description="Backend API for ProjectScribe — AI co-founder for project management, content, and research.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow all origins in development. Tighten this in production by replacing
# allow_origins with a specific list of frontend URLs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Changed from True — incompatible with allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(narratives.router, prefix=API_PREFIX)
app.include_router(sync.router, prefix=API_PREFIX)
app.include_router(drafts.router, prefix=API_PREFIX)
app.include_router(ai.router, prefix=API_PREFIX)
app.include_router(memory.router, prefix=API_PREFIX)
app.include_router(memory.global_router, prefix=API_PREFIX)
app.include_router(github.router, prefix=API_PREFIX)
app.include_router(posting.router, prefix=API_PREFIX)
app.include_router(blog.router, prefix=API_PREFIX)
app.include_router(agentic.router, prefix=API_PREFIX)
app.include_router(workspace.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(chat_starters_router, prefix=API_PREFIX)
app.include_router(publish.router, prefix=API_PREFIX)
app.include_router(linkedin.router, prefix=API_PREFIX)
app.include_router(research.router, prefix=API_PREFIX)
app.include_router(research_starters_router, prefix=API_PREFIX)
app.include_router(paper.router, prefix=API_PREFIX)
app.include_router(portfolio_paper_router, prefix=API_PREFIX)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok", "version": app.version}
