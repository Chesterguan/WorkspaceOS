import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, require_owned_project, verify_api_key
from app.schemas.workspace import (
    WorkspaceContextResponse,
    WorkspaceScanRequest,
    WorkspaceSnapshotResponse,
)
from app.services import workspace_scanner

router = APIRouter(prefix="/projects/{project_id}/workspace", tags=["workspace"])


@router.post("/scan", response_model=WorkspaceSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def scan_workspace(
    project_id: uuid.UUID,
    body: Optional[WorkspaceScanRequest] = None,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> WorkspaceSnapshotResponse:
    """
    Trigger a workspace scan for the project.

    Path resolution, in order:
      1. `body.local_path` if the caller pinned one explicitly.
      2. `project.local_path` if it exists on disk (locally-mounted repo).
      3. A persistent shallow clone of `project.github_repo` at `body.branch`
         (or `project.github_branch`) via repo_cache — the remote-only path.

    Raises 422 only when none of the above is achievable (no path, no remote).
    """
    project = await require_owned_project(project_id, db, jwt_user_id)

    requested_path = body.local_path if body else None
    requested_branch = body.branch if body else None
    local_path: Optional[str] = requested_path or project.local_path

    usable_local = bool(local_path) and os.path.isdir(local_path)
    if not usable_local and not project.github_repo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot scan: no valid local_path and no github_repo to clone. "
                "Either pass a 'local_path' that exists on disk, set one on the "
                "project, or connect a GitHub repo."
            ),
        )

    # Only persist an explicit mounted path — never persist the remote-cache
    # fallback directory, because it's branch-scoped and internal.
    if requested_path and usable_local and not project.local_path:
        project.local_path = requested_path
        await db.flush()

    # If the stored/requested path exists, pass it through (fast path); else
    # pass None so the scanner triggers the repo_cache fallback.
    scanner_path: Optional[str] = local_path if usable_local else None

    snapshot = await workspace_scanner.perform_scan(
        project_id,
        scanner_path,
        db,
        project=project,
        branch=requested_branch,
    )
    return snapshot


@router.get("/context", response_model=WorkspaceContextResponse)
async def get_workspace_context(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> WorkspaceContextResponse:
    """Return the latest workspace snapshot as a flat context object."""
    await require_owned_project(project_id, db, jwt_user_id)

    snapshot = await workspace_scanner.get_latest_snapshot(project_id, db)
    if snapshot is None:
        return WorkspaceContextResponse(has_snapshot=False, summary="No workspace scan has been run yet.")

    raw = snapshot.raw_data or {}
    return WorkspaceContextResponse(
        has_snapshot=True,
        summary=snapshot.summary,
        git_branch=snapshot.git_branch,
        git_status=snapshot.git_status,
        uncommitted_changes=raw.get("git_diff"),
        recent_local_commits=raw.get("git_unpushed"),
        file_tree=raw.get("file_tree"),
        key_files=raw.get("key_files"),
        media_assets=raw.get("media_assets"),
    )
