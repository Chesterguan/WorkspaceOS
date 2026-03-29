"""
Extraction service: reads commits and releases from a sync run, calls the AI for
structured theme extraction, stores results on sync_runs.themes_extracted, and
creates memory entries for each theme.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import GitHubCommit, GitHubRelease, SyncRun
from app.services.ai_client import get_local_client
from app.services.memory_service import add_entry
from app.utils.prompts import get_template


async def extract_sync_themes(sync_run_id: uuid.UUID, db: AsyncSession) -> None:
    """
    Extract structured themes from a sync run's commits and releases.

    Workflow:
    1. Load commits and releases for the sync run.
    2. Call the AI using the extraction template to get a JSON-friendly theme list.
    3. Parse the response into a list of theme strings.
    4. Persist the extracted themes on the SyncRun record.
    5. Create a memory entry for each theme so it is searchable later.
    """
    sync_result = await db.execute(select(SyncRun).where(SyncRun.id == sync_run_id))
    sync_run = sync_result.scalar_one_or_none()
    if sync_run is None:
        raise ValueError(f"SyncRun {sync_run_id} not found")

    # Load associated commits
    commit_result = await db.execute(
        select(GitHubCommit)
        .where(GitHubCommit.sync_run_id == sync_run_id)
        .order_by(GitHubCommit.committed_at.desc())
    )
    commits: List[GitHubCommit] = list(commit_result.scalars().all())

    # Load associated releases
    release_result = await db.execute(
        select(GitHubRelease).where(GitHubRelease.sync_run_id == sync_run_id)
    )
    releases: List[GitHubRelease] = list(release_result.scalars().all())

    commit_lines = []
    for c in commits:
        first_line = c.message.splitlines()[0] if c.message else "(no message)"
        commit_lines.append(f"- {c.sha[:7]}: {first_line}")

    release_lines = []
    for r in releases:
        release_lines.append(f"- {r.tag_name}: {r.release_name or 'no name'}")
        if r.body:
            release_lines.append(f"  {r.body[:200]}")

    ctx = {
        "commit_list": "\n".join(commit_lines) or "No commits.",
        "release_list": "\n".join(release_lines) or "No releases.",
        "commit_count": len(commits),
        "release_count": len(releases),
    }

    template_fn = get_template("extraction")
    system, user = template_fn(ctx)

    ai = get_local_client()
    raw_response = await ai.complete(system, user)

    # Parse the response: expect one theme per line, strip bullets/numbering
    themes = []
    for line in raw_response.splitlines():
        line = line.strip().lstrip("-•*0123456789.)").strip()
        if line:
            themes.append(line)

    # Store structured themes on the sync run
    sync_run.themes_extracted = {"themes": themes, "raw_response": raw_response}
    sync_run.extraction_run_at = datetime.now(timezone.utc)
    await db.flush()

    # Create a searchable memory entry for each extracted theme
    for theme in themes:
        try:
            await add_entry(
                project_id=sync_run.project_id,
                entry_type="commit_summary",
                content=theme,
                source_ref=str(sync_run_id),
                db=db,
            )
        except Exception:
            # Non-fatal: embedding failures should not break the extraction
            logger.exception(
                "Failed to create memory entry for theme (sync_run=%s): %r",
                sync_run_id,
                theme,
            )
