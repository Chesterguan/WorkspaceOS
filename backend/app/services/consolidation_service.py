"""
Consolidation service: synthesises many fine-grained memory entries into a
single "consolidated_summary" entry that captures the project's accumulated
knowledge in a compact, queryable form.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.services.ai_client import get_local_client
from app.services.memory_service import add_entry
from app.utils.prompts import get_template


async def consolidate_memory(project_id: uuid.UUID, db: AsyncSession) -> MemoryEntry:
    """
    Load recent memory entries for the project, ask the AI to synthesise them
    into a dense summary, and store the result as a new 'consolidated_summary'
    memory entry.

    This keeps the working memory compact without losing historical context —
    the consolidated entry is highly semantically similar to all its source
    entries, so vector search will surface it when relevant.
    """
    # Load the 50 most recent entries (excluding any existing consolidated summaries
    # to avoid circular summarisation)
    result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type != "consolidated_summary",
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(50)
    )
    entries = list(result.scalars().all())

    if not entries:
        raise ValueError(f"No memory entries found for project {project_id} to consolidate")

    entry_lines = [f"[{e.entry_type}] {e.content}" for e in entries]
    ctx = {
        "entry_count": len(entries),
        "entries_text": "\n".join(entry_lines),
    }

    template_fn = get_template("consolidation")
    system, user = template_fn(ctx)

    ai = get_local_client()
    summary = await ai.complete(system, user)

    # Persist as a new memory entry so it participates in vector search
    consolidated = await add_entry(
        project_id=project_id,
        entry_type="consolidated_summary",
        content=summary,
        source_ref=f"consolidation_of_{len(entries)}_entries",
        db=db,
    )
    return consolidated
