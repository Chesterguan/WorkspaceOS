# Universal File Ingest Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a universal file ingest pipeline that accepts files from upload or URL, extracts text, auto-generates tags via AI, and stores as enriched memory entries searchable via existing RAG.

**Architecture:** New `file_ingest_service.py` handles text extraction (PDF, markdown, text, code) and AI auto-tagging. New `files` router provides upload/import-url/list/delete endpoints. A JSONB `metadata` column on `memory_entries` stores tags, source, filename, summary. Frontend gets a new "Files" page per project with drag-and-drop upload.

**Tech Stack:** Python 3.9+ (FastAPI UploadFile, PyPDF2, httpx), PostgreSQL JSONB, Next.js 16

**Spec:** `docs/superpowers/specs/2026-04-07-universal-file-ingest-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `backend/app/services/file_ingest_service.py` | Text extraction, AI auto-tagging, ingest pipeline |
| `backend/app/schemas/files.py` | Request/response schemas for file endpoints |
| `backend/app/routers/files.py` | Upload, import-url, list, delete endpoints |
| `backend/alembic/versions/0011_memory_metadata.py` | Add metadata JSONB column to memory_entries |
| `frontend/app/projects/[projectId]/files/page.tsx` | Files page with upload zone and file list |

### Modified files

| File | Changes |
|------|---------|
| `backend/app/models/memory.py` | Add `metadata_` JSONB column |
| `backend/app/requirements.txt` | Add `PyPDF2>=3.0.0` |
| `backend/app/main.py` | Register files router |
| `frontend/lib/types.ts` | Add file-related types |
| `frontend/lib/api.ts` | Add files API methods |
| `frontend/components/ProjectSidebar.tsx` or equivalent | Add "Files" nav link (if sidebar exists) |

---

## Task 1: Migration + Model

**Files:**
- Modify: `backend/app/models/memory.py`
- Create: `backend/alembic/versions/0011_memory_metadata.py`

- [ ] **Step 1: Add metadata_ column to MemoryEntry model**

In `backend/app/models/memory.py`, add after the `context_description` field (before `created_at`):

```python
from sqlalchemy.dialects.postgresql import JSONB

    # Enriched metadata for file ingest (tags, source, filename, summary, etc.)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, name="metadata"
    )
```

Add `JSONB` to the existing `from sqlalchemy.dialects.postgresql import UUID` import line.

- [ ] **Step 2: Create migration**

```python
"""Add metadata JSONB column to memory_entries

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE memory_entries ADD COLUMN IF NOT EXISTS metadata JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE memory_entries DROP COLUMN IF EXISTS metadata")
```

- [ ] **Step 3: Add PyPDF2 to requirements**

Add to `backend/requirements.txt`:
```
PyPDF2>=3.0.0
```

---

## Task 2: File Ingest Service

**Files:**
- Create: `backend/app/services/file_ingest_service.py`

- [ ] **Step 1: Create the service**

```python
"""
Universal file ingest pipeline.

Accepts files from any source (upload, URL), extracts text, auto-generates
tags via AI, and stores as an enriched memory entry with metadata JSONB.
"""
import logging
import uuid
from typing import Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agents import extract_json
from app.services.ai_client import get_cloud_client
from app.services.memory_service import add_entry
from app.models.memory import MemoryEntry

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 50000  # truncate extracted text
MAX_MEMORY_CHARS = 10000   # truncate for memory entry storage
MAX_URL_BYTES = 5 * 1024 * 1024  # 5MB max for URL fetch


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(content_bytes: bytes, mime_type: str) -> str:
    """Extract plain text from file bytes based on mime type.
    
    Supports: PDF, markdown, plain text, code files, HTML.
    Returns truncated text (max MAX_CONTENT_CHARS).
    """
    text = ""

    if mime_type == "application/pdf" or mime_type.endswith("/pdf"):
        text = _extract_pdf(content_bytes)
    elif mime_type.startswith("text/html"):
        text = _extract_html(content_bytes)
    elif mime_type.startswith("text/") or mime_type in (
        "application/json",
        "application/javascript",
        "application/xml",
        "application/x-yaml",
    ):
        try:
            text = content_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    else:
        # Try UTF-8 decode as last resort
        try:
            text = content_bytes.decode("utf-8", errors="replace")
        except Exception:
            logger.warning("extract_text: cannot extract from mime_type=%s", mime_type)
            text = ""

    return text[:MAX_CONTENT_CHARS]


def _extract_pdf(content_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2."""
    try:
        import io
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content_bytes))
        pages: List[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text)
        return "\n\n".join(pages)
    except Exception:
        logger.exception("_extract_pdf: failed to extract text")
        return ""


def _extract_html(content_bytes: bytes) -> str:
    """Strip HTML tags and return plain text."""
    import re
    try:
        html = content_bytes.decode("utf-8", errors="replace")
        # Remove script/style blocks
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# AI auto-tagging
# ---------------------------------------------------------------------------

async def auto_tag(filename: str, text_preview: str, mime_type: str) -> Dict:
    """Generate 3-5 tags and a one-line summary using AI.
    
    Returns {"tags": [...], "summary": "..."}.
    Falls back to {"tags": [], "summary": filename} on failure.
    """
    try:
        ai = get_cloud_client()
        system = (
            "You are a document tagger. Given a file, generate 3-5 descriptive tags "
            "and a one-line summary. Tags should be lowercase, single words or hyphenated.\n"
            "Output ONLY JSON: {\"tags\": [\"tag1\", \"tag2\"], \"summary\": \"one line\"}"
        )
        user = (
            f"Filename: {filename}\n"
            f"Type: {mime_type}\n"
            f"Content preview:\n{text_preview[:500]}"
        )
        raw = await ai.complete(system=system, user=user)
        data = extract_json(raw)
        if data and "tags" in data:
            return {
                "tags": [str(t).lower().strip() for t in data["tags"]][:5],
                "summary": str(data.get("summary", filename))[:200],
            }
    except Exception:
        logger.exception("auto_tag: AI tagging failed for %s", filename)

    return {"tags": [], "summary": filename}


# ---------------------------------------------------------------------------
# Ingest pipeline
# ---------------------------------------------------------------------------

async def ingest_file(
    project_id: uuid.UUID,
    filename: str,
    content_bytes: bytes,
    source: str,
    mime_type: str,
    user_tags: Optional[List[str]],
    db: AsyncSession,
    url: Optional[str] = None,
) -> MemoryEntry:
    """Universal ingest pipeline: extract text → auto-tag → store as memory entry.
    
    Args:
        project_id: The project to store the file in
        filename: Original filename
        content_bytes: Raw file bytes
        source: "upload" | "url"
        mime_type: MIME type of the file
        user_tags: Optional user-provided tags (merged with AI tags)
        db: Database session
        url: Original URL if imported from web
    
    Returns: The created MemoryEntry
    """
    # 1. Extract text
    text = extract_text(content_bytes, mime_type)
    if not text.strip():
        text = f"[Binary file: {filename} ({mime_type}, {len(content_bytes)} bytes)]"

    # 2. Auto-tag
    tag_result = await auto_tag(filename, text, mime_type)
    ai_tags = tag_result["tags"]
    summary = tag_result["summary"]

    # 3. Merge user tags + AI tags (deduplicate)
    all_tags = list(dict.fromkeys((user_tags or []) + ai_tags))

    # 4. Build metadata
    metadata = {
        "source": source,
        "filename": filename,
        "mime_type": mime_type,
        "tags": all_tags,
        "summary": summary,
        "file_size": len(content_bytes),
    }
    if url:
        metadata["url"] = url

    # 5. Store as memory entry (truncated for embedding)
    truncated_content = text[:MAX_MEMORY_CHARS]
    entry_type = "url" if source == "url" else "file"

    entry = await add_entry(
        project_id=project_id,
        entry_type=entry_type,
        content=truncated_content,
        source_ref=url or filename,
        db=db,
    )

    # 6. Attach metadata to the entry
    entry.metadata_ = metadata
    await db.flush()
    await db.refresh(entry)

    logger.info(
        "file_ingest: ingested %s (%s, %d bytes, %d tags) for project %s",
        filename, mime_type, len(content_bytes), len(all_tags), project_id,
    )
    return entry


async def ingest_url(
    project_id: uuid.UUID,
    url: str,
    user_tags: Optional[List[str]],
    db: AsyncSession,
) -> MemoryEntry:
    """Fetch a URL and ingest its content.
    
    Supports HTML pages, PDFs, and plain text URLs.
    """
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "ProjectScribe/1.0"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            if len(resp.content) > MAX_URL_BYTES:
                raise ValueError(f"URL content too large: {len(resp.content)} bytes (max {MAX_URL_BYTES})")

            mime_type = resp.headers.get("content-type", "text/html").split(";")[0].strip()
            filename = url.split("/")[-1].split("?")[0] or "imported_page"

            return await ingest_file(
                project_id=project_id,
                filename=filename,
                content_bytes=resp.content,
                source="url",
                mime_type=mime_type,
                user_tags=user_tags,
                db=db,
                url=url,
            )
    except httpx.HTTPError as exc:
        raise ValueError(f"Failed to fetch URL: {exc}") from exc
```

---

## Task 3: Schemas + Router

**Files:**
- Create: `backend/app/schemas/files.py`
- Create: `backend/app/routers/files.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create schemas**

```python
"""Schemas for the file ingest endpoints."""
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    entry_type: str
    content: str
    metadata_: Optional[dict] = None
    created_at: datetime


class ImportUrlRequest(BaseModel):
    url: str = Field(..., min_length=5)
    tags: Optional[List[str]] = None


class FileListItem(BaseModel):
    id: uuid.UUID
    entry_type: str
    filename: str
    source: str
    mime_type: str
    tags: List[str]
    summary: str
    file_size: int
    created_at: datetime


class FileListResponse(BaseModel):
    files: List[FileListItem]
    total: int
```

- [ ] **Step 2: Create router**

```python
"""File ingest router: upload, import URL, list, and delete files."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.memory import MemoryEntry
from app.models.project import Project
from app.schemas.files import (
    FileListItem,
    FileListResponse,
    FileUploadResponse,
    ImportUrlRequest,
)
from app.services import file_ingest_service

router = APIRouter(
    prefix="/projects/{project_id}/files",
    tags=["files"],
)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file to the project",
)
async def upload_file(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    tags: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> FileUploadResponse:
    """Upload a file (PDF, markdown, text, code). Max 10MB.
    
    Tags are optional, comma-separated. AI will also auto-generate tags.
    """
    await _require_project(project_id, db)

    content_bytes = await file.read()
    if len(content_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {len(content_bytes)} bytes (max {MAX_UPLOAD_SIZE})",
        )

    user_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    mime_type = file.content_type or "application/octet-stream"

    entry = await file_ingest_service.ingest_file(
        project_id=project_id,
        filename=file.filename or "uploaded_file",
        content_bytes=content_bytes,
        source="upload",
        mime_type=mime_type,
        user_tags=user_tags,
        db=db,
    )

    return FileUploadResponse(
        id=entry.id,
        project_id=entry.project_id,
        entry_type=entry.entry_type,
        content=entry.content[:500],
        metadata_=entry.metadata_,
        created_at=entry.created_at,
    )


@router.post(
    "/import-url",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import content from a URL",
)
async def import_url(
    project_id: uuid.UUID,
    body: ImportUrlRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> FileUploadResponse:
    """Fetch content from a URL and ingest it into the project."""
    await _require_project(project_id, db)

    try:
        entry = await file_ingest_service.ingest_url(
            project_id=project_id,
            url=body.url,
            user_tags=body.tags,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return FileUploadResponse(
        id=entry.id,
        project_id=entry.project_id,
        entry_type=entry.entry_type,
        content=entry.content[:500],
        metadata_=entry.metadata_,
        created_at=entry.created_at,
    )


@router.get(
    "",
    response_model=FileListResponse,
    summary="List ingested files",
)
async def list_files(
    project_id: uuid.UUID,
    tag: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> FileListResponse:
    """List all ingested files for the project. Optionally filter by tag."""
    await _require_project(project_id, db)

    query = (
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type.in_(["file", "url"]),
        )
        .order_by(MemoryEntry.created_at.desc())
    )

    if tag:
        # JSONB containment: metadata->'tags' contains the tag
        from sqlalchemy import text, cast
        from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE
        query = query.where(
            MemoryEntry.metadata_.op("@>")(cast({"tags": [tag]}, JSONB_TYPE))
        )

    result = await db.execute(query)
    entries = list(result.scalars().all())

    files = []
    for e in entries:
        meta = e.metadata_ or {}
        files.append(FileListItem(
            id=e.id,
            entry_type=e.entry_type,
            filename=meta.get("filename", "unknown"),
            source=meta.get("source", "unknown"),
            mime_type=meta.get("mime_type", ""),
            tags=meta.get("tags", []),
            summary=meta.get("summary", ""),
            file_size=meta.get("file_size", 0),
            created_at=e.created_at,
        ))

    return FileListResponse(files=files, total=len(files))


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an ingested file",
)
async def delete_file(
    project_id: uuid.UUID,
    memory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> None:
    """Delete a file memory entry."""
    result = await db.execute(
        select(MemoryEntry).where(
            MemoryEntry.id == memory_id,
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type.in_(["file", "url"]),
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    await db.delete(entry)
```

- [ ] **Step 3: Register the router in main.py**

Add to imports:
```python
from app.routers import files as files_router
```

Add to router includes (after memory router):
```python
app.include_router(files_router.router, prefix=API_PREFIX)
```

---

## Task 4: Frontend Types + API

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add types**

In `frontend/lib/types.ts`, add after the `AuthUser` interface:

```typescript
// ─── Files ──────────────────────────────────────────────────────

export interface FileUploadResponse {
  id: string;
  project_id: string;
  entry_type: string;
  content: string;
  metadata_: Record<string, unknown> | null;
  created_at: string;
}

export interface ImportUrlRequest {
  url: string;
  tags?: string[];
}

export interface FileListItem {
  id: string;
  entry_type: string;
  filename: string;
  source: string;
  mime_type: string;
  tags: string[];
  summary: string;
  file_size: number;
  created_at: string;
}

export interface FileListResponse {
  files: FileListItem[];
  total: number;
}
```

- [ ] **Step 2: Add API methods**

Add imports: `FileUploadResponse, ImportUrlRequest, FileListResponse` to the type import block.

Add after the `appSettings` object in `frontend/lib/api.ts`:

```typescript
// ─── Files ───────────────────────────────────────────────────────────────────

export const files = {
  upload(projectId: string, file: globalThis.File, tags?: string): Promise<FileUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (tags) formData.append('tags', tags);

    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    } else if (API_KEY) {
      headers['X-API-Key'] = API_KEY;
    }
    // Do NOT set Content-Type — fetch sets it automatically with boundary for FormData
    return fetch(`${BASE_URL}/projects/${projectId}/files/upload`, {
      method: 'POST',
      headers,
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as Record<string, string>).detail || `Upload failed: ${res.status}`);
      }
      return res.json() as Promise<FileUploadResponse>;
    });
  },
  importUrl(projectId: string, data: ImportUrlRequest): Promise<FileUploadResponse> {
    return apiFetch<FileUploadResponse>(`/projects/${projectId}/files/import-url`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  list(projectId: string, tag?: string): Promise<FileListResponse> {
    const params = tag ? `?tag=${encodeURIComponent(tag)}` : '';
    return apiFetch<FileListResponse>(`/projects/${projectId}/files${params}`);
  },
  delete(projectId: string, memoryId: string): Promise<void> {
    return apiFetch(`/projects/${projectId}/files/${memoryId}`, { method: 'DELETE' });
  },
};
```

Note: The upload method uses raw `fetch` instead of `apiFetch` because `apiFetch` sets `Content-Type: application/json` which conflicts with multipart form data.

---

## Task 5: Frontend Files Page

**Files:**
- Create: `frontend/app/projects/[projectId]/files/page.tsx`

- [ ] **Step 1: Create the files page**

A page with: drag-and-drop upload zone, URL import input, file list with tags.

```tsx
"use client";

import { use, useState, useEffect, useCallback, useRef } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useProjectContext } from "@/components/ProjectContext";
import { files as filesApi } from "@/lib/api";
import { toast } from "sonner";
import { formatDistanceToNow } from "@/lib/utils";
import type { FileListItem, FileListResponse } from "@/lib/types";
import {
  Upload,
  Link as LinkIcon,
  File,
  FileText,
  Code,
  Trash2,
  Loader2,
  ArrowLeft,
  Tag,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

interface FilesPageProps {
  params: Promise<{ projectId: string }>;
}

function fileIcon(mime: string) {
  if (mime.includes("pdf")) return <FileText className="w-4 h-4 text-red-400" />;
  if (mime.includes("markdown") || mime.includes("text")) return <FileText className="w-4 h-4 text-blue-400" />;
  if (mime.includes("javascript") || mime.includes("python") || mime.includes("json"))
    return <Code className="w-4 h-4 text-green-400" />;
  return <File className="w-4 h-4 text-muted-foreground" />;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FilesPage({ params }: FilesPageProps) {
  const { projectId } = use(params);
  const { project } = useProjectContext();

  const { data, mutate, isLoading } = useSWR<FileListResponse>(
    `/projects/${projectId}/files`,
    () => filesApi.list(projectId),
  );

  const [isUploading, setIsUploading] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleUpload(fileList: FileList) {
    setIsUploading(true);
    let uploaded = 0;
    for (const file of Array.from(fileList)) {
      try {
        await filesApi.upload(projectId, file);
        uploaded++;
      } catch (err) {
        toast.error(`Failed to upload ${file.name}`, {
          description: err instanceof Error ? err.message : "Unknown error",
        });
      }
    }
    if (uploaded > 0) {
      toast.success(`${uploaded} file${uploaded > 1 ? "s" : ""} uploaded`);
      await mutate();
    }
    setIsUploading(false);
  }

  async function handleImportUrl() {
    if (!importUrl.trim()) return;
    setIsImporting(true);
    try {
      await filesApi.importUrl(projectId, { url: importUrl.trim() });
      toast.success("URL imported");
      setImportUrl("");
      await mutate();
    } catch (err) {
      toast.error("Import failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsImporting(false);
    }
  }

  async function handleDelete(id: string, filename: string) {
    try {
      await filesApi.delete(projectId, id);
      toast.success(`Deleted ${filename}`);
      await mutate();
    } catch {
      toast.error("Failed to delete file");
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files);
    }
  }

  const fileList = data?.files ?? [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-card shrink-0">
        <Link href={`/projects/${project.id}`}>
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground h-8">
            <ArrowLeft className="w-3.5 h-3.5" />
            {project.name}
          </Button>
        </Link>
        <span className="text-muted-foreground text-sm">/</span>
        <div className="flex items-center gap-2">
          <Upload className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Files</span>
          <Badge variant="outline" className="text-xs">{fileList.length}</Badge>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-4xl mx-auto w-full">
        {/* Upload zone */}
        <div
          className={cn(
            "border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
            isDragOver
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50",
          )}
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept=".pdf,.md,.txt,.py,.js,.ts,.json,.yaml,.yml,.xml,.html,.csv,.tex"
            onChange={(e) => e.target.files && handleUpload(e.target.files)}
          />
          {isUploading ? (
            <Loader2 className="w-8 h-8 mx-auto text-primary animate-spin" />
          ) : (
            <Upload className="w-8 h-8 mx-auto text-muted-foreground" />
          )}
          <p className="mt-2 text-sm font-medium">
            {isUploading ? "Uploading..." : "Drop files here or click to upload"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            PDF, Markdown, Text, Code files. Max 10MB each.
          </p>
        </div>

        {/* URL import */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="Import from URL (arXiv, blog post, documentation...)"
              className="pl-9"
              onKeyDown={(e) => e.key === "Enter" && handleImportUrl()}
            />
          </div>
          <Button
            onClick={handleImportUrl}
            disabled={isImporting || !importUrl.trim()}
          >
            {isImporting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Import"}
          </Button>
        </div>

        {/* File list */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : fileList.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <File className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">No files yet. Upload a PDF or import a URL to get started.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {fileList.map((f) => (
              <Card key={f.id} className="border-border/50 hover:border-border transition-colors">
                <CardContent className="flex items-center gap-3 p-3">
                  {fileIcon(f.mime_type)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate">{f.filename}</p>
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {f.source}
                      </Badge>
                      <span className="text-[11px] text-muted-foreground shrink-0">
                        {formatSize(f.file_size)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{f.summary}</p>
                    {f.tags.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {f.tags.map((t) => (
                          <span key={t} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] bg-secondary text-muted-foreground">
                            <Tag className="w-2.5 h-2.5" />
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <span className="text-[11px] text-muted-foreground shrink-0">
                    {formatDistanceToNow(f.created_at)}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive shrink-0"
                    onClick={() => handleDelete(f.id, f.filename)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

---

## Task 6: Verification

- [ ] **Step 1: Rebuild and run migration**

```bash
docker compose up --build -d backend frontend
```

- [ ] **Step 2: Verify endpoints**

```bash
curl -s http://localhost:8989/openapi.json | python3 -c "import sys,json; paths=json.load(sys.stdin)['paths']; matches=[p for p in paths if 'files' in p]; print(matches)"
```

- [ ] **Step 3: Run test suite**

```bash
docker compose exec backend bash -c "cd /app/tests && python -m pytest test_endpoints.py -v"
```

---

## Summary

| Task | Component | Files | Complexity |
|------|-----------|-------|-----------|
| 1 | Migration + Model | Modify: `memory.py`, Create: `0011_*.py`, Modify: `requirements.txt` | Low |
| 2 | File Ingest Service | Create: `file_ingest_service.py` | High (text extraction + AI tagging) |
| 3 | Schemas + Router | Create: `files.py` (schemas), `files.py` (router), Modify: `main.py` | Medium |
| 4 | Frontend Types + API | Modify: `types.ts`, `api.ts` | Low |
| 5 | Frontend Files Page | Create: `files/page.tsx` | Medium (drag-drop UI) |
| 6 | Verification | No code | Low |

Total: 5 new files, 5 modified files, 1 migration.
