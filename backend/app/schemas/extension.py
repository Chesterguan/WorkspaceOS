"""Extension manifest schema.

An extension is a folder under config/extensions/<id>/ containing:
  - manifest.yaml      — this schema's serialized form
  - personas/cofounder.yaml + research.yaml
  - taxonomies/extra.yaml         (optional — additions to base taxonomy)
  - prompts/worklog/*.txt         (optional — overrides for cadence templates)
  - prompts/extraction/*.txt      (optional — domain-tuned extraction prompts)

The framework ships built-in extensions for common domains (ai-research,
bio-research, indie-founder). Users can drop additional folders into the
same directory — extension loader picks them up at boot.

Match heuristics are intentionally simple keyword-overlap scoring so the
behavior is predictable. The Gemini fallback handles long-tail domains
where heuristics can't help.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ExtensionMatches(BaseModel):
    """Heuristic match rules. All fields are optional — an extension with
    empty matches will never auto-select."""

    domain_keywords: List[str] = Field(
        default_factory=list,
        description="Case-insensitive substrings checked against the user's domain text. Any match scores 2 points per hit.",
    )
    audience_any: List[str] = Field(
        default_factory=list,
        description="Wizard audience ids that activate this extension. Any overlap scores 1 point.",
    )
    outputs_any: List[str] = Field(
        default_factory=list,
        description="Wizard primary_outputs that activate this extension. Any overlap scores 1 point.",
    )


class ExtensionManifest(BaseModel):
    """Top-level manifest. Path-valued fields like `personas` are relative
    to the extension folder and resolved by the loader."""

    id: str = Field(..., description="Stable handle, matches folder name.")
    name: str
    description: Optional[str] = None
    version: str = "0.1.0"
    author: str = "workspaceos"
    matches: ExtensionMatches = Field(default_factory=ExtensionMatches)

    # Path refs relative to extension folder. Loader validates each exists.
    personas: Optional[dict] = Field(
        default=None,
        description="Map of pool_id → relative path, e.g. {'cofounder': './personas/cofounder.yaml'}.",
    )
    taxonomy_extra: Optional[str] = Field(
        default=None,
        description="Relative path to a taxonomy yaml whose node_types extend the base set.",
    )
    worklog_templates: Optional[dict] = Field(
        default=None,
        description="Map of cadence → relative path to a worklog prompt override.",
    )
