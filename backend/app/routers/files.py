import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, require_owned_project, verify_api_key
from app.models.memory import MemoryEntry
from app.schemas.files import FileListItem, FileListResponse, FileUploadResponse, ImportUrlRequest
from app.services import file_ingest_service

router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    tags: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> MemoryEntry:
    """Upload a file and ingest it into the project's memory.

    Accepts multipart form data with a file and optional comma-separated tags.
    Max file size: 10 MB.
    """
    await require_owned_project(project_id, db, jwt_user_id)

    content_bytes = await file.read()
    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    # Parse tags from comma-separated string or JSON array
    user_tags: Optional[List[str]] = None
    if tags:
        tags = tags.strip()
        if tags.startswith("["):
            try:
                user_tags = json.loads(tags)
            except json.JSONDecodeError:
                user_tags = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            user_tags = [t.strip() for t in tags.split(",") if t.strip()]

    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "unknown"

    return await file_ingest_service.ingest_file(
        project_id=project_id,
        filename=filename,
        content_bytes=content_bytes,
        source="upload",
        mime_type=mime_type,
        user_tags=user_tags,
        db=db,
    )


@router.post("/import-url", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def import_url(
    project_id: uuid.UUID,
    body: ImportUrlRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> MemoryEntry:
    """Import content from a URL into the project's memory."""
    await require_owned_project(project_id, db, jwt_user_id)

    try:
        return await file_ingest_service.ingest_url(
            project_id=project_id,
            url=body.url,
            user_tags=body.tags,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to fetch URL: {exc}",
        )


@router.get("", response_model=FileListResponse)
async def list_files(
    project_id: uuid.UUID,
    tag: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """List ingested files/URLs for a project. Optional ?tag=X filter."""
    await require_owned_project(project_id, db, jwt_user_id)

    query = (
        select(MemoryEntry)
        .where(MemoryEntry.project_id == project_id)
        .where(MemoryEntry.entry_type.in_(["file", "url"]))
        .order_by(MemoryEntry.created_at.desc())
    )

    if tag:
        query = query.where(
            MemoryEntry.metadata_.op("@>")(cast({"tags": [tag]}, JSONB_TYPE))
        )

    # Get total count before pagination
    count_query = (
        select(MemoryEntry.id)
        .where(MemoryEntry.project_id == project_id)
        .where(MemoryEntry.entry_type.in_(["file", "url"]))
    )
    if tag:
        count_query = count_query.where(
            MemoryEntry.metadata_.op("@>")(cast({"tags": [tag]}, JSONB_TYPE))
        )
    count_result = await db.execute(count_query)
    total = len(count_result.all())

    # Apply pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    entries = list(result.scalars().all())

    # Transform entries into FileListItem format
    files: List[dict] = []
    for entry in entries:
        meta = entry.metadata_ or {}
        files.append(
            FileListItem(
                id=entry.id,
                entry_type=entry.entry_type,
                filename=meta.get("filename", "unknown"),
                source=meta.get("source", "unknown"),
                mime_type=meta.get("mime_type", "application/octet-stream"),
                tags=meta.get("tags", []),
                summary=meta.get("summary", ""),
                file_size=meta.get("file_size", 0),
                created_at=entry.created_at,
            ).model_dump()
        )

    return {"files": files, "total": total}


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    project_id: uuid.UUID,
    memory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> None:
    """Delete a file/URL memory entry."""
    await require_owned_project(project_id, db, jwt_user_id)

    result = await db.execute(
        select(MemoryEntry).where(
            MemoryEntry.id == memory_id,
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type.in_(["file", "url"]),
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File entry not found")

    await db.delete(entry)
    await db.flush()
