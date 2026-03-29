import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DraftCreate(BaseModel):
    platform: str = Field(..., min_length=1, max_length=100)
    title: Optional[str] = Field(None, max_length=500)
    content: str = Field(..., min_length=1)
    status: str = "draft"
    generation_prompt: Optional[str] = None
    sync_run_id: Optional[uuid.UUID] = None


class DraftUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    status: Optional[str] = None


class DraftResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    platform: str
    title: Optional[str]
    content: str
    status: str
    generation_prompt: Optional[str]
    sync_run_id: Optional[uuid.UUID]
    parent_draft_id: Optional[uuid.UUID]
    version: int
    created_at: datetime
    updated_at: datetime
