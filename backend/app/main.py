import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Make app.* loggers visible at INFO level. Uvicorn only configures its own
# loggers and leaves the root logger at WARNING with no handlers; add a
# StreamHandler so app.services.* INFO messages reach stdout.
_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
if not _app_logger.handlers:
    _app_logger.addHandler(logging.StreamHandler())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

# Global rate limiter — 120 req/min per IP prevents runaway loops while
# still being generous for legitimate use (AI endpoints take 5-30s each).
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

from app.services import domain_config
from app.routers import ai, auth, drafts, files as files_router, memory, narratives, projects, sync
from app.routers import agentic, blog, chat, github, linkedin, posting, publish, workspace
from app.routers import paper, research, settings as settings_router, worklog as worklog_router
from app.routers import activity as activity_router
from app.routers import google_oauth as google_oauth_router
from app.routers import microsoft_oauth as microsoft_oauth_router
from app.routers import skills as skills_router
from app.routers import knowledge as knowledge_router
from app.routers import config as config_router
from app.routers.paper import portfolio_paper_router
from app.routers.publish import blog_publish_router
from app.routers.chat import starters_router as chat_starters_router
from app.routers.research import starters_router as research_starters_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Daily auto-sync: syncs all projects once per day at off-peak hours
# ---------------------------------------------------------------------------
SYNC_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours
SYNC_INITIAL_DELAY_SECONDS = 60  # wait 60s after startup before first check


async def _daily_backup_loop() -> None:
    """Background loop that runs pg_dump daily."""
    import subprocess

    await asyncio.sleep(120)  # wait 2 min after startup
    logger.info("Backup scheduler started")

    while True:
        try:
            result = subprocess.run(
                ["bash", "/app/scripts/backup.sh"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                logger.info("Daily backup completed: %s", result.stdout.strip().split("\n")[-1])
            else:
                logger.warning("Backup failed: %s", result.stderr[:200])
        except Exception:
            logger.exception("Backup scheduler error")

        await asyncio.sleep(24 * 60 * 60)  # 24 hours


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
    """Startup/shutdown lifecycle: validate config, then start background tasks."""
    domain_config.load_on_startup()

    from app.config import settings
    if not settings.validate_startup():
        logger.critical("Aborting startup due to config validation failure")
        raise SystemExit(1)

    # Load DB-stored API keys (overlay onto runtime settings)
    from app.services.settings_service import load_db_keys_into_settings
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        loaded = await load_db_keys_into_settings(db)
        if loaded:
            logger.info("Loaded %d API key(s) from database", loaded)

    sync_task = asyncio.create_task(_daily_sync_loop())
    logger.info("Background auto-sync task scheduled")
    backup_task = asyncio.create_task(_daily_backup_loop())
    logger.info("Background backup task scheduled")

    # Phase 2 capability plugins — ingest sources declared by extensions
    from app.capabilities import ingest_runner
    ingest_runner.start_all()

    # Reconcile any DataMaster jobs left 'running' by a previous process crash
    from app.capabilities.datamaster_runner import spawn_reconcile
    spawn_reconcile()

    yield
    sync_task.cancel()
    backup_task.cancel()
    await ingest_runner.stop_all()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    try:
        await backup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="WorkspaceOS",
    description="Backend API for WorkspaceOS — configurable single-surface workbench framework.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Allow all origins in development. Tighten this in production by replacing
# allow_origins with a specific list of frontend URLs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Changed from True — incompatible with allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_slow_requests(request, call_next):
    """Log any request that takes longer than 5 seconds."""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    if duration > 5.0:
        logger.warning(
            "SLOW REQUEST: %s %s took %.1fs",
            request.method,
            request.url.path,
            duration,
        )
    return response

API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(narratives.router, prefix=API_PREFIX)
app.include_router(sync.router, prefix=API_PREFIX)
app.include_router(drafts.router, prefix=API_PREFIX)
app.include_router(ai.router, prefix=API_PREFIX)
app.include_router(memory.router, prefix=API_PREFIX)
app.include_router(memory.global_router, prefix=API_PREFIX)
app.include_router(files_router.router, prefix=API_PREFIX)
app.include_router(github.router, prefix=API_PREFIX)
app.include_router(posting.router, prefix=API_PREFIX)
app.include_router(blog.router, prefix=API_PREFIX)
app.include_router(agentic.router, prefix=API_PREFIX)
app.include_router(workspace.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(chat_starters_router, prefix=API_PREFIX)
app.include_router(publish.router, prefix=API_PREFIX)
app.include_router(blog_publish_router, prefix=API_PREFIX)
app.include_router(linkedin.router, prefix=API_PREFIX)
app.include_router(research.router, prefix=API_PREFIX)
app.include_router(research_starters_router, prefix=API_PREFIX)
app.include_router(settings_router.router, prefix=API_PREFIX)
app.include_router(paper.router, prefix=API_PREFIX)
app.include_router(portfolio_paper_router, prefix=API_PREFIX)
app.include_router(worklog_router.router, prefix=API_PREFIX)
app.include_router(activity_router.router, prefix=API_PREFIX)
app.include_router(google_oauth_router.router, prefix=API_PREFIX)
app.include_router(microsoft_oauth_router.router, prefix=API_PREFIX)
app.include_router(skills_router.router, prefix=API_PREFIX)
app.include_router(knowledge_router.router, prefix=API_PREFIX)
app.include_router(config_router.router, prefix=API_PREFIX)
from app.routers import events as events_router
app.include_router(events_router.router, prefix=API_PREFIX)
from app.routers import capabilities as capabilities_router
app.include_router(capabilities_router.router, prefix=API_PREFIX)
from app.routers import feedback as feedback_router
app.include_router(feedback_router.router, prefix=API_PREFIX)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Check API and database health."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        logger.warning("Health check DB probe failed: %s", exc)
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": app.version,
        "database": db_status,
    }
