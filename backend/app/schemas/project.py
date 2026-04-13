import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    focus_notes: Optional[str] = None
    github_repo: Optional[str] = None  # Format: "owner/repo"
    github_branch: str = "main"
    # user_id is optional; if omitted the router falls back to the first user in the DB
    user_id: Optional[uuid.UUID] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    # User-pinned context (commitments, deadlines, current focus). Free-form;
    # empty string clears it, None leaves it unchanged (PATCH semantics).
    focus_notes: Optional[str] = None
    github_repo: Optional[str] = None
    github_branch: Optional[str] = None
    status: Optional[str] = None
    # Local filesystem path for workspace scanning (e.g. /projects/MyApp)
    local_path: Optional[str] = None


class ProjectStatsItem(BaseModel):
    project_id: uuid.UUID
    draft_count: int
    last_sync_at: Optional[datetime]


class ProjectStatsResponse(BaseModel):
    stats: List[ProjectStatsItem]


class ProjectResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    focus_notes: Optional[str]
    github_repo: Optional[str]
    github_branch: str
    local_path: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
