import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# PostSchedule schemas
# ---------------------------------------------------------------------------

class PostScheduleCreate(BaseModel):
    draft_id: uuid.UUID
    platform: str = Field(..., min_length=1, max_length=100)
    scheduled_for: datetime
    status: str = "planned"
    notes: Optional[str] = None


class PostScheduleUpdate(BaseModel):
    platform: Optional[str] = Field(None, min_length=1, max_length=100)
    scheduled_for: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PostScheduleResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    draft_id: uuid.UUID
    project_id: uuid.UUID
    platform: str
    scheduled_for: datetime
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PostRecord schemas
# ---------------------------------------------------------------------------

class PostRecordCreate(BaseModel):
    draft_id: uuid.UUID
    platform: str = Field(..., min_length=1, max_length=100)
    posted_at: datetime
    post_url: Optional[str] = None
    notes: Optional[str] = None
    post_type: str = "manual"


class PostRecordResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    draft_id: uuid.UUID
    project_id: uuid.UUID
    platform: str
    posted_at: datetime
    post_url: Optional[str]
    notes: Optional[str]
    post_type: str
    created_at: datetime
