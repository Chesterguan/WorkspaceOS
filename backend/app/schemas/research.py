"""
Pydantic schemas for the Research Assistant feature.
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ResearchMessageRequest(BaseModel):
    message: str
    # Context toggles — default True gives the AI the richest possible context
    include_literature: bool = True  # search Semantic Scholar for related papers
    include_workspace: bool = True   # include local workspace snapshot
    include_repo: bool = True        # include GitHub repo context


class PaperSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)


class PaperResult(BaseModel):
    paper_id: str
    title: str
    authors: List[str]
    year: Optional[int] = None
    abstract: Optional[str] = None
    citation_count: int = 0
    url: Optional[str] = None
    doi: Optional[str] = None
    citation_string: str  # pre-formatted citation for display


class PaperSearchResponse(BaseModel):
    papers: List[PaperResult]
    query: str
    total: int


class ResearchMessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    role: str
    content: str
    metadata_: Optional[dict] = None
    created_at: datetime


class ResearchHistoryResponse(BaseModel):
    messages: List[ResearchMessageResponse]
    total: int
