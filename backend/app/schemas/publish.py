"""
Schemas for the auto-publish endpoints (GitHub Releases and Twitter/X).
"""
import uuid
from typing import Optional

from pydantic import BaseModel


class PublishGitHubReleaseRequest(BaseModel):
    tag_name: str
    target_branch: str = "main"
    # Create as a draft release on GitHub (not publicly visible yet)
    draft_release: bool = False
    prerelease: bool = False


class PublishTweetRequest(BaseModel):
    # No extra params needed — content is pulled from the draft
    pass


class PublishResponse(BaseModel):
    platform: str
    success: bool
    post_url: Optional[str] = None
    post_record_id: Optional[uuid.UUID] = None
    # Human-readable error message when success=False
    error: Optional[str] = None
    # Raw platform-specific response data for debugging
    details: Optional[dict] = None
