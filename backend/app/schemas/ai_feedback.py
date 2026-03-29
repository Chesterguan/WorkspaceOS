import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AIFeedbackCreate(BaseModel):
    """Body for recording feedback on a draft."""

    outcome: str = Field(..., pattern="^(approved|rejected|heavily_edited)$")
    # The final content after user edits — used to compute edit distance
    final_content: Optional[str] = None
    user_notes: Optional[str] = None


class AIFeedbackResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    draft_id: uuid.UUID
    project_id: uuid.UUID
    outcome: str
    edit_distance: Optional[int]
    user_notes: Optional[str]
    created_at: datetime


class FeedbackSummaryResponse(BaseModel):
    """Aggregated statistics and prose summary of AI feedback for a project."""

    project_id: uuid.UUID
    total_feedbacks: int
    approved_count: int
    rejected_count: int
    heavily_edited_count: int
    approval_rate: float
    average_edit_distance: Optional[float]
    summary_prose: str
