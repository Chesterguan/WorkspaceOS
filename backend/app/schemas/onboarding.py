"""Pydantic models for the onboarding wizard.

The wizard collects 7 answers, posts them to /config/generate, and
receives a preview of the proposed domain config. POST /config/apply
then writes the proposed files to disk and reloads the domain config.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Wizard payload
# ---------------------------------------------------------------------------


class OnboardingAnswers(BaseModel):
    """Raw answers from the 7-question wizard.

    Fields mirror the wizard step order. Optional fields let users skip
    individual questions — the generator backfills sensible defaults.
    """

    domain: str = Field(
        ..., description="Free-text research/work domain, e.g. 'computational biology'.",
        min_length=1, max_length=200,
    )
    primary_outputs: List[str] = Field(
        default_factory=list,
        description="Multi-select: papers, blog_posts, code_releases, internal_reports, social.",
    )
    audience: List[str] = Field(
        default_factory=list,
        description="Multi-select: peer_researchers, customers, investors, internal_team, general_public.",
    )
    advisor_panel: Optional[str] = Field(
        None, max_length=500,
        description="Free-text dream advisor description, or null for AI to choose.",
    )
    tracked_artifacts: Optional[str] = Field(
        None, max_length=500,
        description="Free-text: what user tracks over time (decisions, claims, experiments…).",
    )
    cadence: Optional[Literal["weekly", "monthly", "quarterly", "none"]] = Field(
        None, description="Worklog cadence — null skips worklog surface.",
    )
    stage: Optional[Literal["early", "mid", "late"]] = Field(
        None, description="Optional project stage hint for prompt tone.",
    )


# ---------------------------------------------------------------------------
# Generated config preview
# ---------------------------------------------------------------------------


class PersonaPreview(BaseModel):
    id: str
    name: str
    color: str
    avatar: Optional[str] = None
    system_prompt: str


class PersonaPoolPreview(BaseModel):
    pool_id: str
    label: str
    mode_label: str
    personas: List[PersonaPreview]


class TaxonomyNodePreview(BaseModel):
    id: str
    label: str
    color: str
    description: Optional[str] = None


class TaxonomyEdgePreview(BaseModel):
    id: str
    label: Optional[str] = None


class TaxonomyPreview(BaseModel):
    name: str
    node_types: List[TaxonomyNodePreview]
    edge_types: List[TaxonomyEdgePreview]


class SurfacePreview(BaseModel):
    """Subset of SurfaceConfig — what the preview shows for each surface card."""

    type: str
    id: str
    letter: str
    label: str
    accent: str
    enabled: bool = True


class AppPreview(BaseModel):
    name: str
    tagline: Optional[str] = None
    accent: str


class GeneratedConfig(BaseModel):
    """What POST /config/generate returns — the proposed domain config
    rendered into review-friendly shapes. The wizard's preview pane
    consumes this directly; nothing is written to disk yet."""

    app: AppPreview
    surfaces: List[SurfacePreview]
    persona_pools: List[PersonaPoolPreview]
    taxonomy: TaxonomyPreview
    worklog_templates: Dict[str, str] = Field(default_factory=dict)
    # Raw YAML payloads — kept so /config/apply has the original strings
    # to write to disk verbatim. Frontend doesn't render these; they
    # ride along.
    raw_files: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of relative path (e.g. 'domain.yaml') → yaml/text content.",
    )


# ---------------------------------------------------------------------------
# Apply request
# ---------------------------------------------------------------------------


class ApplyConfigRequest(BaseModel):
    """Wraps the GeneratedConfig.raw_files for /config/apply. Echoing the
    payload back keeps the apply endpoint stateless — if the user
    regenerated client-side or edited fields, what they confirm is what
    we write."""

    raw_files: Dict[str, str]
