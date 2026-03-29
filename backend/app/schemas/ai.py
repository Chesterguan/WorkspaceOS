import uuid
from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    project_id: Optional[uuid.UUID] = None
    platform: str = Field(
        ...,
        description="Target platform: linkedin, twitter, xiaohongshu, medium_outline, github_release",
    )
    sync_run_id: Optional[uuid.UUID] = None


class GenerateResponse(BaseModel):
    content: str
    platform: str
    draft_id: Optional[uuid.UUID] = None


class SummaryRequest(BaseModel):
    sync_run_id: uuid.UUID
