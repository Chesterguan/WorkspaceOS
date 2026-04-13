"""Response schemas for the project activity feed."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ActivityEventResponse(BaseModel):
    """One row on the activity feed. Shape mirrors the ActivityEvent model."""
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    event_type: str
    summary: str
    details: Optional[dict]
    source: str
    created_at: datetime


class ActivityFeedResponse(BaseModel):
    """Paginated feed: `next_cursor` is the ISO timestamp to pass back for the
    next page, or None when the caller has reached the end."""
    items: List[ActivityEventResponse]
    next_cursor: Optional[str] = None
