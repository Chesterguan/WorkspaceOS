import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryEntryCreate(BaseModel):
    entry_type: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)
    source_ref: Optional[str] = None


class MemoryEntryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    entry_type: str
    content: str
    source_ref: Optional[str]
    # Embedding is not exposed in the API — it's an internal vector field
    created_at: datetime


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class CrossProjectSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
