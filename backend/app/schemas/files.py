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
