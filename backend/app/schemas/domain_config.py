"""Pydantic schemas for the domain config files under config/.

Top-level shape:
    DomainConfig
      ├── app: AppConfig
      ├── surfaces: List[SurfaceConfig]
      └── integrations: Dict[str, bool]

Surface configs reference external YAML files via path strings; the loader
resolves those into the matching dataclasses after parsing.
"""
from typing import List, Literal, Optional, Set

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# App-level
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    name: str
    accent: str
    tagline: Optional[str] = None


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

class Persona(BaseModel):
    id: str
    name: str
    color: str
    system_prompt: str
    tagline: Optional[str] = None
    avatar: Optional[str] = None
    expertise: List[str] = Field(default_factory=list)
    # Research-style metadata — present on academic reviewers, optional for cofounders.
    modeled_after: Optional[str] = None
    focus: Optional[str] = None


class PersonaRouting(BaseModel):
    strategy: Literal["smart_select", "all", "manual"] = "smart_select"
    max_concurrent: int = 4


class PersonaPool(BaseModel):
    pool_id: str
    label: str
    mode_label: str
    description: Optional[str] = None
    routing: PersonaRouting = Field(default_factory=PersonaRouting)
    personas: List[Persona]


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

class NodeTypeDef(BaseModel):
    id: str
    label: str
    color: str
    description: Optional[str] = None


class EdgeTypeDef(BaseModel):
    id: str
    label: Optional[str] = None
    stroke: Optional[str] = None
    style: Optional[Literal["solid", "dashed"]] = None


class Taxonomy(BaseModel):
    name: str
    description: Optional[str] = None
    node_types: List[NodeTypeDef]
    edge_types: List[EdgeTypeDef]

    @property
    def node_type_ids(self) -> Set[str]:
        return {n.id for n in self.node_types}

    @property
    def edge_type_ids(self) -> Set[str]:
        return {e.id for e in self.edge_types}


# ---------------------------------------------------------------------------
# Paper type hints
# ---------------------------------------------------------------------------

class PaperTypeHint(BaseModel):
    id: str
    label: str
    hint: str


# ---------------------------------------------------------------------------
# Surfaces
# ---------------------------------------------------------------------------

_SURFACE_TYPES = {"roundtable", "list", "graph", "editor", "report"}


class SurfaceExtractionRefs(BaseModel):
    stage1: Optional[str] = None
    stage2: Optional[str] = None
    taxonomy: Optional[str] = None


class SurfaceTemplatesRefs(BaseModel):
    weekly: Optional[str] = None
    monthly: Optional[str] = None
    quarterly: Optional[str] = None


class SurfaceConfig(BaseModel):
    """One surface entry in scribe.yaml. Path-valued fields are resolved by
    the loader; this schema only validates the raw shape."""
    type: str
    id: str
    letter: str
    label: str
    accent: str
    # Optional refs depending on surface type
    personas: Optional[str] = None
    extraction: Optional[SurfaceExtractionRefs] = None
    taxonomy: Optional[str] = None
    templates: Optional[SurfaceTemplatesRefs] = None
    paper_types: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in _SURFACE_TYPES:
            raise ValueError(f"surface type must be one of {sorted(_SURFACE_TYPES)}")
        return v


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

class DomainConfig(BaseModel):
    app: AppConfig
    surfaces: List[SurfaceConfig]
    integrations: dict = Field(default_factory=dict)
