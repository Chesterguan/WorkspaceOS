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
    Trigger a local workspace scan for the project.

    Uses `local_path` from the request body if provided; otherwise falls back
    to the path stored on the project record.  Raises 422 if neither is set.
    Body is optional — sending no body or an empty body is allowed.
    """
    project = await require_owned_project(project_id, db, jwt_user_id)

    local_path = (body.local_path if body else None) or project.local_path
    if not local_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No local_path provided. Either pass 'local_path' in the request body "
                "or set it on the project record first."
            ),
        )

    # Persist the path on the project if it wasn't already stored
    if not project.local_path and local_path:
        project.local_path = local_path
        await db.flush()

    snapshot = await workspace_scanner.perform_scan(project_id, local_path, db)
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
