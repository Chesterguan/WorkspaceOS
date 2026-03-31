import uuid
from typing import List, Optional

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


class PortfolioGenerateRequest(BaseModel):
    project_ids: List[uuid.UUID] = Field(
        ...,
        description="2-5 project IDs to include in the portfolio post",
        min_length=2,
        max_length=5,
    )
    platform: str = Field(
        ...,
        description="Target platform: linkedin, twitter, xiaohongshu, medium_outline",
    )
    theme: Optional[str] = Field(
        None,
        description="Post theme, e.g. 'monthly update', 'project roundup', 'what I'm building'",
    )
    additional_context: Optional[str] = None


class PortfolioGenerateResponse(BaseModel):
    content: str
    platform: str
    draft_id: Optional[uuid.UUID] = None
    projects_included: List[str]  # project names


class DashboardSummaryResponse(BaseModel):
    total_projects: int
    total_drafts: int
    total_syncs: int
    recent_activity: List[dict]
