"""
Blog service: CRUD with automatic version snapshotting and AI-assisted generation.
"""
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost, BlogPostVersion
from app.models.project import Project
from app.models.sync import GitHubCommit, GitHubRelease, SyncRun
from app.schemas.blog import BlogPostCreate, BlogPostUpdate
from app.services.ai_client import get_ai_client
from app.services.memory_service import get_recent_entries, search_memory
from app.services.narrative_service import build_context_block, get_or_create
from app.utils.prompts import get_template


async def create_blog_post(
    project_id: uuid.UUID,
    data: BlogPostCreate,
    db: AsyncSession,
) -> BlogPost:
    """Create a new blog post and immediately snapshot it as version 1."""
    post = BlogPost(
        project_id=project_id,
        title=data.title,
        content=data.content,
        status=data.status,
        tags=data.tags,
        sync_run_id=data.sync_run_id,
    )
    db.add(post)
    await db.flush()  # Assigns post.id before creating the version record

    version = BlogPostVersion(
        blog_post_id=post.id,
        version=1,
        content=data.content,
        title=data.title,
        change_note="Initial version",
    )
    db.add(version)
    await db.flush()
    await db.refresh(post)
    return post


async def update_blog_post(
    post_id: uuid.UUID,
    data: BlogPostUpdate,
    db: AsyncSession,
) -> BlogPost:
    """
    Apply a partial update. Snapshots the current state as a new version
    entry before writing the changes, preserving full edit history.
    """
    result = await db.execute(select(BlogPost).where(BlogPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise ValueError(f"BlogPost {post_id} not found")

    # Determine the next version number
    version_result = await db.execute(
        select(BlogPostVersion.version)
        .where(BlogPostVersion.blog_post_id == post_id)
        .order_by(BlogPostVersion.version.desc())
        .limit(1)
    )
    last_version = version_result.scalar_one_or_none() or 0

    # Snapshot current state before applying new values
    update_data = data.model_dump(exclude_unset=True)
    change_note = update_data.pop("change_note", None)

    snapshot = BlogPostVersion(
        blog_post_id=post.id,
        version=last_version + 1,
        content=post.content,
        title=post.title,
        change_note=change_note,
    )
    db.add(snapshot)

    # Apply updates to the live post
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.flush()
    await db.refresh(post)
    return post


async def get_version_chain(
    post_id: uuid.UUID,
    db: AsyncSession,
) -> List[BlogPostVersion]:
    """Return all version snapshots for a blog post, oldest first."""
    result = await db.execute(
        select(BlogPostVersion)
        .where(BlogPostVersion.blog_post_id == post_id)
        .order_by(BlogPostVersion.version.asc())
    )
    return list(result.scalars().all())


async def generate_blog_draft(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    context_hint: Optional[str],
    db: AsyncSession,
) -> str:
    """
    Generate blog content using the AI, seeded with:
    - project narrative
    - relevant memory entries
    - recent commits/releases
    - an optional free-text hint from the user

    Saves the generated content to the blog post (creating a new version snapshot)
    and returns the generated text.
    """
    # Load project and narrative
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    post_result = await db.execute(select(BlogPost).where(BlogPost.id == post_id))
    post = post_result.scalar_one_or_none()
    if post is None:
        raise ValueError(f"BlogPost {post_id} not found")

    narrative = await get_or_create(project_id, db)
    narrative_ctx = build_context_block(narrative)

    # Build recent changes summary from commits and releases
    commit_result = await db.execute(
        select(GitHubCommit)
        .where(GitHubCommit.project_id == project_id)
        .order_by(GitHubCommit.committed_at.desc())
        .limit(15)
    )
    commits = list(commit_result.scalars().all())

    release_result = await db.execute(
        select(GitHubRelease)
        .where(GitHubRelease.project_id == project_id)
        .order_by(GitHubRelease.published_at.desc())
        .limit(3)
    )
    releases = list(release_result.scalars().all())

    changes_lines = []
    if commits:
        changes_lines.append("### Recent Commits")
        for c in commits:
            date_str = c.committed_at.strftime("%Y-%m-%d") if c.committed_at else "unknown"
            first_line = c.message.splitlines()[0] if c.message else "(no message)"
            changes_lines.append(f"- [{c.sha[:7]}] {first_line} ({date_str})")
    if releases:
        changes_lines.append("\n### Releases")
        for r in releases:
            date_str = r.published_at.strftime("%Y-%m-%d") if r.published_at else "unknown"
            changes_lines.append(f"- {r.tag_name}: {r.release_name or 'no name'} ({date_str})")
    changes_summary = "\n".join(changes_lines) if changes_lines else "No recent activity."

    # Semantic memory lookup
    memory_query = context_hint or narrative.one_liner or project.name
    try:
        entries = await search_memory(project_id, memory_query, limit=5, db=db)
    except Exception:
        entries = await get_recent_entries(project_id, limit=5, db=db)

    memory_context = (
        "\n".join(f"[{e.entry_type}] {e.content}" for e in entries)
        if entries
        else "No relevant memory entries."
    )

    ctx = {
        "project_name": project.name,
        "post_title": post.title,
        "changes_summary": changes_summary,
        "memory_context": memory_context,
        "context_hint": context_hint or "No specific hint provided.",
        **narrative_ctx,
    }

    template_fn = get_template("blog_post")
    system, user = template_fn(ctx)

    ai = get_ai_client()
    generated_content = await ai.complete(system, user)

    # Save the generated content into the post (snapshot current first)
    update_data = BlogPostUpdate(
        content=generated_content,
        change_note="AI-generated content",
    )
    await update_blog_post(post_id, update_data, db)

    return generated_content
