"""
Shared context-building utilities used by both ai_generation and agentic_generation.
"""
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import GitHubCommit, GitHubRelease


async def build_changes_summary(
    project_id: uuid.UUID,
    sync_run_id: Optional[uuid.UUID],
    db: AsyncSession,
) -> str:
    """
    Build a human-readable summary of recent commits and releases.

    If a sync_run_id is provided the query is restricted to that run; otherwise
    the 10 most recent commits and 3 most recent releases across all runs are used.
    """
    commit_query = select(GitHubCommit).where(GitHubCommit.project_id == project_id)
    release_query = select(GitHubRelease).where(GitHubRelease.project_id == project_id)

    if sync_run_id:
        commit_query = commit_query.where(GitHubCommit.sync_run_id == sync_run_id)
        release_query = release_query.where(GitHubRelease.sync_run_id == sync_run_id)
    else:
        commit_query = commit_query.order_by(GitHubCommit.committed_at.desc()).limit(10)
        release_query = release_query.order_by(GitHubRelease.published_at.desc()).limit(3)

    commits: List[GitHubCommit] = list((await db.execute(commit_query)).scalars().all())
    releases: List[GitHubRelease] = list((await db.execute(release_query)).scalars().all())

    lines: List[str] = []

    if commits:
        lines.append("### Recent Commits")
        for c in commits:
            date_str = c.committed_at.strftime("%Y-%m-%d") if c.committed_at else "unknown date"
            # Only the first line of the commit message keeps things concise
            first_line = c.message.splitlines()[0] if c.message else "(no message)"
            lines.append(f"- [{c.sha[:7]}] {first_line} ({date_str})")

    if releases:
        lines.append("\n### Releases")
        for r in releases:
            date_str = r.published_at.strftime("%Y-%m-%d") if r.published_at else "unknown date"
            lines.append(f"- {r.tag_name}: {r.release_name or 'no name'} ({date_str})")
            if r.body:
                # Include first 200 chars of the release body for context
                snippet = r.body[:200].replace("\n", " ")
                lines.append(f"  {snippet}...")

    return "\n".join(lines) if lines else "No recent activity found."
