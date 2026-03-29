"""
Feedback service: record human feedback on AI drafts and summarise preferences.
The preference summary is injected into prompts to guide future generation.
"""
import uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_feedback import AIFeedback
from app.models.draft import Draft


async def record_feedback(
    draft_id: uuid.UUID,
    project_id: uuid.UUID,
    outcome: str,
    final_content: Optional[str],
    notes: Optional[str],
    db: AsyncSession,
) -> AIFeedback:
    """
    Persist a feedback record.  If final_content is supplied and the outcome is
    'heavily_edited', compute a simple character-level edit distance as a rough
    quality signal (true Levenshtein is O(n*m) — we use difflib for speed).
    """
    edit_distance: Optional[int] = None

    if outcome == "heavily_edited" and final_content is not None:
        # Load the original generated content to compare
        draft_result = await db.execute(select(Draft).where(Draft.id == draft_id))
        draft = draft_result.scalar_one_or_none()
        if draft is not None:
            import difflib
            sm = difflib.SequenceMatcher(None, draft.content, final_content)
            # Edit distance approximation: total characters - matching characters
            matching = sum(t.size for t in sm.get_matching_blocks())
            edit_distance = len(draft.content) + len(final_content) - 2 * matching

    feedback = AIFeedback(
        draft_id=draft_id,
        project_id=project_id,
        outcome=outcome,
        edit_distance=edit_distance,
        user_notes=notes,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)
    return feedback


async def get_preference_summary(project_id: uuid.UUID, db: AsyncSession) -> str:
    """
    Compute statistics from recorded feedback for a project and return a prose
    summary suitable for injection into AI generation prompts.
    """
    result = await db.execute(
        select(AIFeedback).where(AIFeedback.project_id == project_id)
    )
    feedbacks: List[AIFeedback] = list(result.scalars().all())

    if not feedbacks:
        return "No feedback recorded yet. Aim for a balanced, informative tone."

    total = len(feedbacks)
    approved = sum(1 for f in feedbacks if f.outcome == "approved")
    rejected = sum(1 for f in feedbacks if f.outcome == "rejected")
    heavily_edited = sum(1 for f in feedbacks if f.outcome == "heavily_edited")
    approval_rate = approved / total if total > 0 else 0.0

    edit_distances = [f.edit_distance for f in feedbacks if f.edit_distance is not None]
    avg_edit = sum(edit_distances) / len(edit_distances) if edit_distances else None

    # Collect user notes for context
    notes_list = [f.user_notes for f in feedbacks if f.user_notes]
    notes_excerpt = ""
    if notes_list:
        # Include the 3 most recent notes as examples
        recent_notes = notes_list[-3:]
        notes_excerpt = " Example feedback: " + " | ".join(f'"{n}"' for n in recent_notes)

    lines = [
        f"Based on {total} past drafts: {approved} approved ({approval_rate:.0%}), "
        f"{rejected} rejected, {heavily_edited} heavily edited."
    ]
    if avg_edit is not None:
        lines.append(f"Average edit distance on heavily-edited drafts: {avg_edit:.0f} characters.")
    if heavily_edited > approved:
        lines.append(
            "The user frequently edits generated content — prioritise accuracy and specificity "
            "over style. Avoid filler phrases."
        )
    elif approval_rate > 0.7:
        lines.append(
            "The user approves most drafts — the current style is working well. "
            "Maintain the established voice and structure."
        )
    if notes_excerpt:
        lines.append(notes_excerpt)

    return " ".join(lines)
