import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class NarrativeUpdate(BaseModel):
    one_liner: Optional[str] = None
    target_audience: Optional[str] = None
    origin_story: Optional[str] = None
    preferred_angles: Optional[List[str]] = None
    avoided_angles: Optional[List[str]] = None
    faq: Optional[List[Dict]] = None
    tone_notes: Optional[str] = None


class NarrativeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    one_liner: Optional[str]
    target_audience: Optional[str]
    origin_story: Optional[str]
    preferred_angles: Optional[List[str]]
    avoided_angles: Optional[List[str]]
    faq: List[Dict]
    tone_notes: Optional[str]
    updated_at: datetime
