import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def allowed_node_types() -> Optional[set]:
    """Active node-type IDs from the knowledge surface taxonomy.

    Returns None if no taxonomy is configured for the surface — callers should
    treat that as "accept anything" rather than failing closed, so a misconfigured
    or unloaded config doesn't take the API down.
    """
    from app.services.domain_config import get_loader  # avoid import cycle at module load
    try:
        tax = get_loader().get_taxonomy_for_surface("knowledge")
    except (KeyError, RuntimeError):
        return None
    return tax.node_type_ids


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
    # The ORM column is named metadata_ in Python (maps to "metadata" in DB).
    # SQLAlchemy Base also has a .metadata attribute (MetaData()), so we MUST
    # read metadata_ (underscore) from the ORM object and serialize it as
    # "metadata" in JSON output via serialization_alias.
    metadata_: dict = Field(default_factory=dict, serialization_alias="metadata")
    archived: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        # Ensure serialization_alias is used when rendering JSON responses.
        "by_alias": True,
    }

    @model_validator(mode="before")
    @classmethod
    def _coerce_orm_metadata(cls, data: Any) -> Any:
        """When building from an ORM object, copy metadata_ into the field.

        Pydantic from_attributes reads attribute names from the model instance.
        KnowledgeNode.metadata_ holds the user-defined dict; KnowledgeNode.metadata
        (inherited from Base) is the SQLAlchemy MetaData object and must be ignored.
        """
        if hasattr(data, "metadata_") and not isinstance(data, dict):
            # It's an ORM object — return a plain dict so all fields are resolved
            # from attributes directly, bypassing the Base.metadata collision.
            return {
                "id": data.id,
                "user_id": data.user_id,
                "project_id": data.project_id,
                "node_type": data.node_type,
                "title": data.title,
                "content": data.content,
                "source_refs": data.source_refs,
                "metadata_": data.metadata_ or {},
                "archived": data.archived,
                "created_by": data.created_by,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


class KnowledgeEdgeOut(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    edge_type: str
    weight: float
    created_at: datetime

    model_config = {"from_attributes": True}


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
        allowed = allowed_node_types()
        if allowed is not None and v not in allowed:
            raise ValueError(f"node_type must be one of {sorted(allowed)}")
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
        if v is None:
            return v
        allowed = allowed_node_types()
        if allowed is not None and v not in allowed:
            raise ValueError(f"node_type must be one of {sorted(allowed)}")
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


# ---------------------------------------------------------------------------
# Edge creation / linking
# ---------------------------------------------------------------------------

# Canonical edge types across all bio/AI taxonomies.
# We accept these plus any custom types — only reject empty / >40 chars.
_CANONICAL_EDGE_TYPES = {
    "supports", "refutes", "tests", "derived_from", "derives_from",
    "rejects", "related_to", "cites",
}


class EdgeCreateRequest(BaseModel):
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    edge_type: str

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("edge_type must not be empty")
        if len(v) > 40:
            raise ValueError("edge_type must be 40 characters or fewer")
        return v


# ---------------------------------------------------------------------------
# Node links response (GET /knowledge/nodes/{node_id}/links)
# ---------------------------------------------------------------------------

class LinkedEdge(BaseModel):
    """One side of a link: the edge + the other node + direction tag."""
    edge: KnowledgeEdgeOut
    node: KnowledgeNodeOut
    direction: str  # "out" | "in"

    model_config = {"from_attributes": True}


class NodeLinksResponse(BaseModel):
    outgoing: List[LinkedEdge]
    incoming: List[LinkedEdge]
