import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = ""
    status: str = "draft"
    tags: Optional[List[str]] = None
    sync_run_id: Optional[uuid.UUID] = None


class BlogPostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    # Optional user-supplied note describing what changed in this edit
    change_note: Optional[str] = None


class BlogPostResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    content: str
    status: str
    tags: Optional[List[str]]
    sync_run_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class BlogPostVersionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    blog_post_id: uuid.UUID
    version: int
    content: str
    title: str
    saved_at: datetime
    change_note: Optional[str]


class BlogGenerateRequest(BaseModel):
    """Body for the AI blog generation endpoint."""
    context_hint: Optional[str] = Field(
        None,
        description="Optional free-text hint to guide generation (e.g. 'focus on performance improvements')",
    )
