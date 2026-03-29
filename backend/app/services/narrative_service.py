"""
Narrative service: get-or-create, upsert, and context block builder.
"""
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.narrative import Narrative
from app.schemas.narrative import NarrativeUpdate


async def get_or_create(project_id: uuid.UUID, db: AsyncSession) -> Narrative:
    """Return the narrative for the project, creating an empty one if it doesn't exist."""
    result = await db.execute(
        select(Narrative).where(Narrative.project_id == project_id)
    )
    narrative = result.scalar_one_or_none()
    if narrative is None:
        narrative = Narrative(project_id=project_id, faq=[])
        db.add(narrative)
        await db.flush()
    return narrative


async def upsert(
    project_id: uuid.UUID, data: NarrativeUpdate, db: AsyncSession
) -> Narrative:
    """Update (or create) the narrative for a project, applying only the provided fields."""
    narrative = await get_or_create(project_id, db)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(narrative, field, value)

    await db.flush()
    await db.refresh(narrative)
    return narrative


def build_context_block(narrative: Optional[Narrative]) -> dict:
    """Return a flat dict of narrative fields suitable for prompt templates."""
    if narrative is None:
        return {
            "one_liner": None,
            "target_audience": None,
            "origin_story": None,
            "preferred_angles": [],
            "avoided_angles": [],
            "faq_text": "",
            "tone_notes": None,
        }

    # Render FAQ as readable Q&A pairs
    faq_lines: list[str] = []
    for item in narrative.faq or []:
        q = item.get("q") or item.get("question", "")
        a = item.get("a") or item.get("answer", "")
        if q:
            faq_lines.append(f"Q: {q}\nA: {a}")

    return {
        "one_liner": narrative.one_liner,
        "target_audience": narrative.target_audience,
        "origin_story": narrative.origin_story,
        "preferred_angles": narrative.preferred_angles or [],
        "avoided_angles": narrative.avoided_angles or [],
        "faq_text": "\n\n".join(faq_lines) if faq_lines else "None provided.",
        "tone_notes": narrative.tone_notes,
    }
