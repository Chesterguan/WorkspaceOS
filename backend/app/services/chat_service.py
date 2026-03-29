"""
Chat service: Co-Founder AI conversation.

Manages conversation history, assembles rich context (narrative, repo, workspace,
memory, recent drafts/blogs), calls the cloud AI, and persists both the user
message and the assistant reply.
"""
import logging
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost
from app.models.chat import ChatMessage
from app.models.draft import Draft
from app.models.project import Project
from app.services.ai_client import get_cloud_client
from app.services.memory_service import search_memory
from app.services.narrative_service import build_context_block, get_or_create
from app.services.repo_context import get_generation_context
from app.services.workspace_scanner import get_latest_snapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CO_FOUNDER_SYSTEM = """You are an AI co-founder and strategic advisor embedded in the user's \
project management tool, ProjectScribe.

Your role:
- Act as a knowledgeable, candid co-founder who deeply understands the project
- Help with strategy, product decisions, technical architecture, GTM planning, and fundraising
- Give honest, direct opinions — not just validation
- Ask clarifying questions when a problem isn't clearly defined
- Remember context from earlier in the conversation and across sessions (via memory)
- Help draft communications, blog posts, LinkedIn content, press releases, and investor updates
- Identify risks, blind spots, and opportunities the founder might be missing

Tone:
- Conversational and direct, like a trusted co-founder over coffee
- Confident but not arrogant — acknowledge uncertainty where it exists
- Supportive without being a yes-man
- Use concrete examples and specific recommendations, not vague platitudes

Guidelines:
- If you have workspace context, refer to actual files and code when relevant
- If you have repository context, cite specific commits, PRs, or issues
- If you have memory entries, connect past learnings to current questions
- Always be actionable — end responses with a clear next step when appropriate
- Keep responses focused; prefer depth on one topic over shallow coverage of many"""


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

async def _build_chat_context(
    project_id: uuid.UUID,
    user_message: str,
    include_workspace: bool,
    include_memory: bool,
    include_repo: bool,
    db: AsyncSession,
) -> str:
    """
    Assemble a rich context block to prepend to the AI conversation.

    Pulls from:
    - Project narrative (always included)
    - GitHub repo context (if include_repo and project has github_repo)
    - Workspace snapshot (if include_workspace and a snapshot exists)
    - Semantic memory search (if include_memory)
    - Recent drafts (last 3 titles/platforms)
    - Recent blog posts (last 3 titles)
    """
    from sqlalchemy import select as sa_select

    sections: List[str] = []

    # -- Project narrative --
    try:
        narrative = await get_or_create(project_id, db)
        ctx = build_context_block(narrative)
        narrative_parts: List[str] = []
        if ctx.get("one_liner"):
            narrative_parts.append(f"One-liner: {ctx['one_liner']}")
        if ctx.get("target_audience"):
            narrative_parts.append(f"Target audience: {ctx['target_audience']}")
        if ctx.get("origin_story"):
            narrative_parts.append(f"Origin story: {ctx['origin_story']}")
        if ctx.get("tone_notes"):
            narrative_parts.append(f"Tone notes: {ctx['tone_notes']}")
        if ctx.get("preferred_angles"):
            narrative_parts.append(f"Preferred angles: {', '.join(ctx['preferred_angles'])}")
        if narrative_parts:
            sections.append("## Project Narrative\n" + "\n".join(narrative_parts))
    except Exception:
        logger.exception("Failed to load narrative for project %s", project_id)

    # -- GitHub repo context --
    if include_repo:
        try:
            result = await db.execute(
                sa_select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project and project.github_repo:
                is_private = False  # assume public; could be stored on project
                repo_ctx = await get_generation_context(project.github_repo, is_private=is_private)
                if repo_ctx and repo_ctx.strip():
                    # Truncate to keep total context manageable
                    if len(repo_ctx) > 5000:
                        repo_ctx = repo_ctx[:5000] + "\n\n[... truncated ...]"
                    sections.append(f"## Repository Context\n{repo_ctx}")
        except Exception:
            logger.exception("Failed to fetch repo context for project %s", project_id)

    # -- Workspace snapshot --
    if include_workspace:
        try:
            snapshot = await get_latest_snapshot(project_id, db)
            if snapshot:
                ws_parts: List[str] = [snapshot.summary]
                if snapshot.git_branch:
                    ws_parts.append(f"\nCurrent branch: {snapshot.git_branch}")
                if snapshot.git_status:
                    ws_parts.append(f"Git status:\n{snapshot.git_status}")
                sections.append("## Local Workspace\n" + "\n".join(ws_parts))
        except Exception:
            logger.exception("Failed to load workspace snapshot for project %s", project_id)

    # -- Memory search --
    if include_memory:
        try:
            memories = await search_memory(project_id, user_message, limit=5, db=db)
            if memories:
                mem_lines = [f"- {m.content[:300]}" for m in memories]
                sections.append("## Relevant Memory\n" + "\n".join(mem_lines))
        except Exception:
            logger.exception("Memory search failed for project %s", project_id)

    # -- Recent drafts --
    try:
        draft_result = await db.execute(
            sa_select(Draft)
            .where(Draft.project_id == project_id, Draft.parent_draft_id.is_(None))
            .order_by(Draft.created_at.desc())
            .limit(3)
        )
        recent_drafts = list(draft_result.scalars().all())
        if recent_drafts:
            draft_lines = [
                f"- [{d.platform}] {d.title or '(no title)'} ({d.status})"
                for d in recent_drafts
            ]
            sections.append("## Recent Drafts\n" + "\n".join(draft_lines))
    except Exception:
        logger.exception("Failed to load recent drafts for project %s", project_id)

    # -- Recent blog posts --
    try:
        blog_result = await db.execute(
            sa_select(BlogPost)
            .where(BlogPost.project_id == project_id)
            .order_by(BlogPost.created_at.desc())
            .limit(3)
        )
        recent_blogs = list(blog_result.scalars().all())
        if recent_blogs:
            blog_lines = [f"- {b.title} ({b.status})" for b in recent_blogs]
            sections.append("## Recent Blog Posts\n" + "\n".join(blog_lines))
    except Exception:
        logger.exception("Failed to load recent blog posts for project %s", project_id)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_message(
    project_id: uuid.UUID,
    user_message: str,
    include_workspace: bool,
    include_memory: bool,
    include_repo: bool,
    db: AsyncSession,
) -> ChatMessage:
    """
    Store the user message, build context, fetch history, call cloud AI,
    store the assistant reply, and return it.
    """
    # 1. Persist user message
    user_msg = ChatMessage(
        project_id=project_id,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    await db.flush()

    # 2. Build rich context block
    context_block = await _build_chat_context(
        project_id=project_id,
        user_message=user_message,
        include_workspace=include_workspace,
        include_memory=include_memory,
        include_repo=include_repo,
        db=db,
    )

    # 3. Build conversation history (last 20 messages before the one we just inserted)
    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.project_id == project_id,
            ChatMessage.id != user_msg.id,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    history: List[ChatMessage] = list(reversed(history_result.scalars().all()))

    # 4. Compose the user prompt that carries context + history + new message
    user_prompt_parts: List[str] = []

    if context_block.strip():
        user_prompt_parts.append(
            f"## Project Context\n\n{context_block}\n\n---\n"
        )

    if history:
        history_lines: List[str] = []
        for msg in history:
            role_label = "User" if msg.role == "user" else "Assistant"
            # Truncate very long history entries to keep token budget reasonable
            content = msg.content if len(msg.content) <= 1000 else msg.content[:1000] + "..."
            history_lines.append(f"**{role_label}:** {content}")
        user_prompt_parts.append(
            "## Conversation History\n\n" + "\n\n".join(history_lines) + "\n\n---\n"
        )

    user_prompt_parts.append(f"**User:** {user_message}")
    user_prompt = "\n".join(user_prompt_parts)

    # 5. Call cloud AI
    ai = get_cloud_client()
    try:
        reply_text = await ai.complete(system=CO_FOUNDER_SYSTEM, user=user_prompt)
    except Exception:
        logger.exception("Cloud AI call failed for project %s", project_id)
        reply_text = (
            "I encountered an error while generating a response. "
            "Please check the AI provider configuration and try again."
        )

    # 6. Persist assistant reply
    assistant_msg = ChatMessage(
        project_id=project_id,
        role="assistant",
        content=reply_text,
        metadata_={
            "include_workspace": include_workspace,
            "include_memory": include_memory,
            "include_repo": include_repo,
        },
    )
    db.add(assistant_msg)
    await db.flush()
    await db.refresh(assistant_msg)
    return assistant_msg


async def get_history(
    project_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[ChatMessage], int]:
    """
    Return a page of chat messages (oldest-first) and the total count.
    """
    total_result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.project_id == project_id)
    )
    total: int = total_result.scalar_one()

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    messages = list(result.scalars().all())
    return messages, total


async def clear_history(project_id: uuid.UUID, db: AsyncSession) -> int:
    """Delete all chat messages for the project. Returns the number deleted."""
    from sqlalchemy import delete
    result = await db.execute(
        delete(ChatMessage).where(ChatMessage.project_id == project_id)
    )
    return result.rowcount
