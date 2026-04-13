import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class WorkspaceScanRequest(BaseModel):
    # If provided, overrides the project's stored local_path for this scan.
    local_path: Optional[str] = None
    # Which git branch to scan. Only meaningful for the repo-cache fallback
    # path (remote-only projects). When omitted, defaults to the project's
    # tracked `github_branch`. Ignored when `local_path` points to a real
    # directory — that scan always reflects whatever is checked out there.
    branch: Optional[str] = None


class WorkspaceSnapshotResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    local_path: str
    summary: str
    raw_data: Optional[dict]
    git_branch: Optional[str]
    git_status: Optional[str]
    git_recent_log: Optional[str]
    scanned_at: datetime


class WorkspaceContextResponse(BaseModel):
    """Flattened workspace context ready for display or inclusion in AI prompts."""

    has_snapshot: bool
    summary: str
    git_branch: Optional[str] = None
    git_status: Optional[str] = None
    # Uncommitted diff (git diff HEAD)
    uncommitted_changes: Optional[str] = None
    # Local commits not yet pushed to remote
    recent_local_commits: Optional[str] = None
    # Two-level directory tree
    file_tree: Optional[str] = None
    # Key config file contents
    key_files: Optional[str] = None
    # Discovered media assets (images, videos, GIFs, diagrams)
    media_assets: Optional[str] = None
