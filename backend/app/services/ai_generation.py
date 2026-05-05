"""
AI generation service: builds context from DB, renders prompts, calls the AI,
and persists the resulting draft.
"""
import logging
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.models.project import Project
from app.models.sync import GitHubRelease, SyncRun
from app.services.ai_client import get_ai_client
from app.services.draft_service import create_draft
from app.services.memory_service import get_recent_entries, search_memory
from app.services.narrative_service import build_context_block, get_or_create
from app.schemas.draft import DraftCreate
from app.services.repo_context import get_generation_context
from app.utils.context import build_changes_summary
from app.utils.prompts import get_template

logger = logging.getLogger(__name__)


async def _load_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    return project


async def _build_memory_context(
    project_id: uuid.UUID,
    query: str,
    db: AsyncSession,
) -> str:
    """Return relevant memory entries as a prose block for prompt injection."""
    try:
        entries = await search_memory(project_id, query, limit=5, db=db)
    except Exception:
        # If embeddings aren't available (e.g. no API key in dev), fall back
        entries = await get_recent_entries(project_id, limit=5, db=db)

    if not entries:
        return "No relevant memory entries found."

    lines: List[str] = []
    for e in entries:
        lines.append(f"[{e.entry_type}] {e.content}")
    return "\n".join(lines)


async def _fetch_readme_content(project_id: uuid.UUID, db: AsyncSession) -> str:
    """
    Return the most recently stored README memory entry content, or an empty
    string if no README has been synced yet.
    """
    result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type == "readme_content",
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(1)
    )
    entry = result.scalar_one_or_none()
    return entry.content if entry else ""


async def _fetch_recent_release_notes(
    project_id: uuid.UUID, db: AsyncSession, limit: int = 3
) -> str:
    """
    Return the most recently stored release_note memory entries as a text block.
    """
    result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type == "release_note",
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
    )
    entries = list(result.scalars().all())
    if not entries:
        return ""
    return "\n".join(e.content for e in entries)


async def generate_draft(
    project_id: uuid.UUID,
    platform: str,
    sync_run_id: Optional[uuid.UUID],
    db: AsyncSession,
) -> Tuple[str, uuid.UUID]:
    """
    Generate content for the given platform and persist it as a Draft.
    Returns (content, draft_id).
    """
    project = await _load_project(project_id, db)
    narrative = await get_or_create(project_id, db)
    narrative_ctx = build_context_block(narrative)

    changes_summary = await build_changes_summary(project_id, sync_run_id, db)

    # Use the one_liner as the memory search query for relevance
    memory_query = narrative.one_liner or project.name
    memory_context = await _build_memory_context(project_id, memory_query, db)

    # -- Knowledge layer (decisions, claims, rejections, etc.) --
    try:
        from app.services.knowledge_service import search_knowledge
        kn_query = ((narrative.one_liner or "") + " " + (project.name or "")).strip()
        kn_query = kn_query or "project knowledge"
        hits = await search_knowledge(
            user_id=project.user_id, query=kn_query, db=db,
            project_id=project_id, limit=10,
        )
        if hits:
            lines = [
                f"- [{h.node.node_type}] {h.node.title} — {h.node.content[:300]}"
                for h in hits
            ]
            knowledge_context = "## Project knowledge\n" + "\n".join(lines)
            memory_context = knowledge_context + "\n\n" + memory_context
    except Exception:
        logger.exception("knowledge enrichment of draft generation failed (non-fatal)")

    # Fetch LIVE repo context from GitHub (the key missing piece)
    repo_context = ""
    if project.github_repo:
        is_private = project.status == "private"  # crude check; improve later
        repo_context = await get_generation_context(project.github_repo, is_private=is_private)

    # Also include stored README and release notes as fallback
    readme_content = await _fetch_readme_content(project_id, db)
    release_notes = await _fetch_recent_release_notes(project_id, db)

    ctx = {
        "project_name": project.name,
        "github_url": f"https://github.com/{project.github_repo}" if project.github_repo else "",
        "changes_summary": changes_summary,
        "memory_context": memory_context,
        "repo_context": repo_context,
        "readme_content": readme_content,
        "release_notes": release_notes,
        **narrative_ctx,
    }

    # Add release-specific context for the github_release platform
    if platform == "github_release":
        release_result = await db.execute(
            select(GitHubRelease)
            .where(GitHubRelease.project_id == project_id)
            .order_by(GitHubRelease.published_at.desc())
            .limit(2)
        )
        releases = list(release_result.scalars().all())
        if releases:
            ctx["tag_name"] = releases[0].tag_name
            ctx["release_name"] = releases[0].release_name or ""
            ctx["previous_release_body"] = releases[1].body if len(releases) > 1 else "N/A"

    template_fn = get_template(platform)
    system, user = template_fn(ctx)
    rendered_prompt = f"SYSTEM:\n{system}\n\nUSER:\n{user}"

    ai = get_ai_client()
    content = await ai.complete(system, user)

    draft_data = DraftCreate(
        platform=platform,
        content=content,
        generation_prompt=rendered_prompt,
        sync_run_id=sync_run_id,
    )
    draft = await create_draft(project_id, draft_data, db)
    return content, draft.id


async def generate_portfolio_draft(
    project_ids: List[uuid.UUID],
    platform: str,
    theme: Optional[str],
    additional_context: Optional[str],
    db: AsyncSession,
) -> Tuple[str, Optional[uuid.UUID], List[str]]:
    """
    Generate a combined post covering multiple projects.

    1. For each project: load narrative, fetch repo context (cached), get recent memory.
    2. Build a combined context block with all projects.
    3. Use the portfolio prompt template.
    4. Generate with cloud AI.
    5. Save as a draft under the FIRST project (with a title noting it's a portfolio post).
    6. Return (content, draft_id, project_names).
    """
    project_contexts: List[dict] = []
    project_names: List[str] = []
    first_project_id: Optional[uuid.UUID] = None

    for project_id in project_ids:
        project = await _load_project(project_id, db)
        if first_project_id is None:
            first_project_id = project_id

        project_names.append(project.name)
        narrative = await get_or_create(project_id, db)
        narrative_ctx = build_context_block(narrative)

        memory_query = narrative.one_liner or project.name
        memory_context = await _build_memory_context(project_id, memory_query, db)

        repo_context = ""
        if project.github_repo:
            is_private = project.status == "private"
            repo_context = await get_generation_context(project.github_repo, is_private=is_private)

        changes_summary = await build_changes_summary(project_id, None, db)

        project_contexts.append({
            "name": project.name,
            "github_url": f"https://github.com/{project.github_repo}" if project.github_repo else "",
            "one_liner": narrative_ctx.get("one_liner", ""),
            "repo_context": repo_context,
            "memory_context": memory_context,
            "changes_summary": changes_summary,
        })

    ctx = {
        "platform": platform,
        "theme": theme or "",
        "additional_context": additional_context or "",
        "projects": project_contexts,
    }

    template_fn = get_template("portfolio")
    system, user = template_fn(ctx)
    rendered_prompt = f"SYSTEM:\n{system}\n\nUSER:\n{user}"

    ai_client = get_ai_client()
    content = await ai_client.complete(system, user)

    # Compose a descriptive title for the draft
    names_joined = ", ".join(project_names)
    title_theme = f" — {theme}" if theme else ""
    draft_title = f"Portfolio Post{title_theme}: {names_joined}"

    draft_data = DraftCreate(
        platform=platform,
        title=draft_title,
        content=content,
        generation_prompt=rendered_prompt,
        sync_run_id=None,
    )
    draft = await create_draft(first_project_id, draft_data, db)
    return content, draft.id, project_names


async def generate_evolution_summary(sync_run_id: uuid.UUID, db: AsyncSession) -> str:
    """
    Generate a prose summary of what changed during a sync run and attach it
    to the SyncRun record.
    """
    result = await db.execute(select(SyncRun).where(SyncRun.id == sync_run_id))
    sync_run = result.scalar_one_or_none()
    if sync_run is None:
        raise ValueError(f"SyncRun {sync_run_id} not found")

    project = await _load_project(sync_run.project_id, db)

    # Gather commits for this run
    from app.models.sync import GitHubCommit
    commit_result = await db.execute(
        select(GitHubCommit)
        .where(GitHubCommit.sync_run_id == sync_run_id)
        .order_by(GitHubCommit.committed_at.desc())
    )
    commits = list(commit_result.scalars().all())

    release_result = await db.execute(
        select(GitHubRelease).where(GitHubRelease.sync_run_id == sync_run_id)
    )
    releases = list(release_result.scalars().all())

    commit_lines = []
    for c in commits:
        first_line = c.message.splitlines()[0] if c.message else "(no message)"
        commit_lines.append(f"- {c.sha[:7]}: {first_line}")

    release_lines = []
    for r in releases:
        release_lines.append(f"- {r.tag_name}: {r.release_name or 'no name'}")

    ctx = {
        "project_name": project.name,
        "github_repo": project.github_repo,
        "commit_count": len(commits),
        "commit_list": "\n".join(commit_lines) or "No commits.",
        "release_list": "\n".join(release_lines) or "No releases.",
    }

    template_fn = get_template("evolution_summary")
    system, user = template_fn(ctx)

    ai = get_ai_client()
    summary = await ai.complete(system, user)

    # Persist the summary on the sync run
    sync_run.evolution_summary = summary
    await db.flush()

    return summary
