import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.knowledge import EDGE_TYPES, NODE_TYPES


class SourceRef(BaseModel):
    kind: str = Field(..., description="chat_message | memory_entry | manual | draft | file_ingest")
    id: Optional[str] = None
    excerpt: Optional[str] = None
    note: Optional[str] = None


class KnowledgeNodeOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    node_type: str
    title: str
    content: str
    source_refs: List[SourceRef]
    metadata_: dict = Field(alias="metadata", default_factory=dict)
    archived: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class KnowledgeEdgeOut(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    edge_type: str
    weight: float
    created_at: datetime

    class Config:
        from_attributes = True


class NodeCreateRequest(BaseModel):
    project_id: Optional[uuid.UUID] = None
    node_type: str
    title: str = Field(..., max_length=160)
    content: str
    source_refs: List[SourceRef] = Field(default_factory=list)
    metadata_: dict = Field(alias="metadata", default_factory=dict)

    @field_validator("node_type")
    @classmethod
    def validate_node_type(cls, v: str) -> str:
        if v not in NODE_TYPES:
            raise ValueError(f"node_type must be one of {sorted(NODE_TYPES)}")
        return v


class NodeUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=160)
    content: Optional[str] = None
    node_type: Optional[str] = None
    archived: Optional[bool] = None
    project_id: Optional[uuid.UUID] = None

    @field_validator("node_type")
    @classmethod
    def validate_node_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in NODE_TYPES:
            raise ValueError(f"node_type must be one of {sorted(NODE_TYPES)}")
        return v


class PromoteRequest(BaseModel):
    project_id: Optional[uuid.UUID] = None
    source: SourceRef
    suggested_type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None  # if absent, extractor proposes one


class GraphResponse(BaseModel):
    nodes: List[KnowledgeNodeOut]
    edges: List[KnowledgeEdgeOut]


class SearchResultItem(BaseModel):
    node: KnowledgeNodeOut
    score: float
