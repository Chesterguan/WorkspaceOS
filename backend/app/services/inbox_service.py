"""
Inbox project — the per-user "unassigned" bucket.

When the classifier can't confidently place an ingested item (calendar
event, email, MCP payload) on a specific project, it lands here. A real
Project row rather than a special memory_entry flag so every downstream
feature (feed, search, wiki, worklog) just works.

Creation is idempotent and guarded by (user_id, slug="inbox") uniqueness.
We avoid the heavier SQL ``ON CONFLICT ... RETURNING`` construct because
the unique constraint already exists at the row level — a duplicate
INSERT from a concurrent call fails, we catch it, and re-SELECT.
"""
import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project

logger = logging.getLogger(__name__)

INBOX_SLUG = "inbox"


async def get_or_create_inbox(user_id: uuid.UUID, db: AsyncSession) -> Project:
    """Return the user's Inbox project, creating it if necessary."""
    existing = await _find(user_id, db)
    if existing is not None:
        return existing

    project = Project(
        user_id=user_id,
        name="Inbox",
        slug=INBOX_SLUG,
        description=(
            "Auto-created catch-all for ingested items the classifier "
            "couldn't confidently place on a specific project. Items you "
            "re-tag will get their own project membership."
        ),
        github_branch="main",
        status="active",
    )
    db.add(project)
    try:
        await db.flush()
        await db.refresh(project)
    except IntegrityError:
        # Concurrent create lost the race — someone else made it first.
        # Roll back the failed flush, then return the existing row.
        await db.rollback()
        existing = await _find(user_id, db)
        if existing is None:
            raise  # Shouldn't happen; re-raise to avoid silent weirdness
        return existing
    logger.info("inbox: created Inbox project for user %s", user_id)
    return project


async def _find(user_id: uuid.UUID, db: AsyncSession) -> Optional[Project]:
    result = await db.execute(
        select(Project).where(
            Project.user_id == user_id,
            Project.slug == INBOX_SLUG,
        )
    )
    return result.scalar_one_or_none()
