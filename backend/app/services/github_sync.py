"""
GitHub sync service: pulls commits, releases, and README for a project and
stores them in the database. Designed to be triggered by the /sync endpoint.

After a successful sync, extract_sync_themes is scheduled as a fire-and-forget
background task so callers receive the SyncRun response without waiting for AI.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.narrative import Narrative

logger = logging.getLogger(__name__)
from app.models.project import Project
from app.models.sync import GitHubCommit, GitHubRelease, SyncRun


def _github_headers() -> Dict[str, str]:
    """Build standard GitHub API request headers."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def _fetch_commits(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    since: Optional[datetime],
    per_page: int,
) -> List[dict]:
    """Fetch up to `per_page` commits from the GitHub API."""
    params: Dict[str, Union[str, int]] = {"per_page": per_page}
    if since:
        params["since"] = since.isoformat()

    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    response = await client.get(url, params=params, headers=_github_headers())
    response.raise_for_status()
    return response.json()


async def _fetch_releases(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
) -> List[dict]:
    """Fetch the latest 30 releases from the GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    response = await client.get(url, params={"per_page": 30}, headers=_github_headers())
    response.raise_for_status()
    return response.json()


async def _fetch_readme(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
) -> Optional[str]:
    """Return the decoded README content, or None if unavailable."""
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {**_github_headers(), "Accept": "application/vnd.github.raw+json"}
    response = await client.get(url, headers=headers)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


async def _last_sync_time(project_id: uuid.UUID, db: AsyncSession) -> Optional[datetime]:
    """Return the completed_at timestamp of the most recent successful sync."""
    result = await db.execute(
        select(SyncRun.completed_at)
        .where(SyncRun.project_id == project_id, SyncRun.status == "completed")
        .order_by(SyncRun.completed_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def run_sync(project_id: uuid.UUID, db: AsyncSession) -> SyncRun:
    """
    Main entry point. Creates a SyncRun record, fetches GitHub data, stores
    commits and releases (idempotent via ON CONFLICT DO NOTHING), and marks
    the run completed or failed.
    """
    # Load the project to get repo info
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    if not project.github_repo:
        raise ValueError(f"Project {project.name} has no GitHub repo configured")

    # Create the sync run record immediately so callers can track it
    sync_run = SyncRun(project_id=project_id, status="running")
    db.add(sync_run)
    await db.flush()  # Ensure sync_run.id is assigned

    raw_payload: dict = {}

    try:
        owner, repo = project.github_repo.split("/", 1)
    except ValueError:
        sync_run.status = "failed"
        sync_run.error_message = f"Invalid github_repo format: '{project.github_repo}'. Expected 'owner/repo'."
        sync_run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return sync_run

    since = await _last_sync_time(project_id, db)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # --- Commits ---
            raw_commits = await _fetch_commits(
                client, owner, repo, since, settings.max_commits_per_sync
            )
            raw_payload["commits"] = raw_commits

            new_commits: List[GitHubCommit] = []
            for c in raw_commits:
                commit_detail = c.get("commit", {})
                author_detail = commit_detail.get("author", {})
                committed_str = author_detail.get("date")
                committed_at = (
                    datetime.fromisoformat(committed_str.replace("Z", "+00:00"))
                    if committed_str
                    else None
                )
                new_commits.append(
                    GitHubCommit(
                        project_id=project_id,
                        sync_run_id=sync_run.id,
                        sha=c.get("sha", ""),
                        message=commit_detail.get("message", ""),
                        author_name=author_detail.get("name"),
                        committed_at=committed_at,
                        url=c.get("html_url"),
                    )
                )

            # Bulk insert; skip duplicates via ON CONFLICT DO NOTHING
            if new_commits:
                stmt = pg_insert(GitHubCommit).values(
                    [
                        {
                            "id": uuid.uuid4(),
                            "project_id": nc.project_id,
                            "sync_run_id": nc.sync_run_id,
                            "sha": nc.sha,
                            "message": nc.message,
                            "author_name": nc.author_name,
                            "committed_at": nc.committed_at,
                            "url": nc.url,
                        }
                        for nc in new_commits
                    ]
                ).on_conflict_do_nothing(constraint="uq_github_commits_project_sha")
                await db.execute(stmt)

            # --- Releases ---
            raw_releases = await _fetch_releases(client, owner, repo)
            raw_payload["releases"] = raw_releases

            new_releases: List[dict] = []
            for r in raw_releases:
                published_str = r.get("published_at")
                published_at = (
                    datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    if published_str
                    else None
                )
                new_releases.append(
                    {
                        "id": uuid.uuid4(),
                        "project_id": project_id,
                        "sync_run_id": sync_run.id,
                        "tag_name": r.get("tag_name", ""),
                        "release_name": r.get("name"),
                        "body": r.get("body"),
                        "published_at": published_at,
                        "url": r.get("html_url"),
                    }
                )

            if new_releases:
                stmt = pg_insert(GitHubRelease).values(new_releases).on_conflict_do_nothing(
                    constraint="uq_github_releases_project_tag"
                )
                await db.execute(stmt)

            # --- README ---
            readme_content = await _fetch_readme(client, owner, repo)
            readme_changed = readme_content is not None
            # Store full README in raw_payload for audit/debug purposes
            raw_payload["readme"] = readme_content or ""

        # Mark success
        sync_run.status = "completed"
        sync_run.completed_at = datetime.now(timezone.utc)
        sync_run.commits_fetched = len(new_commits)
        sync_run.releases_fetched = len(new_releases)
        sync_run.readme_changed = readme_changed
        sync_run.raw_payload = raw_payload

        # Fix 1: Store README as a memory entry for use in AI generation
        if readme_content:
            await _store_readme_memory(project_id, readme_content, sync_run.id, db)

        # Fix 2: Store release bodies as memory entries
        if new_releases:
            await _store_release_memories(project_id, new_releases, db)

        # Fix 3: Auto-populate narrative on first sync if all fields are empty
        await _maybe_populate_narrative(project_id, project, readme_content, db)

    except Exception as exc:
        sync_run.status = "failed"
        sync_run.error_message = str(exc)
        sync_run.completed_at = datetime.now(timezone.utc)
        sync_run.raw_payload = raw_payload

    await db.flush()

    # Commit NOW so background tasks (which open their own sessions) can see the data.
    # Without this, the request-scoped commit in get_db happens after response is sent,
    # causing a race where background tasks can't find the SyncRun.
    await db.commit()

    # Fire-and-forget theme extraction after a successful sync.
    if sync_run.status == "completed":
        _schedule_extraction(sync_run.id)
        _schedule_evolution_summary(sync_run.id)

    return sync_run


async def _store_readme_memory(
    project_id: uuid.UUID,
    readme_content: str,
    sync_run_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    Persist README content as a memory entry so AI generation can read it.
    Embedding is attempted but failure is non-fatal (handled inside add_entry).
    """
    from app.services.memory_service import add_entry
    try:
        await add_entry(
            project_id=project_id,
            entry_type="readme_content",
            content=readme_content,
            source_ref="sync:" + str(sync_run_id),
            db=db,
        )
    except Exception:
        logger.exception(
            "Failed to store README memory entry for project=%s sync_run=%s",
            project_id,
            sync_run_id,
        )


async def _store_release_memories(
    project_id: uuid.UUID,
    releases: List[dict],
    db: AsyncSession,
) -> None:
    """
    Create a memory entry for each release that has a body, keyed by tag name.
    Silently skips releases without a body — tag-only entries add little value.
    """
    from app.services.memory_service import add_entry
    for release in releases:
        tag_name = release.get("tag_name", "")
        body = release.get("body") or ""
        if not body.strip():
            continue
        content = f"{tag_name}: {body}"
        try:
            await add_entry(
                project_id=project_id,
                entry_type="release_note",
                content=content,
                source_ref=tag_name,
                db=db,
            )
        except Exception:
            logger.exception(
                "Failed to store release memory entry for project=%s tag=%s",
                project_id,
                tag_name,
            )


async def _maybe_populate_narrative(
    project_id: uuid.UUID,
    project: "Project",
    readme_content: Optional[str],
    db: AsyncSession,
) -> None:
    """
    Auto-populate narrative fields on the first sync if they are all empty.

    This is a plain text extraction — no AI call — so it works in full privacy
    mode (e.g. Ollama or no API key configured).
    """
    result = await db.execute(
        select(Narrative).where(Narrative.project_id == project_id)
    )
    narrative = result.scalar_one_or_none()

    # Only fill in fields if they are all empty; never overwrite existing data
    if narrative and any([
        narrative.one_liner,
        narrative.target_audience,
        narrative.origin_story,
    ]):
        return

    if narrative is None:
        narrative = Narrative(project_id=project_id, faq=[])
        db.add(narrative)

    # origin_story: use the GitHub repo description stored on the Project
    if not narrative.origin_story and getattr(project, "description", None):
        narrative.origin_story = project.description

    # one_liner: first non-empty paragraph from README, trimmed to one sentence
    if not narrative.one_liner and readme_content:
        one_liner = _extract_one_liner(readme_content)
        if one_liner:
            narrative.one_liner = one_liner

    # target_audience: sensible default so prompts don't show "N/A"
    if not narrative.target_audience:
        narrative.target_audience = "Developers"

    await db.flush()


def _extract_one_liner(readme_content: str) -> Optional[str]:
    """
    Extract a short description from README text.

    Strategy:
    1. Skip any leading heading lines (lines starting with #).
    2. Return the first non-empty paragraph (text up to a blank line).
    3. Trim to the first sentence (up to the first period, ! or ?).
    4. Cap at 200 characters.
    """
    lines = readme_content.splitlines()
    # Skip leading headings and blank lines
    content_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # If we already collected content lines, stop
            if content_lines:
                break
            continue  # skip leading headings
        if not stripped and not content_lines:
            continue  # skip leading blank lines
        if not stripped and content_lines:
            break  # blank line ends the first paragraph
        content_lines.append(stripped)

    if not content_lines:
        return None

    paragraph = " ".join(content_lines)

    # Trim to first sentence
    for i, char in enumerate(paragraph):
        if char in ".!?" and i > 10:
            return paragraph[: i + 1].strip()[:200]

    # No sentence terminator found — return up to 200 chars
    return paragraph[:200].strip() or None


def _schedule_extraction(sync_run_id: uuid.UUID) -> None:
    """
    Schedule extract_sync_themes as a background asyncio task.
    A fresh DB session is opened inside the task so it is not affected by
    the request-scoped session being closed after the response is sent.
    Errors inside the extraction task are swallowed so they cannot affect
    the sync response already returned to the caller.
    """
    async def _run() -> None:
        from app.services.extraction_service import extract_sync_themes  # local import to avoid circular
        from app.database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as task_db:
                await extract_sync_themes(sync_run_id, task_db)
        except Exception:
            logger.exception("Background extraction task failed for sync_run=%s", sync_run_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        # No running event loop (e.g. during testing) — skip silently
        pass


def _schedule_evolution_summary(sync_run_id: uuid.UUID) -> None:
    """
    Schedule generate_evolution_summary as a background asyncio task.

    Opens its own DB session so it is fully decoupled from the request
    lifecycle. Errors are logged but never propagate to the caller.
    """
    async def _run() -> None:
        from app.services.ai_generation import generate_evolution_summary  # local import to avoid circular
        from app.database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as task_db:
                await generate_evolution_summary(sync_run_id, task_db)
        except Exception:
            logger.exception(
                "Background evolution summary task failed for sync_run=%s", sync_run_id
            )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        # No running event loop (e.g. during testing) — skip silently
        pass
