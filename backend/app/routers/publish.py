"""
Publishing router: endpoints to auto-publish drafts to external platforms.

Both endpoints follow the same contract:
- Validate the draft exists and belongs to the project.
- Delegate to publish_service which handles the platform API call.
- On success: the service creates a PostRecord and marks the draft published.
- On failure: return success=False with an error message rather than a 500.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.draft import Draft
from app.models.project import Project
from app.schemas.publish import (
    PublishGitHubReleaseRequest,
    PublishLinkedInRequest,
    PublishResponse,
    PublishTweetRequest,
)
from app.services import publish_service

router = APIRouter(
    prefix="/projects/{project_id}/drafts/{draft_id}/publish",
    tags=["publish"],
)


# ---------------------------------------------------------------------------
# Guards — reused by both endpoints
# ---------------------------------------------------------------------------

async def _require_project_and_draft(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    db: AsyncSession,
) -> Draft:
    """
    Raise 404 if the project or draft does not exist, or if the draft does not
    belong to the project.
    """
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    draft_result = await db.execute(select(Draft).where(Draft.id == draft_id))
    draft = draft_result.scalar_one_or_none()
    if draft is None or draft.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    return draft


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/github-release",
    response_model=PublishResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish draft as a GitHub Release",
)
async def publish_github_release(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: PublishGitHubReleaseRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PublishResponse:
    """
    Create a GitHub Release from the draft content.

    The release body is taken directly from the draft. The draft status is
    updated to 'published' and a PostRecord is created on success.
    """
    await _require_project_and_draft(project_id, draft_id, db)

    result = await publish_service.publish_github_release(
        project_id=project_id,
        draft_id=draft_id,
        tag_name=body.tag_name,
        target_branch=body.target_branch,
        draft_release=body.draft_release,
        prerelease=body.prerelease,
        db=db,
    )

    return PublishResponse(
        platform="github_release",
        success=result["success"],
        post_url=result["post_url"],
        post_record_id=result["post_record_id"],
        error=result["error"],
        details=result["details"],
    )


@router.post(
    "/twitter",
    response_model=PublishResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish draft as a tweet or thread",
)
async def publish_twitter(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: PublishTweetRequest,  # noqa: ARG001 — no fields yet, kept for API consistency
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PublishResponse:
    """
    Post the draft to Twitter/X.

    Automatically detects numbered thread markers (1/, 2/, …) and posts as a
    reply chain. Single tweets are posted directly. The draft status is updated
    to 'published' and a PostRecord is created on success.
    """
    await _require_project_and_draft(project_id, draft_id, db)

    result = await publish_service.publish_tweet(
        project_id=project_id,
        draft_id=draft_id,
        db=db,
    )

    return PublishResponse(
        platform="twitter",
        success=result["success"],
        post_url=result["post_url"],
        post_record_id=result["post_record_id"],
        error=result["error"],
        details=result["details"],
    )


@router.post(
    "/linkedin",
    response_model=PublishResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish draft as a LinkedIn post",
)
async def publish_linkedin(
    project_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: PublishLinkedInRequest,  # noqa: ARG001 — no fields yet, kept for API consistency
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PublishResponse:
    """
    Post the draft to LinkedIn.

    Requires a valid OAuth access token stored by completing the LinkedIn
    OAuth flow via GET /linkedin/auth. The draft status is updated to
    'published' and a PostRecord is created on success.
    """
    await _require_project_and_draft(project_id, draft_id, db)

    result = await publish_service.publish_linkedin(
        project_id=project_id,
        draft_id=draft_id,
        db=db,
    )

    return PublishResponse(
        platform="linkedin",
        success=result["success"],
        post_url=result["post_url"],
        post_record_id=result["post_record_id"],
        error=result["error"],
        details=result["details"],
    )
