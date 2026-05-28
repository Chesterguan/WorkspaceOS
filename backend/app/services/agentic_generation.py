"""
Agentic generation service: multi-model, multi-round draft pipeline.

Three-model architecture:
  1. LOCAL (Ollama) — privacy scan: checks draft for leaked secrets/private info before cloud calls
  2. CLOUD (Gemini) — generator: writes and revises drafts (fast, cheap, good quality)
  3. REVIEWER (OpenAI) — judge: scores and critiques drafts (strong reasoning)

Flow per round:
  1. Generator writes/revises draft
  2. Privacy scanner checks for leaks (local, no data leaves machine)
  3. Reviewer scores + critiques
  4. If score >= 8, stop. Otherwise loop with critique feedback.

Default: 4 rounds.
"""
import logging
import re
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.models.project import Project
from app.models.sync import GitHubRelease
from app.schemas.draft import DraftCreate
from app.services.ai_client import get_cloud_client, get_local_client
from app.services.repo_context import get_generation_context
from app.services.draft_service import create_draft
from app.services.feedback_service import get_preference_summary
from app.services.memory_service import get_recent_entries, search_memory
from app.services.narrative_service import build_context_block, get_or_create
from app.utils.context import build_changes_summary
from app.utils.prompts import get_template

logger = logging.getLogger(__name__)

# Cached reviewer client (OpenAI)
_reviewer_client = None


def _get_reviewer():
    """
    Return the reviewer client for draft judging.

    Routes through get_cloud_client() so CLOUD_AI_PROVIDER is respected.
    The multi-provider diversity rationale that justifies a direct OpenAI
    call only applies to the paper-reviewer roundtable (paper_reviewers.py);
    agentic draft review uses the configured cloud provider like everything else.
    """
    global _reviewer_client
    if _reviewer_client is None:
        _reviewer_client = get_cloud_client()
    return _reviewer_client


def _parse_score(review_text: str) -> int:
    match = re.search(r"(?:score|rating)[:\s]+(\d+)", review_text, re.IGNORECASE)
    if match:
        return min(10, max(0, int(match.group(1))))
    match = re.search(r"(\d+)\s*/\s*10", review_text)
    if match:
        return min(10, max(0, int(match.group(1))))
    match = re.search(r"^\s*(\d+)\s*$", review_text, re.MULTILINE)
    if match:
        return min(10, max(0, int(match.group(1))))
    return 5


PRIVACY_SCAN_SYSTEM = """You are a privacy scanner. Check the following draft for any leaked private information:
- API keys, tokens, secrets, passwords
- Internal URLs, IP addresses, database connection strings
- Personal emails, phone numbers, physical addresses
- Internal project codenames or confidential business data
- File paths that reveal system structure

Respond with ONLY one of:
- "CLEAN" if no private information found
- "FLAGGED: <brief description of what was found>" if private info detected

Be strict. When in doubt, flag it."""


async def _privacy_scan(content: str) -> Tuple[bool, str]:
    """Run local privacy scan. Returns (is_clean, message)."""
    local = get_local_client()
    try:
        result = await local.complete(
            PRIVACY_SCAN_SYSTEM,
            f"Scan this draft:\n\n{content}"
        )
        result = result.strip()
        if result.upper().startswith("CLEAN"):
            return True, "Clean"
        return False, result
    except Exception as e:
        # Fail-closed: treat an unavailable scanner as a flagged result so
        # we never accidentally publish a draft that skipped the privacy check.
        logger.warning("Privacy scan failed: %s", e)
        return False, "Privacy scan unavailable — treating as flagged for safety"


async def agentic_generate_draft(
    project_id: uuid.UUID,
    platform: str,
    sync_run_id: Optional[uuid.UUID],
    db: AsyncSession,
    max_rounds: int = 4,
) -> Tuple[str, uuid.UUID, List[Dict]]:
    """
    Multi-model draft generation pipeline.

    Returns:
        (final_content, draft_id, loop_trace)
    """
    generator = get_cloud_client()   # Gemini — writes drafts
    reviewer = _get_reviewer()       # OpenAI — judges quality

    # --- Build context ---
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    narrative = await get_or_create(project_id, db)
    narrative_ctx = build_context_block(narrative)
    changes_summary = await build_changes_summary(project_id, sync_run_id, db)

    memory_query = narrative.one_liner or project.name
    try:
        entries = await search_memory(project_id, memory_query, limit=5, db=db)
    except Exception:
        entries = await get_recent_entries(project_id, limit=5, db=db)

    memory_context = (
        "\n".join(f"[{e.entry_type}] {e.content}" for e in entries)
        if entries
        else "No relevant memory entries."
    )

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
        logger.exception("knowledge enrichment of agentic draft failed (non-fatal)")

    preference_summary = await get_preference_summary(project_id, db)

    readme_result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type == "readme_content",
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(1)
    )
    readme_entry = readme_result.scalar_one_or_none()
    readme_content = readme_entry.content if readme_entry else ""

    release_notes_result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type == "release_note",
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(3)
    )
    release_note_entries = list(release_notes_result.scalars().all())
    release_notes = "\n".join(e.content for e in release_note_entries) if release_note_entries else ""

    # Fetch LIVE repo context from GitHub
    repo_context = ""
    if project.github_repo:
        is_private = project.status == "private"
        repo_context = await get_generation_context(project.github_repo, is_private=is_private)

    ctx = {
        "project_name": project.name,
        "github_url": f"https://github.com/{project.github_repo}" if project.github_repo else "",
        "changes_summary": changes_summary,
        "memory_context": memory_context,
        "preference_context": preference_summary,
        "repo_context": repo_context,
        "readme_content": readme_content,
        "release_notes": release_notes,
        **narrative_ctx,
    }

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
    system, user_prompt = template_fn(ctx)

    # --- Step 1: Initial generation (Gemini) ---
    content = await generator.complete(system, user_prompt)
    loop_trace: List[Dict] = []

    # --- Step 2: Privacy scan (Local Ollama) ---
    is_clean, scan_msg = await _privacy_scan(content)
    if not is_clean:
        # Auto-revise to remove flagged content
        content = await generator.complete(
            system,
            f"Your previous draft contained private/sensitive information that must be removed.\n"
            f"Privacy scan result: {scan_msg}\n\n"
            f"Original draft:\n{content}\n\n"
            f"Rewrite the draft with ALL sensitive information removed. Output only the clean draft."
        )

    # --- Step 3: Review loop (OpenAI reviews, Gemini revises) ---
    for round_num in range(1, max_rounds + 1):
        # OpenAI reviews
        review_template_fn = get_template("review")
        review_system, review_user = review_template_fn({
            "platform": platform,
            "draft_content": content,
            "project_name": project.name,
        })
        review_response = await reviewer.complete(review_system, review_user)
        score = _parse_score(review_response)

        # Privacy scan each revision
        is_clean, scan_msg = await _privacy_scan(content)

        loop_trace.append({
            "round": round_num,
            "content": content,
            "score": score,
            "critique": review_response,
            "privacy_clean": is_clean,
            "privacy_note": scan_msg,
            "generator": "gemini",
            "reviewer": "openai",
        })

        if score >= 8 and is_clean:
            break

        # Gemini revises based on OpenAI's critique
        revision_notes = []
        if score < 8:
            revision_notes.append(
                f"A reviewer scored this {score}/10 with this critique:\n{review_response}"
            )
        if not is_clean:
            revision_notes.append(
                f"Privacy scan flagged issues: {scan_msg}\nRemove ALL sensitive information."
            )

        refine_user = (
            f"Here is your previous draft:\n\n{content}\n\n"
            + "\n\n".join(revision_notes) +
            "\n\nRewrite the draft addressing all points. Output only the improved draft."
        )
        content = await generator.complete(system, refine_user)

    # --- Save final draft ---
    rendered_prompt = f"SYSTEM:\n{system}\n\nUSER:\n{user_prompt}"
    draft_data = DraftCreate(
        platform=platform,
        content=content,
        generation_prompt=rendered_prompt,
        sync_run_id=sync_run_id,
    )
    draft = await create_draft(project_id, draft_data, db)

    return content, draft.id, loop_trace
