"""
Draft service: CRUD operations plus version chain management.
"""
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.schemas.draft import DraftCreate, DraftUpdate


async def create_draft(
    project_id: uuid.UUID, data: DraftCreate, db: AsyncSession
) -> Draft:
    """Create a new root draft (version 1, no parent)."""
    draft = Draft(
        project_id=project_id,
        platform=data.platform,
        title=data.title,
        content=data.content,
        status=data.status,
        generation_prompt=data.generation_prompt,
        sync_run_id=data.sync_run_id,
        parent_draft_id=None,
        version=1,
    )
    db.add(draft)
    await db.flush()
    await db.refresh(draft)
    return draft


async def get_draft(draft_id: uuid.UUID, db: AsyncSession) -> Optional[Draft]:
    result = await db.execute(select(Draft).where(Draft.id == draft_id))
    return result.scalar_one_or_none()


async def list_drafts(
    project_id: uuid.UUID,
    db: AsyncSession,
    platform: Optional[str] = None,
) -> List[Draft]:
    """Return all root drafts (no parent) for a project, optionally filtered by platform."""
    query = select(Draft).where(
        Draft.project_id == project_id,
        Draft.parent_draft_id.is_(None),
    )
    if platform:
        query = query.where(Draft.platform == platform)
    query = query.order_by(Draft.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_draft(
    draft: Draft, data: DraftUpdate, db: AsyncSession
) -> Draft:
    """Apply a partial update to an existing draft in place."""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(draft, field, value)
    await db.flush()
    await db.refresh(draft)
    return draft


async def delete_draft(draft: Draft, db: AsyncSession) -> None:
    await db.delete(draft)
    await db.flush()


async def save_new_version(
    parent_draft_id: uuid.UUID,
    content: str,
    generation_prompt: Optional[str],
    db: AsyncSession,
) -> Draft:
    """
    Create a new version in the chain.

    The root draft is always the anchor — child drafts point to it via
    parent_draft_id.  We find the highest version in the chain and increment.
    """
    # Load the parent (or root) draft to copy metadata
    result = await db.execute(select(Draft).where(Draft.id == parent_draft_id))
    parent = result.scalar_one_or_none()
    if parent is None:
        raise ValueError(f"Draft {parent_draft_id} not found")

    # If the parent itself has a parent, the true root is the parent's parent.
    # For simplicity we keep a flat chain: all versions point to the original root.
    root_id = parent.parent_draft_id or parent.id

    # Find the current max version in this chain
    chain_result = await db.execute(
        select(Draft.version).where(
            (Draft.id == root_id) | (Draft.parent_draft_id == root_id)
        )
    )
    versions = [row[0] for row in chain_result.all()]
    next_version = max(versions, default=1) + 1

    new_draft = Draft(
        project_id=parent.project_id,
        platform=parent.platform,
        title=parent.title,
        content=content,
        status="draft",
        generation_prompt=generation_prompt,
        sync_run_id=parent.sync_run_id,
        parent_draft_id=root_id,
        version=next_version,
    )
    db.add(new_draft)
    await db.flush()
    await db.refresh(new_draft)
    return new_draft


async def get_version_chain(draft_id: uuid.UUID, db: AsyncSession) -> List[Draft]:
    """
    Return all versions in the chain for a given draft, sorted oldest-first.
    Works whether the given draft_id is the root or any version in the chain.
    """
    result = await db.execute(select(Draft).where(Draft.id == draft_id))
    draft = result.scalar_one_or_none()
    if draft is None:
        return []

    root_id = draft.parent_draft_id or draft.id

    chain_result = await db.execute(
        select(Draft)
        .where((Draft.id == root_id) | (Draft.parent_draft_id == root_id))
        .order_by(Draft.version.asc())
    )
    return list(chain_result.scalars().all())
