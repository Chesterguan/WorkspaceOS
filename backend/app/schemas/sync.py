import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SyncRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    triggered_at: datetime
    completed_at: Optional[datetime]
    status: str
    error_message: Optional[str]
    commits_fetched: int
    releases_fetched: int
    readme_changed: bool
    evolution_summary: Optional[str]


class GitHubCommitResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    sync_run_id: uuid.UUID
    sha: str
    message: str
    author_name: Optional[str]
    committed_at: Optional[datetime]
    url: Optional[str]


class GitHubReleaseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    sync_run_id: uuid.UUID
    tag_name: str
    release_name: Optional[str]
    body: Optional[str]
    published_at: Optional[datetime]
    url: Optional[str]
