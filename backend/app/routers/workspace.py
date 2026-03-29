import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.project import Project
from app.schemas.workspace import (
    WorkspaceContextResponse,
    WorkspaceScanRequest,
    WorkspaceSnapshotResponse,
)
from app.services import workspace_scanner

router = APIRouter(prefix="/projects/{project_id}/workspace", tags=["workspace"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/scan", response_model=WorkspaceSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def scan_workspace(
    project_id: uuid.UUID,
    body: WorkspaceScanRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> WorkspaceSnapshotResponse:
    """
    Trigger a local workspace scan for the project.

    Uses `local_path` from the request body if provided; otherwise falls back
    to the path stored on the project record.  Raises 422 if neither is set.
    """
    project = await _require_project(project_id, db)

    local_path = body.local_path or project.local_path
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
) -> WorkspaceContextResponse:
    """Return the latest workspace snapshot as a flat context object."""
    await _require_project(project_id, db)

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
    )
