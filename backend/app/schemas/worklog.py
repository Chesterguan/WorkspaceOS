"""Pydantic schemas for the work log (progress report) feature."""
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class WorkLogGoal(BaseModel):
    description: str
    status: str = Field(
        default="in_progress",
        description="One of: completed, in_progress, blocked, deferred",
    )


class GenerateWorkLogRequest(BaseModel):
    period_type: str = Field(
        ...,
        description="One of: weekly, monthly, quarterly",
    )
    period_start: date
    period_end: date
    project_ids: List[uuid.UUID] = Field(..., min_length=1)
    goals: Optional[List[WorkLogGoal]] = None
    additional_instructions: Optional[str] = Field(
        default=None,
        description="Free-text instructions to guide report generation",
    )


class WorkLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    period_type: str
    period_start: date
    period_end: date
    project_ids: List[uuid.UUID]
    content: str
    goals: Optional[dict]
    created_at: datetime
    updated_at: datetime


class WorkLogListResponse(BaseModel):
    items: List[WorkLogResponse]
    total: int


class UpdateWorkLogRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = None
    goals: Optional[List[WorkLogGoal]] = None


class ExportDocxResponse(BaseModel):
    docx_base64: str
    filename: str
