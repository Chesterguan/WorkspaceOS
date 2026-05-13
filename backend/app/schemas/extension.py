"""Extension manifest schema.

An extension is a folder under config/extensions/<id>/ containing:
  - manifest.yaml      — this schema's serialized form
  - personas/cofounder.yaml + research.yaml      (Phase 1: content)
  - taxonomies/extra.yaml                        (Phase 1: content)
  - prompts/worklog/*.txt                        (Phase 1: content)
  - prompts/extraction/*.txt                     (Phase 1: content)
  - capabilities/<name>/                         (Phase 2: code — see below)

The framework ships built-in extensions for common domains (ai-research,
bio-research). Users drop additional folders into the same directory —
extension loader picks them up at boot.

Two layers of extension are designed in:

  Phase 1 — CONTENT extensions (live today):
    Pure YAML/text. Tells the wizard which personas to pick, which
    taxonomy nodes are domain-relevant, which prompt tone to use.

  Phase 2 — CAPABILITY extensions (declared, not yet activated):
    Code that runs inside the host. Things like ingest sources
    (Gmail, Calendar, Slack), slash commands for the ⌘K palette,
    or action buttons on knowledge nodes. Capabilities are declared
    in the manifest's `capabilities` field NOW so the schema is
    stable; the loader stores them as raw dicts and the runtime
    ignores them. Phase 2 adds the activation path without a
    manifest break.

Match heuristics are intentionally simple keyword-overlap scoring so
behavior is predictable. Gemini fallback handles long-tail domains
where heuristics can't help.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# Capability kinds reserved for Phase 2. Listed here so manifest authors
# can write forward-compatible YAML today. The loader passes capability
# entries through verbatim; the host runtime does not yet execute them.
CapabilityKind = Literal[
    "ingest_source",     # external data sync (Gmail, Calendar, Slack, Notion)
    "slash_command",     # ⌘K palette entry
    "action_button",     # context-menu action on a knowledge node / item
    "surface_widget",    # sub-component inside an existing surface
]


class Capability(BaseModel):
    """A Phase 2 capability declaration. Schema is stable; runtime
    behavior arrives in Phase 2.

    Fields beyond `kind`/`name` are intentionally loose (`config: Dict`)
    so capability kinds can evolve their own sub-schemas without
    requiring this top-level type to change.
    """

    kind: CapabilityKind
    name: str = Field(..., description="Stable identifier within the extension.")
    description: Optional[str] = None
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Kind-specific configuration. See docs/extensions.md for the contract per kind.",
    )


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

    # ── Phase 1: content (paths relative to extension folder) ───────────
    personas: Optional[Dict[str, str]] = Field(
        default=None,
        description="Map of pool_id → relative path, e.g. {'cofounder': './personas/cofounder.yaml'}.",
    )
    taxonomy_extra: Optional[str] = Field(
        default=None,
        description="Relative path to a taxonomy yaml whose node_types extend the base set.",
    )
    worklog_templates: Optional[Dict[str, str]] = Field(
        default=None,
        description="Map of cadence → relative path to a worklog prompt override.",
    )

    # ── Phase 2: capabilities (declared, not activated yet) ────────────
    capabilities: List[Capability] = Field(
        default_factory=list,
        description="Phase 2 capability declarations. Schema is stable; runtime "
                    "behavior arrives in a later release. Authors can list "
                    "intended ingest sources / slash commands / action buttons "
                    "now to communicate forward-compatible intent.",
    )
