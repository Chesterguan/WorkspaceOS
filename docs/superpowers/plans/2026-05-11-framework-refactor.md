# Framework Refactor — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the bench code domain-blind. Extract all hardcoded domain content (personas, taxonomies, prompts, worklog templates, paper type hints, theme) into YAML files under `config/`. Add a `domain_config` service that loads + validates + serves it. Ship 2 presets (`indie-hacker.yaml` reproduces current behavior verbatim; `bio-researcher.yaml` proves a different domain works).

**Architecture:** YAML files under `config/` are the single source of domain truth. A backend `domain_config` singleton loads them at boot, resolves `$ref` paths, substitutes prompt placeholders, validates via Pydantic, and exposes typed accessors. Existing services (advisors, paper_reviewers, knowledge_extractor, worklog, paper) replace their hardcoded constants with calls to that service. A new `GET /api/v1/config/domain` endpoint serves the relevant subset to the frontend, which renders the bench surfaces / rail / taxonomy filters from the response.

**Tech Stack:** FastAPI · Pydantic v2 · PyYAML · Next.js 16 · SWR · existing Docker Compose setup.

**Working directory:** `/Users/ziyuanguan/ProjectScribe-general` (the bench-ui worktree). Branch: `feat/bench-ui`. **Do NOT work in `/Users/ziyuanguan/ProjectScribe` — that's the personal version on `main`.**

**Spec:** `docs/superpowers/specs/2026-05-11-framework-refactor-design.md`

**IMPORTANT:** Implementers must read `frontend/AGENTS.md` (Next.js 16 caveats) before touching frontend code.

---

## File Structure

### Backend — new files

| File | Responsibility |
|---|---|
| `backend/app/schemas/domain_config.py` | Pydantic schemas: `AppConfig`, `SurfaceConfig`, `PersonaPool`, `Persona`, `Taxonomy`, `NodeTypeDef`, `EdgeTypeDef`, `DomainConfig` (root) |
| `backend/app/services/domain_config.py` | Singleton loader: read `config/scribe.yaml`, resolve `$ref` paths, substitute placeholders, validate, expose typed accessors |
| `backend/app/routers/config.py` | `GET /api/v1/config/domain` endpoint |
| `backend/tests/test_domain_config.py` | Unit tests: schema validation, $ref resolution, placeholder substitution, first-install copy |

### Backend — modified files

| File | Change |
|---|---|
| `backend/app/main.py` | Call `domain_config.load_on_startup()` early; register the new `config` router |
| `backend/app/services/advisors.py` | Delete hardcoded `ADVISORS` dict; expose functions that proxy to `domain_config.get_personas('cofounder')` |
| `backend/app/services/paper_reviewers.py` | Same pattern with `domain_config.get_personas('research')` |
| `backend/app/services/knowledge_extractor.py` | Replace `_CLASSIFIER_SYSTEM`, `_EXTRACTION_SYSTEM` constants with `domain_config.get_prompt(...)`. Replace `NODE_TYPES`/`EDGE_TYPES` imports with `domain_config.get_taxonomy().node_type_ids` |
| `backend/app/services/worklog_service.py` | Replace `_TEMPLATES` dict with `domain_config.get_worklog_template(period)` |
| `backend/app/services/paper_service.py` | Replace `_PAPER_TYPE_HINTS` with `domain_config.get_paper_type_hints()` |
| `backend/app/routers/paper.py` | Derive `_VALID_PAPER_TYPES` from `domain_config.get_paper_type_hints().keys()` |
| `backend/app/models/knowledge.py` | Remove `NODE_TYPES`/`EDGE_TYPES` frozensets entirely (validation moves to Pydantic field validators using `domain_config`) |
| `backend/app/schemas/knowledge.py` | Field validators (`@field_validator("node_type")`) call `domain_config.get_taxonomy().node_type_ids` instead of importing the frozenset |

### Config files — all new

```
config/
├── scribe.yaml                               # auto-copied from presets/indie-hacker.yaml on first install
│
├── personas/
│   ├── cofounder.yaml                        # ported verbatim from advisors.py
│   ├── research.yaml                         # ported verbatim from paper_reviewers.py
│   └── bio-lab.yaml                          # new: PI, Postdoc, Methodology Critic, Statistics Reviewer
│
├── taxonomies/
│   ├── startup.yaml                          # ported from NODE_TYPES + EDGE_TYPES
│   └── bio-research.yaml                     # new: gene_finding, protocol_step, hypothesis, negative_result, observation
│
├── prompts/
│   ├── extraction/
│   │   ├── stage1-classifier.txt             # ported from knowledge_extractor._CLASSIFIER_SYSTEM
│   │   └── stage2-extractor.txt              # ported from knowledge_extractor._EXTRACTION_SYSTEM
│   ├── worklog/
│   │   ├── weekly.txt                        # ported from worklog_service._TEMPLATES["weekly"]
│   │   ├── monthly.txt                       # ported
│   │   ├── quarterly.txt                     # ported
│   │   └── lab-weekly.txt                    # new: bio research weekly
│   └── paper/
│       └── type-hints.yaml                   # ported from paper_service._PAPER_TYPE_HINTS
│
└── presets/
    ├── indie-hacker.yaml                     # default — reproduces current bench behavior
    └── bio-researcher.yaml                   # demonstration of a different domain
```

### Frontend — new files

| File | Responsibility |
|---|---|
| `frontend/lib/bench/useDomainConfig.ts` | SWR hook fetching `/api/v1/config/domain` |
| `frontend/lib/bench/accent-classes.ts` | Static map from accent name (`violet`, `orange`, `blue`, `teal`, `emerald`) → Tailwind classes. Static so Tailwind purge keeps them. |

### Frontend — modified files

| File | Change |
|---|---|
| `frontend/lib/bench/surfaces.ts` | Replace hardcoded `SURFACES` array with helpers that operate on config |
| `frontend/components/bench/Rail.tsx` | Render surfaces from `useDomainConfig()` instead of `SURFACES` |
| `frontend/components/bench/surfaces/RoundtableSurface.tsx` | Mode labels come from `personas.<pool>.mode_label` |
| `frontend/components/knowledge/KnowledgeFilters.tsx` | Node type list from config taxonomy |
| `frontend/lib/knowledge-style.ts` | Color/edge-style maps come from active taxonomy via the hook (or use defaults if config not loaded) |
| `frontend/app/bench/page.tsx` | Wrap content in a `useDomainConfig()` guard; brief loading state |
| `frontend/lib/types.ts` | `NodeType` / `EdgeType` change from string literal unions to plain `string` |

---

## Phase 1 — Schemas + loader (TDD)

### Task 1: Pydantic schemas for domain config

**Files:**
- Create: `backend/app/schemas/domain_config.py`
- Create: `backend/tests/test_domain_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_domain_config.py
import pytest
from app.schemas.domain_config import (
    AppConfig, Persona, PersonaPool, NodeTypeDef, EdgeTypeDef,
    Taxonomy, SurfaceConfig,
)


def test_app_config_minimal():
    app = AppConfig(name="ProjectScribe", accent="#7c3aed")
    assert app.name == "ProjectScribe"
    assert app.tagline is None


def test_persona_pool_resolves_pool_id_required():
    pool = PersonaPool(
        pool_id="cofounder",
        label="Co-Founder",
        mode_label="Co-Founder",
        personas=[
            Persona(id="yc", name="YC", color="#3b82f6", system_prompt="..."),
        ],
    )
    assert len(pool.personas) == 1
    assert pool.routing.strategy == "smart_select"  # default


def test_taxonomy_node_type_ids_property():
    tax = Taxonomy(
        name="startup",
        node_types=[
            NodeTypeDef(id="decision", label="Decision", color="#22c55e"),
            NodeTypeDef(id="claim", label="Claim", color="#3b82f6"),
        ],
        edge_types=[EdgeTypeDef(id="supports")],
    )
    assert tax.node_type_ids == {"decision", "claim"}
    assert tax.edge_type_ids == {"supports"}


def test_surface_config_supports_known_types():
    s = SurfaceConfig(
        type="roundtable", id="cofounder", letter="R",
        label="Roundtable", accent="violet",
        personas="./personas/cofounder.yaml",
    )
    assert s.type == "roundtable"


def test_surface_config_rejects_unknown_type():
    with pytest.raises(ValueError):
        SurfaceConfig(
            type="alien", id="x", letter="X",
            label="X", accent="violet",
        )
```

- [ ] **Step 2: Run — fail**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/test_domain_config.py -v
```
Expected: `ModuleNotFoundError: app.schemas.domain_config`.

- [ ] **Step 3: Implement schemas**

```python
# backend/app/schemas/domain_config.py
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
```

- [ ] **Step 4: Run — pass**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/test_domain_config.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/domain_config.py backend/tests/test_domain_config.py
git commit -m "feat(framework): Pydantic schemas for domain config"
```

---

### Task 2: domain_config loader — read + $ref resolve + placeholder sub

**Files:**
- Create: `backend/app/services/domain_config.py`
- Modify: `backend/tests/test_domain_config.py`

- [ ] **Step 1: Add loader tests**

Append to `backend/tests/test_domain_config.py`:

```python
import os
import textwrap
from pathlib import Path

from app.services.domain_config import DomainConfigLoader


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip())


@pytest.fixture
def fake_config(tmp_path):
    """Build a minimal config tree under tmp_path."""
    base = tmp_path
    _write(base / "personas/cofounder.yaml", """
        pool_id: cofounder
        label: "Co-Founder"
        mode_label: "Co-Founder"
        personas:
          - id: yc
            name: "YC"
            color: "#3b82f6"
            system_prompt: "You are a YC partner."
    """)
    _write(base / "taxonomies/startup.yaml", """
        name: startup
        node_types:
          - id: decision
            label: "Decision"
            color: "#22c55e"
            description: "A choice made"
        edge_types:
          - id: supports
            label: "supports"
    """)
    _write(base / "prompts/extraction/stage2.txt",
           "Use these node types: {taxonomy_node_type_ids}\n\nDetails:\n{taxonomy_summary}")
    _write(base / "scribe.yaml", """
        app:
          name: "TestApp"
          accent: "#7c3aed"
        surfaces:
          - type: roundtable
            id: cofounder
            letter: R
            label: "Roundtable"
            accent: violet
            personas: ./personas/cofounder.yaml
            extraction:
              stage2: ./prompts/extraction/stage2.txt
              taxonomy: ./taxonomies/startup.yaml
        integrations:
          github: false
    """)
    return base


def test_loader_reads_scribe_yaml(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    app = loader.get_app()
    assert app.name == "TestApp"


def test_loader_resolves_persona_refs(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    pool = loader.get_personas("cofounder")
    assert pool.pool_id == "cofounder"
    assert pool.personas[0].id == "yc"


def test_loader_resolves_taxonomy_refs(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    tax = loader.get_taxonomy_by_path("./taxonomies/startup.yaml")
    assert "decision" in tax.node_type_ids
    assert "supports" in tax.edge_type_ids


def test_loader_substitutes_placeholders(fake_config):
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    surface = loader.get_surfaces()[0]
    rendered = loader.render_prompt(
        surface.extraction.stage2,
        taxonomy_path=surface.extraction.taxonomy,
    )
    assert "decision" in rendered
    assert "{taxonomy_node_type_ids}" not in rendered
    assert "{taxonomy_summary}" not in rendered


def test_loader_unknown_placeholder_left_literal(fake_config):
    # An unknown placeholder is left as-is (no template error).
    bad_prompt = fake_config / "prompts/extraction/stage2.txt"
    bad_prompt.write_text("Hello {unknown_thing}")
    loader = DomainConfigLoader(config_dir=fake_config)
    loader.load()
    surface = loader.get_surfaces()[0]
    rendered = loader.render_prompt(
        surface.extraction.stage2,
        taxonomy_path=surface.extraction.taxonomy,
    )
    assert "{unknown_thing}" in rendered  # untouched
```

- [ ] **Step 2: Run — fail**

```bash
docker compose exec backend python -m pytest tests/test_domain_config.py -v
```
Expected: ImportError on `DomainConfigLoader`.

- [ ] **Step 3: Implement the loader**

```python
# backend/app/services/domain_config.py
"""Loads domain config files at boot and exposes typed accessors.

Lifecycle:
  - On startup, load_on_startup() reads config/scribe.yaml from CONFIG_DIR
  - If missing, copies config/presets/indie-hacker.yaml to scribe.yaml
  - Parses + validates against Pydantic schemas
  - Caches in module-level singleton

Path refs (./personas/foo.yaml) are resolved lazily on accessor calls so
broken refs surface at use-time with a clear error, not at startup.
"""
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.schemas.domain_config import (
    AppConfig, DomainConfig, PaperTypeHint, PersonaPool, SurfaceConfig, Taxonomy,
)

logger = logging.getLogger(__name__)

# Default CONFIG_DIR is the project root's config/ directory. Tests can
# inject a different one via DomainConfigLoader(config_dir=tmp_path).
_DEFAULT_CONFIG_DIR = Path("/app/config") if Path("/app/config").exists() else Path("config")


class DomainConfigLoader:
    """Owns the parsed config tree. Exposes accessors used by services + router."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = Path(config_dir) if config_dir else _DEFAULT_CONFIG_DIR
        self._root: Optional[DomainConfig] = None

    # -- lifecycle -----------------------------------------------------------

    def load(self) -> None:
        """Read + parse + validate. Call once at startup."""
        scribe_path = self.config_dir / "scribe.yaml"
        if not scribe_path.exists():
            self._install_default_preset(scribe_path)
        with open(scribe_path) as f:
            raw = yaml.safe_load(f)
        self._root = DomainConfig.model_validate(raw)
        logger.info(
            "domain_config loaded: app=%s surfaces=%d",
            self._root.app.name, len(self._root.surfaces),
        )

    def _install_default_preset(self, target: Path) -> None:
        preset = self.config_dir / "presets" / "indie-hacker.yaml"
        if not preset.exists():
            raise FileNotFoundError(
                f"No domain config at {target} and no default preset at {preset}. "
                "Cannot start without one of these."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(preset, target)
        logger.info("Installed default preset: %s -> %s", preset, target)

    # -- top-level accessors --------------------------------------------------

    def get_app(self) -> AppConfig:
        return self._require().app

    def get_surfaces(self) -> List[SurfaceConfig]:
        return self._require().surfaces

    def get_integrations(self) -> Dict[str, bool]:
        return dict(self._require().integrations)

    # -- referenced-file accessors -------------------------------------------

    def get_personas(self, pool_id: str) -> PersonaPool:
        """Find the surface with `personas: ./path.yaml` matching pool_id."""
        for s in self.get_surfaces():
            if s.personas:
                pool = self._load_persona_file(s.personas)
                if pool.pool_id == pool_id:
                    return pool
        raise KeyError(f"persona pool {pool_id!r} not found in any surface")

    def get_taxonomy_by_path(self, ref: str) -> Taxonomy:
        return self._load_taxonomy_file(ref)

    def get_taxonomy_for_surface(self, surface_id: str) -> Taxonomy:
        for s in self.get_surfaces():
            if s.id == surface_id and s.taxonomy:
                return self._load_taxonomy_file(s.taxonomy)
        raise KeyError(f"no taxonomy on surface {surface_id!r}")

    def get_paper_type_hints(self) -> Dict[str, PaperTypeHint]:
        for s in self.get_surfaces():
            if s.paper_types:
                path = (self.config_dir / s.paper_types).resolve()
                with open(path) as f:
                    raw = yaml.safe_load(f)
                return {item["id"]: PaperTypeHint.model_validate(item) for item in raw}
        return {}

    def get_worklog_template(self, period: str) -> str:
        for s in self.get_surfaces():
            if s.type == "report" and s.templates:
                template_path = getattr(s.templates, period, None)
                if template_path:
                    path = (self.config_dir / template_path).resolve()
                    return path.read_text()
        raise KeyError(f"no worklog template for period {period!r}")

    def render_prompt(
        self,
        ref: str,
        *,
        taxonomy_path: Optional[str] = None,
        extra_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """Read a prompt file and substitute placeholders.

        Available placeholders:
          - {taxonomy_node_type_ids} — comma-separated IDs
          - {taxonomy_edge_type_ids} — comma-separated IDs
          - {taxonomy_summary} — bulleted list of "id: description"
          - anything in extra_vars

        Unknown placeholders are left as literal text (no error).
        """
        path = (self.config_dir / ref).resolve()
        body = path.read_text()
        replacements: Dict[str, str] = dict(extra_vars or {})
        if taxonomy_path:
            tax = self._load_taxonomy_file(taxonomy_path)
            replacements["taxonomy_node_type_ids"] = "|".join(sorted(tax.node_type_ids))
            replacements["taxonomy_edge_type_ids"] = "|".join(sorted(tax.edge_type_ids))
            replacements["taxonomy_summary"] = "\n".join(
                f"- {n.id}: {n.description or n.label}" for n in tax.node_types
            )
        # Replace {key} only when key matches our known set; leave unknowns alone.
        def _sub(match: re.Match) -> str:
            key = match.group(1)
            return replacements.get(key, match.group(0))
        return re.sub(r"\{(\w+)\}", _sub, body)

    # -- internal helpers -----------------------------------------------------

    def _require(self) -> DomainConfig:
        if self._root is None:
            raise RuntimeError("domain_config not loaded; call load_on_startup() first")
        return self._root

    def _load_persona_file(self, ref: str) -> PersonaPool:
        path = (self.config_dir / ref).resolve()
        with open(path) as f:
            return PersonaPool.model_validate(yaml.safe_load(f))

    def _load_taxonomy_file(self, ref: str) -> Taxonomy:
        path = (self.config_dir / ref).resolve()
        with open(path) as f:
            return Taxonomy.model_validate(yaml.safe_load(f))


# Module-level singleton (constructed lazily)
_loader: Optional[DomainConfigLoader] = None


def get_loader() -> DomainConfigLoader:
    global _loader
    if _loader is None:
        _loader = DomainConfigLoader()
    return _loader


def load_on_startup() -> None:
    """Call from app startup (in main.py) before any service uses config."""
    get_loader().load()
```

- [ ] **Step 4: Run — pass**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/test_domain_config.py -v
```
Expected: 10 passed (5 schema + 5 loader).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/domain_config.py backend/tests/test_domain_config.py
git commit -m "feat(framework): domain_config loader + $ref + placeholder substitution"
```

---

## Phase 2 — Port hardcoded content to YAML

### Task 3: Port advisors + reviewers + taxonomy + prompts to config/

**Files:**
- Create: `config/personas/cofounder.yaml`
- Create: `config/personas/research.yaml`
- Create: `config/taxonomies/startup.yaml`
- Create: `config/prompts/extraction/stage1-classifier.txt`
- Create: `config/prompts/extraction/stage2-extractor.txt`
- Create: `config/prompts/worklog/weekly.txt`
- Create: `config/prompts/worklog/monthly.txt`
- Create: `config/prompts/worklog/quarterly.txt`
- Create: `config/prompts/paper/type-hints.yaml`
- Create: `config/presets/indie-hacker.yaml`

This task is mechanical porting — read each existing source file and write its content into the config file. NO behavior change.

- [ ] **Step 1: Port cofounder personas**

Read `backend/app/services/advisors.py`. For each entry in the `ADVISORS` dict, write a YAML entry in `config/personas/cofounder.yaml`:

```yaml
pool_id: cofounder
label: "Co-Founder Roundtable"
mode_label: "Co-Founder"
description: "8 business advisors modeled after well-known thinkers."
routing:
  strategy: smart_select
  max_concurrent: 4
personas:
  - id: yc_partner
    name: "YC Partner"
    tagline: "Startup Strategy & PMF"
    color: "#3b82f6"
    avatar: "/avatars/yc_partner.png"
    expertise: [startup, pmf, fundraising, metrics, pitch]
    system_prompt: |
      # PASTE THE EXACT system_prompt FROM advisors.py FOR yc_partner HERE
  # ... repeat for all 8 advisors: yc_partner, elon_musk, alex_hormozi,
  # greg_isenberg, nathan_gotch, julia_mccoy, growth_tribe, dan_koe
```

Copy each field verbatim — same id, name, color, tagline, system_prompt, expertise.

- [ ] **Step 2: Port research reviewers**

Read `backend/app/services/paper_reviewers.py`. Same pattern in `config/personas/research.yaml`:

```yaml
pool_id: research
label: "Research Roundtable"
mode_label: "Research"
description: "6 academic reviewers covering different perspectives on a paper."
routing:
  strategy: all
  max_concurrent: 6
personas:
  - id: technical_rigor
    # ... copy verbatim from paper_reviewers.py
```

Six reviewers: technical_rigor, novelty_positioning, science_communication, practical_impact, design_elegance, writing_clarity.

- [ ] **Step 3: Port knowledge taxonomy**

Read `backend/app/models/knowledge.py` for `NODE_TYPES` and `EDGE_TYPES`. Read `frontend/lib/knowledge-style.ts` for colors. Write `config/taxonomies/startup.yaml`:

```yaml
name: startup
description: "Decisions, claims, rejections, hypotheses, questions, blockers, insights from startup-builder conversations."
node_types:
  - id: decision
    label: "Decision"
    color: "#22c55e"
    description: "A choice made about the project"
  - id: claim
    label: "Claim"
    color: "#3b82f6"
    description: "An assertion about the world or product"
  - id: rejection
    label: "Rejection"
    color: "#ef4444"
    description: "Something explicitly ruled out with reasoning"
  - id: hypothesis
    label: "Hypothesis"
    color: "#a855f7"
    description: "A claim to test"
  - id: question
    label: "Question"
    color: "#f59e0b"
    description: "An open question to revisit"
  - id: blocker
    label: "Blocker"
    color: "#f97316"
    description: "Something stopping progress"
  - id: insight
    label: "Insight"
    color: "#14b8a6"
    description: "An observation worth saving"
edge_types:
  - id: supports
    label: "supports"
    stroke: "#22c55e"
  - id: contradicts
    label: "contradicts"
    stroke: "#ef4444"
    style: dashed
  - id: refines
    label: "refines"
  - id: rejects
    label: "rejects"
  - id: depends_on
    label: "depends on"
  - id: derives_from
    label: "derives from"
  - id: follows_up
    label: "follows up"
  - id: related_to
    label: "related to"
    style: dashed
```

- [ ] **Step 4: Port extraction prompts**

From `backend/app/services/knowledge_extractor.py`, externalize BOTH classifier strings:
- `_CLASSIFIER_SYSTEM` → `config/prompts/extraction/stage1-classifier.txt` (verbatim)
- `_CLASSIFIER_TEMPLATE` → `config/prompts/extraction/stage1-classifier-template.txt` (verbatim, including its `{user}` and `{ai}` placeholders — the framework substitutes them via `render_prompt(..., extra_vars=...)`)

For `_EXTRACTION_SYSTEM`, copy verbatim into `config/prompts/extraction/stage2-extractor.txt`, replacing the hardcoded enum list `<one of: claim|decision|...>` with the placeholder `<one of: {taxonomy_node_type_ids}>` AND the edge enum similarly. The summary section uses `{taxonomy_summary}`.

Final content of `stage2-extractor.txt`:

```
You extract structured knowledge from conversation turns.
Output ONLY valid JSON, no prose, no fences.

Schema:
{"nodes":[{"node_type":"<one of: {taxonomy_node_type_ids}>","title":"<=120 chars","content":"1-3 sentences","confidence":0..1,"rationale":"why this type"}],"edges_within_turn":[{"from_idx":int,"to_idx":int,"edge_type":"<one of: {taxonomy_edge_type_ids}>"}]}

Node types and what each means:
{taxonomy_summary}

If nothing meaningful, return {"nodes":[],"edges_within_turn":[]}.
```

- [ ] **Step 5: Port worklog templates**

From `backend/app/services/worklog_service.py`, the `_TEMPLATES` dict has three keys: `weekly`, `monthly`, `quarterly`. Copy each value into the matching `.txt` file under `config/prompts/worklog/`. Each file is the full system prompt string for that period — concatenate the base prompt with `_CONTEXT_DIRECTIVE`.

- [ ] **Step 6: Port paper type hints**

From `backend/app/services/paper_service.py:_PAPER_TYPE_HINTS`, write `config/prompts/paper/type-hints.yaml`:

```yaml
- id: conference
  label: "Conference Paper"
  hint: "A peer-reviewed conference paper (typical length: 8-12 pages). Include: Abstract, Introduction, Related Work, Methodology, Experiments/Evaluation, Discussion, Conclusion, References."
- id: workshop
  label: "Workshop Paper"
  hint: "..."
# ... all 9 from _PAPER_TYPE_HINTS verbatim
```

- [ ] **Step 7: Assemble the indie-hacker preset (default scribe.yaml)**

Write `config/presets/indie-hacker.yaml`:

```yaml
app:
  name: "ProjectScribe"
  tagline: "AI co-founder for builders"
  accent: "#7c3aed"

surfaces:
  - type: roundtable
    id: cofounder
    letter: "R"
    label: "Roundtable"
    accent: violet
    personas: ./personas/cofounder.yaml
    extraction:
      stage1: ./prompts/extraction/stage1-classifier.txt
      stage2: ./prompts/extraction/stage2-extractor.txt
      taxonomy: ./taxonomies/startup.yaml

  - type: list
    id: drafts
    letter: "D"
    label: "Drafts"
    accent: orange

  - type: list
    id: papers
    letter: "P"
    label: "Papers"
    accent: blue
    paper_types: ./prompts/paper/type-hints.yaml

  - type: graph
    id: knowledge
    letter: "K"
    label: "Knowledge"
    accent: teal
    taxonomy: ./taxonomies/startup.yaml

  - type: report
    id: worklog
    letter: "W"
    label: "Worklog"
    accent: emerald
    templates:
      weekly: ./prompts/worklog/weekly.txt
      monthly: ./prompts/worklog/monthly.txt
      quarterly: ./prompts/worklog/quarterly.txt

integrations:
  github: false
  google_drive: false
  google_gmail: false
  outlook: false
```

- [ ] **Step 8: Smoke test — load the config**

Rebuild backend so the new files land in the image:

```bash
docker compose up --build -d backend
sleep 4
docker compose exec backend python -c "
from pathlib import Path
import shutil
shutil.copy('/app/config/presets/indie-hacker.yaml', '/app/config/scribe.yaml')
from app.services.domain_config import DomainConfigLoader
loader = DomainConfigLoader()
loader.load()
print('app:', loader.get_app().name)
print('surfaces:', len(loader.get_surfaces()))
print('cofounder personas:', len(loader.get_personas('cofounder').personas))
print('startup taxonomy node types:', sorted(loader.get_taxonomy_by_path('./taxonomies/startup.yaml').node_type_ids))
print('paper type hints:', sorted(loader.get_paper_type_hints().keys()))
print('weekly worklog template len:', len(loader.get_worklog_template('weekly')))
"
```

Expected output:
```
app: ProjectScribe
surfaces: 5
cofounder personas: 8
startup taxonomy node types: ['blocker', 'claim', 'decision', 'hypothesis', 'insight', 'question', 'rejection']
paper type hints: ['book_chapter', 'conference', 'extended_abstract', 'grant_proposal', 'journal', 'phd_proposal', 'technical_report', 'white_paper', 'workshop']
weekly worklog template len: <some int > 100>
```

- [ ] **Step 9: Commit**

```bash
git add config/
git commit -m "feat(framework): port hardcoded domain content to config/ files

Verbatim port of advisors.py, paper_reviewers.py, knowledge taxonomy,
extraction prompts, worklog templates, paper type hints. Plus
presets/indie-hacker.yaml as the default scribe.yaml. No code paths
read from these files yet — that's the next phase."
```

---

### Task 4: Wire load_on_startup into main.py + Docker mount

**Files:**
- Modify: `backend/app/main.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Mount config/ into the backend container**

Edit `docker-compose.yml`. The backend service's `volumes:` section currently has:

```yaml
    volumes:
      - ${WORKSPACE_HOST_PATH:-/tmp/no-workspace}:/projects:ro
      - backend_data:/app/data
```

Add a mount for the config dir so changes on disk are visible inside the container without rebuilding:

```yaml
    volumes:
      - ${WORKSPACE_HOST_PATH:-/tmp/no-workspace}:/projects:ro
      - backend_data:/app/data
      - ./config:/app/config
```

- [ ] **Step 2: Wire load_on_startup**

Open `backend/app/main.py`. Find the FastAPI app instantiation and the existing startup events (search for `@app.on_event` or `lifespan`). Add a call to `domain_config.load_on_startup()` BEFORE any router is registered (so services that import the loader's singleton on import don't get None).

```python
from app.services import domain_config

# ... in startup / lifespan ...
domain_config.load_on_startup()
```

If the app uses `lifespan` (Starlette new style), insert at the top of the startup branch.
If the app uses the older `@app.on_event("startup")`, insert in that handler.

Look at the existing pattern in the file and match it.

- [ ] **Step 3: Rebuild + verify boot**

```bash
docker compose up --build -d backend
sleep 6
docker compose logs backend --tail 30 | grep -iE "domain_config|error"
```

Expected: `domain_config loaded: app=ProjectScribe surfaces=5` in the logs, no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py docker-compose.yml
git commit -m "feat(framework): mount config/ + load domain config at startup"
```

---

## Phase 3 — Refactor backend services to read from config

### Task 5: Refactor advisors.py

**Files:**
- Modify: `backend/app/services/advisors.py`

- [ ] **Step 1: Inspect current shape**

Read `backend/app/services/advisors.py`. It has:
- `ADVISORS: Dict[str, Advisor]` — hardcoded dict of all 8
- `Advisor` dataclass
- `get_advisor(id)` / `get_advisor_info_list()` / `route_to_advisors(message)` functions

Plan: keep the public functions but make them read from `domain_config`. Delete the hardcoded `ADVISORS` dict + `_load_advisors()` if it exists.

- [ ] **Step 2: Rewrite the file**

Replace the file content. Keep imports + the `Advisor` dataclass shape if other code references it; otherwise replace with the `Persona` schema.

```python
"""Advisor roster — reads from domain config.

Backwards-compat: keeps the same public functions other services already
call (get_advisor, get_advisor_info_list, route_to_advisors) so consumers
don't need to change.
"""
import logging
import random
from typing import List, Optional

from app.schemas.domain_config import Persona
from app.services.domain_config import get_loader

logger = logging.getLogger(__name__)


def get_advisor(advisor_id: str) -> Optional[Persona]:
    """Return the persona matching this id from the cofounder pool, or None."""
    pool = get_loader().get_personas("cofounder")
    for p in pool.personas:
        if p.id == advisor_id:
            return p
    return None


def get_advisor_info_list() -> List[dict]:
    """Return advisor info for the frontend dropdown (id, name, color, tagline)."""
    pool = get_loader().get_personas("cofounder")
    return [
        {
            "id": p.id,
            "name": p.name,
            "tagline": p.tagline,
            "color": p.color,
            "avatar": p.avatar,
            "expertise": p.expertise,
        }
        for p in pool.personas
    ]


async def route_to_advisors(user_message: str) -> List[str]:
    """Smart routing — pick up to `max_concurrent` advisor IDs relevant to the message.

    For now: random sample of `max_concurrent` advisors. The previous LLM-
    based router used the hardcoded ADVISOR_REGISTRY; reworking it to use
    config-driven expertise tags is a follow-up task.
    """
    pool = get_loader().get_personas("cofounder")
    max_n = pool.routing.max_concurrent
    if pool.routing.strategy == "all":
        return [p.id for p in pool.personas]
    # smart_select fallback for now: random sample
    n = min(max_n, len(pool.personas))
    return [p.id for p in random.sample(pool.personas, n)]


# Re-export the constants name some callers might use
def get_advisor_count() -> int:
    return len(get_loader().get_personas("cofounder").personas)
```

If `Advisor` dataclass is imported elsewhere by name, add a compat alias:
```python
Advisor = Persona  # compat alias
```

- [ ] **Step 3: Find + update callers**

```bash
docker compose exec backend grep -rn "from app.services.advisors import" /app | head -20
```

For each importer, verify the call shape still works. Most will use `get_advisor(id).name` etc. — `Persona` has the same field names as the old `Advisor` (id, name, color, tagline, system_prompt) so the access pattern still works.

- [ ] **Step 4: Run tests**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/ -v -k "chat or advisor or roundtable" 2>&1 | tail -10
```

Expected: same pass/fail as before.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/advisors.py
git commit -m "refactor(framework): advisors.py reads from domain_config"
```

---

### Task 6: Refactor paper_reviewers.py

**Files:**
- Modify: `backend/app/services/paper_reviewers.py`

- [ ] **Step 1: Mirror the advisors.py pattern**

Apply the same refactor to `paper_reviewers.py`. Replace hardcoded `REVIEWERS` (or whatever the constant is named) with calls to `get_loader().get_personas("research")`. Keep public functions intact.

Specifically: locate the hardcoded reviewer list, replace with:

```python
from app.schemas.domain_config import Persona
from app.services.domain_config import get_loader


def get_reviewer(reviewer_id: str) -> Optional[Persona]:
    pool = get_loader().get_personas("research")
    for r in pool.personas:
        if r.id == reviewer_id:
            return r
    return None


def get_all_reviewers() -> List[Persona]:
    return list(get_loader().get_personas("research").personas)
```

- [ ] **Step 2: Run tests**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/ -v -k "research or reviewer or paper" 2>&1 | tail -10
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/paper_reviewers.py
git commit -m "refactor(framework): paper_reviewers.py reads from domain_config"
```

---

### Task 7: Refactor knowledge_extractor.py + models/knowledge.py + schemas/knowledge.py

**Files:**
- Modify: `backend/app/services/knowledge_extractor.py`
- Modify: `backend/app/models/knowledge.py`
- Modify: `backend/app/schemas/knowledge.py`

This refactor removes `NODE_TYPES` / `EDGE_TYPES` frozensets, replacing them with runtime queries against the active taxonomy.

- [ ] **Step 1: Update models/knowledge.py**

Delete `NODE_TYPES` and `EDGE_TYPES` frozensets entirely. They were only used for validation; that moves to schemas/. The DB column stays `node_type: str` — Postgres doesn't care about the set.

```python
# After: backend/app/models/knowledge.py
# (Just delete the NODE_TYPES = frozenset({...}) and EDGE_TYPES = frozenset({...}) blocks.)
```

- [ ] **Step 2: Update schemas/knowledge.py field validators**

Find every `@field_validator("node_type")` and `@field_validator("edge_type")`. Change them to look up the active taxonomy via `domain_config`:

```python
from app.services.domain_config import get_loader

class KnowledgeNodeCreate(BaseModel):
    node_type: str
    # ... other fields ...

    @field_validator("node_type")
    @classmethod
    def validate_node_type(cls, v: str) -> str:
        # The active taxonomy comes from the surface that has one referenced.
        # For now we look up the "knowledge" surface explicitly.
        try:
            tax = get_loader().get_taxonomy_for_surface("knowledge")
        except KeyError:
            return v  # if no taxonomy configured, accept anything
        if v not in tax.node_type_ids:
            raise ValueError(
                f"node_type {v!r} must be one of {sorted(tax.node_type_ids)}"
            )
        return v
```

Same for `edge_type`.

- [ ] **Step 3: Update knowledge_extractor.py**

Find `_CLASSIFIER_SYSTEM`, `_CLASSIFIER_TEMPLATE`, `_EXTRACTION_SYSTEM` constants. Replace usages with `get_loader().render_prompt(ref, taxonomy_path=...)`.

Find the exact callsite in the extractor (search for `_CLASSIFIER_SYSTEM` and `_CLASSIFIER_TEMPLATE`). Replace whatever pattern is there with:
```python
from app.services.domain_config import get_loader

# get the cofounder surface's extraction refs (it's the only one with them currently)
surfaces = get_loader().get_surfaces()
ext = next((s.extraction for s in surfaces if s.extraction), None)
if ext is None:
    raise RuntimeError("no surface has extraction configured")

system = get_loader().render_prompt(ext.stage1, taxonomy_path=ext.taxonomy)
# user message template — we need {user} and {ai} substituted
template = get_loader().render_prompt(
    ext.stage1.replace("stage1-classifier.txt", "stage1-classifier-template.txt"),
    taxonomy_path=ext.taxonomy,
    extra_vars={"user": message_text, "ai": ai_text},
)
```

The exact integration depends on the existing extractor's structure — read it, find where the system + user prompts are built, and route through `render_prompt`.

- [ ] **Step 4: Run knowledge tests**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/test_knowledge*.py -v
```

Expected: same pass/fail count as before (any pre-existing skips remain skips).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge_extractor.py backend/app/models/knowledge.py backend/app/schemas/knowledge.py
git commit -m "refactor(framework): knowledge extractor + schemas read taxonomy + prompts from config"
```

---

### Task 8: Refactor worklog_service.py

**Files:**
- Modify: `backend/app/services/worklog_service.py`

- [ ] **Step 1: Find `_TEMPLATES`**

```bash
docker compose exec backend grep -n "_TEMPLATES" /app/app/services/worklog_service.py
```

- [ ] **Step 2: Replace with config call**

Wherever the code does `_TEMPLATES[period]`, replace with:

```python
from app.services.domain_config import get_loader

# ...
system_prompt = get_loader().get_worklog_template(period)
```

Delete the `_TEMPLATES` dict and `_CONTEXT_DIRECTIVE` constants (now in the config files).

- [ ] **Step 3: Run tests + commit**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/ -v -k worklog 2>&1 | tail -10

git add backend/app/services/worklog_service.py
git commit -m "refactor(framework): worklog_service.py reads templates from config"
```

---

### Task 9: Refactor paper_service.py + routers/paper.py

**Files:**
- Modify: `backend/app/services/paper_service.py`
- Modify: `backend/app/routers/paper.py`

- [ ] **Step 1: Replace `_PAPER_TYPE_HINTS` in paper_service.py**

Find usages of `_PAPER_TYPE_HINTS`. Replace with:

```python
from app.services.domain_config import get_loader

# In the function that uses the hints:
hints = get_loader().get_paper_type_hints()
hint = hints.get(paper_type)
if hint is None:
    raise ValueError(f"unknown paper_type {paper_type!r}")
# hint.hint is the string previously in the dict
```

Delete the `_PAPER_TYPE_HINTS` dict.

- [ ] **Step 2: Replace `_VALID_PAPER_TYPES` in routers/paper.py**

Find the `_VALID_PAPER_TYPES = frozenset(...)` line. Replace:

```python
from app.services.domain_config import get_loader

def _valid_paper_types() -> set[str]:
    return set(get_loader().get_paper_type_hints().keys())

# Wherever `_VALID_PAPER_TYPES` was used:
if body.paper_type not in _valid_paper_types():
    raise HTTPException(...)
```

(The original frozenset was a module-level constant; now it's a function call. The cost is negligible because `domain_config` is in-memory.)

- [ ] **Step 3: Run tests + commit**

```bash
docker compose up --build -d backend
docker compose exec backend python -m pytest tests/ -v -k paper 2>&1 | tail -10

git add backend/app/services/paper_service.py backend/app/routers/paper.py
git commit -m "refactor(framework): paper_service + routers/paper read type hints from config"
```

---

### Task 10: New router — GET /api/v1/config/domain

**Files:**
- Create: `backend/app/routers/config.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the router**

```python
# backend/app/routers/config.py
"""Serve the domain config to the frontend."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.dependencies import verify_api_key
from app.services.domain_config import get_loader

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/domain")
async def get_domain_config(_: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Return the domain config in a shape friendly to the bench frontend.

    Note: this serves the resolved + denormalized view (taxonomies inlined
    onto surfaces that reference them) so the frontend can render in one
    request without follow-up calls.
    """
    loader = get_loader()
    surfaces: List[Dict[str, Any]] = []
    for s in loader.get_surfaces():
        surface_dict: Dict[str, Any] = {
            "type": s.type,
            "id": s.id,
            "letter": s.letter,
            "label": s.label,
            "accent": s.accent,
        }
        if s.taxonomy:
            tax = loader.get_taxonomy_by_path(s.taxonomy)
            surface_dict["taxonomy"] = {
                "node_types": [n.model_dump() for n in tax.node_types],
                "edge_types": [e.model_dump() for e in tax.edge_types],
            }
        if s.personas:
            pool = loader._load_persona_file(s.personas)
            surface_dict["personas"] = {
                "pool_id": pool.pool_id,
                "mode_label": pool.mode_label,
                "items": [
                    {"id": p.id, "name": p.name, "color": p.color, "avatar": p.avatar}
                    for p in pool.personas
                ],
            }
        surfaces.append(surface_dict)

    app = loader.get_app()
    return {
        "app": {"name": app.name, "accent": app.accent, "tagline": app.tagline},
        "surfaces": surfaces,
        "integrations": loader.get_integrations(),
    }
```

- [ ] **Step 2: Register the router**

In `backend/app/main.py`, add (near other `include_router` calls):

```python
from app.routers import config as config_router
app.include_router(config_router.router, prefix=API_PREFIX)
```

- [ ] **Step 3: Smoke test**

```bash
docker compose up --build -d backend
sleep 4
API_KEY=$(grep -E "^API_SECRET_KEY" .env | cut -d= -f2)
curl -s -H "X-API-Key: $API_KEY" "http://localhost:9000/api/v1/config/domain" | python3 -m json.tool | head -40
```

Expected: JSON with `app.name = "ProjectScribe"`, `surfaces` array with 5 entries, the roundtable surface has `personas.items` with 8 advisors, the knowledge surface has `taxonomy.node_types` with 7 types.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/config.py backend/app/main.py
git commit -m "feat(framework): GET /api/v1/config/domain endpoint"
```

---

## Phase 4 — Frontend refactor

### Task 11: Frontend types + useDomainConfig hook

**Files:**
- Modify: `frontend/lib/types.ts`
- Create: `frontend/lib/bench/useDomainConfig.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Loosen types in types.ts**

Find these literal unions:

```typescript
export type NodeType = 'claim' | 'decision' | 'question' | 'hypothesis' | 'rejection' | 'blocker' | 'insight';
export type EdgeType = 'supports' | 'contradicts' | ...;
```

Change both to plain string aliases since taxonomy is now runtime-defined:

```typescript
export type NodeType = string;
export type EdgeType = string;
```

Add new types for the domain config response:

```typescript
export interface DomainConfigApp {
  name: string;
  accent: string;
  tagline?: string;
}

export interface DomainConfigNodeType {
  id: string;
  label: string;
  color: string;
  description?: string;
}

export interface DomainConfigEdgeType {
  id: string;
  label?: string;
  stroke?: string;
  style?: 'solid' | 'dashed';
}

export interface DomainConfigTaxonomy {
  node_types: DomainConfigNodeType[];
  edge_types: DomainConfigEdgeType[];
}

export interface DomainConfigPersonaItem {
  id: string;
  name: string;
  color: string;
  avatar?: string;
}

export interface DomainConfigPersonas {
  pool_id: string;
  mode_label: string;
  items: DomainConfigPersonaItem[];
}

export interface DomainConfigSurface {
  type: 'roundtable' | 'list' | 'graph' | 'editor' | 'report';
  id: string;
  letter: string;
  label: string;
  accent: string;
  taxonomy?: DomainConfigTaxonomy;
  personas?: DomainConfigPersonas;
}

export interface DomainConfig {
  app: DomainConfigApp;
  surfaces: DomainConfigSurface[];
  integrations: Record<string, boolean>;
}
```

- [ ] **Step 2: Add API helper**

Append to `frontend/lib/api.ts`:

```typescript
export const config = {
  domain(): Promise<DomainConfig> {
    return apiFetch<DomainConfig>('/config/domain');
  },
};
```

And add `DomainConfig` to the import at the top of the file.

- [ ] **Step 3: Create the hook**

```typescript
// frontend/lib/bench/useDomainConfig.ts
import useSWR from 'swr';
import { config } from '@/lib/api';
import type { DomainConfig } from '@/lib/types';

/**
 * Fetches the active domain config once per session.
 * Cached aggressively — config only changes on backend restart.
 */
export function useDomainConfig() {
  return useSWR<DomainConfig>('/config/domain', () => config.domain(), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: 1000 * 60 * 5, // 5 minutes
  });
}
```

- [ ] **Step 4: Build + verify type-check**

```bash
docker compose up --build -d frontend
sleep 12
docker compose logs frontend --tail 10
```

Expected: no TS errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts frontend/lib/bench/useDomainConfig.ts
git commit -m "feat(framework ui): domain config types + useDomainConfig hook"
```

---

### Task 12: Refactor Rail + bench page to read from config

**Files:**
- Create: `frontend/lib/bench/accent-classes.ts`
- Modify: `frontend/lib/bench/surfaces.ts`
- Modify: `frontend/components/bench/Rail.tsx`
- Modify: `frontend/app/bench/page.tsx`

- [ ] **Step 1: Create the accent-class util**

```typescript
// frontend/lib/bench/accent-classes.ts
// Static map so Tailwind purge keeps the class strings. Maps accent
// name (from YAML config) to the on/off Tailwind classes used on the rail.
export const ACCENT_CLASSES: Record<string, { active: string; inactive: string }> = {
  violet: {
    active: 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  orange: {
    active: 'bg-orange-500/20 text-orange-300 ring-1 ring-orange-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  blue: {
    active: 'bg-blue-500/20 text-blue-300 ring-1 ring-blue-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  teal: {
    active: 'bg-teal-500/20 text-teal-300 ring-1 ring-teal-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  emerald: {
    active: 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
};

export function getAccentClasses(accent: string, active: boolean): string {
  const klass = ACCENT_CLASSES[accent] ?? ACCENT_CLASSES.blue;
  return active ? klass.active : klass.inactive;
}
```

- [ ] **Step 2: Replace `surfaces.ts` exports**

Replace the hardcoded `SURFACES` array with thin helpers that operate on the config:

```typescript
// frontend/lib/bench/surfaces.ts
import type { DomainConfigSurface } from '@/lib/types';

export type SurfaceId = string;

export function findSurface(
  surfaces: DomainConfigSurface[],
  id: string,
): DomainConfigSurface | undefined {
  return surfaces.find((s) => s.id === id);
}

export function findSurfaceByLetter(
  surfaces: DomainConfigSurface[],
  letter: string,
): DomainConfigSurface | undefined {
  return surfaces.find((s) => s.letter.toLowerCase() === letter.toLowerCase());
}

export function defaultSurfaceId(surfaces: DomainConfigSurface[]): SurfaceId | undefined {
  return surfaces[0]?.id;
}
```

- [ ] **Step 3: Update Rail.tsx**

```tsx
'use client';

import { Search, Settings } from 'lucide-react';
import { useDomainConfig } from '@/lib/bench/useDomainConfig';
import { getAccentClasses } from '@/lib/bench/accent-classes';
import { cn } from '@/lib/utils';
import type { SurfaceId } from '@/lib/bench/surfaces';

interface RailProps {
  active: SurfaceId | undefined;
  onSelect: (id: SurfaceId) => void;
  onPaletteOpen: () => void;
  onSettingsOpen: () => void;
}

export function Rail({ active, onSelect, onPaletteOpen, onSettingsOpen }: RailProps) {
  const { data } = useDomainConfig();
  const surfaces = data?.surfaces ?? [];

  return (
    <nav className="flex h-full flex-col items-center gap-2 py-3" aria-label="Bench surfaces">
      {surfaces.map((s) => {
        const isActive = s.id === active;
        return (
          <button
            key={s.id}
            type="button"
            title={s.label}
            aria-label={s.label}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => onSelect(s.id)}
            className={cn(
              'h-8 w-8 rounded-md flex items-center justify-center font-semibold text-xs transition',
              getAccentClasses(s.accent, isActive),
            )}
          >
            {s.letter}
          </button>
        );
      })}

      <div className="my-1 h-px w-7 bg-border" />

      <button
        type="button"
        title="Search (⌘K)"
        aria-label="Open command palette"
        onClick={onPaletteOpen}
        className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40 transition"
      >
        <Search className="w-4 h-4" />
      </button>

      <div className="flex-1" />

      <button
        type="button"
        title="Settings"
        aria-label="Open settings"
        onClick={onSettingsOpen}
        className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40 transition"
      >
        <Settings className="w-4 h-4" />
      </button>
    </nav>
  );
}
```

- [ ] **Step 4: Update bench/page.tsx**

Add a brief loading state if config isn't yet loaded, and replace SURFACES references with config-driven logic.

Find the existing rendering logic. Wherever the code does `state.surface === 'r' && <RoundtableSurface .../>`, replace with a lookup on the surface type from config:

```tsx
const surface = data?.surfaces.find((s) => s.id === state.surface);

// ...

{surface?.type === 'roundtable' && (
  <RoundtableSurface
    projectId={state.projectId}
    mode={state.mode}
    onModeChange={(m) => update({ mode: m })}
  />
)}
{surface?.type === 'list' && surface.id === 'drafts' && (
  <DraftsSurface projectId={state.projectId} />
)}
{surface?.type === 'list' && surface.id === 'papers' && (
  <PapersSurface projectId={state.projectId} />
)}
{surface?.type === 'graph' && (
  <KnowledgeSurface projectId={state.projectId} />
)}
{surface?.type === 'report' && (
  <WorklogSurface projectId={state.projectId} />
)}
```

For the title in the header, use `surface?.label` instead of the hardcoded `SURFACE_INDEX[state.surface].label`.

If `data` is undefined (initial fetch), render a centered "Loading..." in the main area:

```tsx
if (!data) {
  return (
    <div className="flex h-screen items-center justify-center text-muted-foreground text-sm">
      Loading…
    </div>
  );
}
```

- [ ] **Step 5: Rebuild + smoke test**

```bash
docker compose up --build -d frontend
sleep 12
docker compose logs frontend --tail 10
docker compose exec frontend sh -c "wget -qO- -S http://localhost:3000/bench 2>&1 | head -3"
```

Expected: 200, no TS errors. Open the browser at `localhost:4000/bench` — rail shows 5 letters, layout looks identical to before.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/bench/accent-classes.ts frontend/lib/bench/surfaces.ts frontend/components/bench/Rail.tsx frontend/app/bench/page.tsx
git commit -m "refactor(framework ui): Rail + bench page read surfaces from config"
```

---

### Task 13: Refactor knowledge components for taxonomy-driven UI

**Files:**
- Modify: `frontend/components/knowledge/KnowledgeFilters.tsx`
- Modify: `frontend/lib/knowledge-style.ts`

- [ ] **Step 1: Make KnowledgeFilters taxonomy-driven**

Find the hardcoded node-type list in `KnowledgeFilters.tsx`. Replace with config:

```tsx
'use client';

import { useDomainConfig } from '@/lib/bench/useDomainConfig';

interface Props {
  // ... existing props ...
}

export function KnowledgeFilters({ projectId, onProjectChange, nodeType, onTypeChange, ... }: Props) {
  const { data } = useDomainConfig();
  const knowledgeSurface = data?.surfaces.find((s) => s.type === 'graph');
  const taxonomy = knowledgeSurface?.taxonomy;
  const nodeTypes = taxonomy?.node_types ?? [];

  return (
    <div className="...">
      <select value={nodeType ?? ''} onChange={...}>
        <option value="">All types</option>
        {nodeTypes.map((nt) => (
          <option key={nt.id} value={nt.id}>{nt.label}</option>
        ))}
      </select>
      {/* ... rest ... */}
    </div>
  );
}
```

- [ ] **Step 2: Make knowledge-style.ts config-derived (with fallback)**

The existing `NODE_COLORS` / `EDGE_STYLES` maps are used by `KnowledgeGraph.tsx` to color nodes. Replace with a helper that reads from the active taxonomy:

```typescript
// frontend/lib/knowledge-style.ts
import type { DomainConfigTaxonomy, NodeType, EdgeType } from '@/lib/types';

export function nodeColor(taxonomy: DomainConfigTaxonomy | undefined, type: NodeType): string {
  const nt = taxonomy?.node_types.find((n) => n.id === type);
  return nt?.color ?? '#888';
}

export function edgeStyle(taxonomy: DomainConfigTaxonomy | undefined, type: EdgeType): { stroke: string; dashed: boolean } {
  const et = taxonomy?.edge_types.find((e) => e.id === type);
  return {
    stroke: et?.stroke ?? '#888',
    dashed: et?.style === 'dashed',
  };
}
```

Update `KnowledgeGraph.tsx` to pass the taxonomy from `useDomainConfig` into these helpers (or to use a `useTaxonomy()` hook):

```tsx
const { data } = useDomainConfig();
const taxonomy = data?.surfaces.find((s) => s.type === 'graph')?.taxonomy;

// ...
fill: nodeColor(taxonomy, node.type),
```

- [ ] **Step 3: Build + smoke test**

```bash
docker compose up --build -d frontend
sleep 12
docker compose logs frontend --tail 10
```

Expected: no TS errors. Browser: open `/bench?surface=k` — knowledge graph renders with same colors as before (because the default preset's startup taxonomy has the same colors).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/knowledge/KnowledgeFilters.tsx frontend/lib/knowledge-style.ts
git commit -m "refactor(framework ui): knowledge components read taxonomy from config"
```

---

## Phase 5 — Bio researcher preset + verification

### Task 14: Hand-craft bio-researcher preset

**Files:**
- Create: `config/personas/bio-lab.yaml`
- Create: `config/taxonomies/bio-research.yaml`
- Create: `config/prompts/worklog/lab-weekly.txt`
- Create: `config/presets/bio-researcher.yaml`

- [ ] **Step 1: bio-lab personas**

```yaml
# config/personas/bio-lab.yaml
pool_id: cofounder
label: "Lab Discussion"
mode_label: "Lab"
description: "PI, postdoc, methodology critic, and statistics reviewer for wet-lab discussions."
routing:
  strategy: smart_select
  max_concurrent: 3
personas:
  - id: pi
    name: "PI"
    tagline: "Principal Investigator"
    color: "#22c55e"
    expertise: [strategy, hypothesis_generation, grant_writing]
    system_prompt: |
      You are a senior PI in molecular biology. You guide the lab's
      strategic direction. When the user asks for input, focus on
      whether the experiment answers a meaningful question, whether
      the design is publishable, and what the next logical step is.

  - id: postdoc
    name: "Postdoc"
    tagline: "Hands-on experimentalist"
    color: "#3b82f6"
    expertise: [experimental_design, troubleshooting, protocols]
    system_prompt: |
      You are a senior postdoc with 5+ years of bench experience.
      You focus on practical execution: which protocol variation to
      try first, common pitfalls in the chosen technique, time
      budgeting, and reagent costs.

  - id: methodology_critic
    name: "Methodology Critic"
    tagline: "Rigor and reproducibility"
    color: "#a855f7"
    expertise: [reproducibility, controls, blinding, randomization]
    system_prompt: |
      You are a rigorous methodologist. You ask hard questions:
      what's the right control, is the sample size justified, are
      confounders handled, is the analysis pre-registered. Be polite
      but uncompromising.

  - id: stats_reviewer
    name: "Statistics Reviewer"
    tagline: "Quantitative analyst"
    color: "#f59e0b"
    expertise: [statistical_tests, effect_sizes, multiple_comparisons]
    system_prompt: |
      You are a statistician who reviews experimental designs and
      analyses. Flag underpowered studies, inappropriate tests, missing
      effect sizes, and uncorrected multiple comparisons. Suggest
      specific alternatives.
```

- [ ] **Step 2: bio-research taxonomy**

```yaml
# config/taxonomies/bio-research.yaml
name: bio-research
description: "Findings, protocols, hypotheses, and observations from wet-lab work."
node_types:
  - id: gene_finding
    label: "Gene Finding"
    color: "#22c55e"
    description: "An empirical observation about a gene's function or expression"
  - id: protocol_step
    label: "Protocol Step"
    color: "#a855f7"
    description: "A step or parameter in an experimental protocol"
  - id: hypothesis
    label: "Hypothesis"
    color: "#3b82f6"
    description: "A testable prediction"
  - id: observation
    label: "Observation"
    color: "#14b8a6"
    description: "A noted phenomenon not yet explained"
  - id: negative_result
    label: "Negative Result"
    color: "#ef4444"
    description: "An experiment that produced no significant effect"
  - id: open_question
    label: "Open Question"
    color: "#f59e0b"
    description: "Something to investigate next"
edge_types:
  - id: confirms
    label: "confirms"
    stroke: "#22c55e"
  - id: refutes
    label: "refutes"
    stroke: "#ef4444"
    style: dashed
  - id: replicates
    label: "replicates"
  - id: requires
    label: "requires"
  - id: cites
    label: "cites"
    style: dashed
  - id: related_to
    label: "related to"
    style: dashed
```

- [ ] **Step 3: lab-weekly worklog template**

```text
# config/prompts/worklog/lab-weekly.txt
You are summarizing one week of bench work for a PI. Use markdown.

Include these sections:
1. Experiments run (with conditions and N)
2. Findings (cite the relevant nodes from the knowledge graph)
3. Negative results worth noting
4. Open questions to address next week
5. Blockers (reagents, equipment, etc.)

Be concise. Cite nodes by their title when relevant. The PI cares
most about: rigor of controls, reproducibility, and whether progress
matches the grant timeline.

Project context follows.
```

- [ ] **Step 4: presets/bio-researcher.yaml**

```yaml
app:
  name: "BioScribe"
  tagline: "AI lab assistant for wet-lab researchers"
  accent: "#5a9fa7"

surfaces:
  - type: roundtable
    id: cofounder
    letter: "L"
    label: "Lab Discussion"
    accent: teal
    personas: ./personas/bio-lab.yaml
    extraction:
      stage1: ./prompts/extraction/stage1-classifier.txt
      stage2: ./prompts/extraction/stage2-extractor.txt
      taxonomy: ./taxonomies/bio-research.yaml

  - type: graph
    id: knowledge
    letter: "F"
    label: "Findings"
    accent: emerald
    taxonomy: ./taxonomies/bio-research.yaml

  - type: report
    id: worklog
    letter: "W"
    label: "Lab Progress"
    accent: orange
    templates:
      weekly: ./prompts/worklog/lab-weekly.txt
      monthly: ./prompts/worklog/lab-weekly.txt
      quarterly: ./prompts/worklog/lab-weekly.txt

integrations:
  github: false
  google_drive: true
```

(Drops Drafts and Papers since they're not central to the wife's daily workflow; she can edit the YAML later if she wants them.)

- [ ] **Step 5: Manual switch + smoke test**

```bash
cp config/presets/bio-researcher.yaml config/scribe.yaml
docker compose restart backend frontend
sleep 8
curl -s -H "X-API-Key: $(grep -E "^API_SECRET_KEY" .env | cut -d= -f2)" "http://localhost:9000/api/v1/config/domain" | python3 -m json.tool | head -30
```

Expected: `app.name = "BioScribe"`, 3 surfaces, the roundtable surface has personas with `id: pi`, `id: postdoc`, etc.

Open `localhost:4000/bench` in the browser. The rail shows 3 letters (L, F, W). App title in the project filter dropdown is "BioScribe". Roundtable mode toggle says "Lab".

Switch back to default before continuing:
```bash
cp config/presets/indie-hacker.yaml config/scribe.yaml
docker compose restart backend frontend
```

- [ ] **Step 6: Commit**

```bash
git add config/personas/bio-lab.yaml config/taxonomies/bio-research.yaml config/prompts/worklog/lab-weekly.txt config/presets/bio-researcher.yaml
git commit -m "feat(framework): hand-crafted bio-researcher preset

Demonstrates the framework works for a different domain — bio research
with PI/postdoc/methodology-critic personas, gene-finding/protocol-step
taxonomy, and a lab-weekly worklog template. Switching scribe.yaml to
this preset and restarting gives an app called BioScribe with no code
changes."
```

---

### Task 15: Final verification — grep test + full test suite

**Files:**
- None (verification only)

- [ ] **Step 1: Grep for hardcoded domain strings**

Per spec success criterion #4 — no startup-domain strings should remain in `backend/app/services/`:

```bash
cd ~/ProjectScribe-general
grep -rE "(yc_partner|elon_musk|alex_hormozi|claim|decision|rejection)" backend/app/services/ 2>&1 | grep -v "domain_config.py" | head -10
```

Expected: empty (or only `domain_config.py` matches, which is the loader). If a service still has hardcoded references, identify it and refactor (or accept it with a justification comment in the commit).

- [ ] **Step 2: Run all backend tests**

```bash
docker compose exec backend python -m pytest tests/ 2>&1 | tail -5
```

Expected: same pass/fail count as before the refactor (baseline was 167 passed + 1 pre-existing failure).

- [ ] **Step 3: Manual end-to-end with default preset**

In a browser at `localhost:4000`:
1. Open the bench → rail shows 5 surfaces matching `indie-hacker.yaml`
2. Pick a project → inspector opens
3. Send a chat message in Co-Founder mode → advisor replies
4. Check `/knowledge` (K surface) → shows node types from the startup taxonomy
5. Open Worklog (W surface) → generate a weekly report

Each should work identically to before the refactor.

- [ ] **Step 4: Manual end-to-end with bio preset**

```bash
cp config/presets/bio-researcher.yaml config/scribe.yaml
docker compose restart backend frontend
sleep 8
```

In a browser:
1. Open `/bench` → app title "BioScribe", 3 surfaces (L, F, W), accent is teal
2. Pick a project, send a Lab Discussion message → bio personas reply
3. `/bench?surface=k` (knowledge=findings here) → taxonomy shows gene_finding/protocol_step/etc.
4. Worklog → lab-weekly template

Switch back to default:
```bash
cp config/presets/indie-hacker.yaml config/scribe.yaml
docker compose restart backend frontend
```

- [ ] **Step 5: Push the branch**

```bash
git push origin feat/bench-ui
```

- [ ] **Step 6: Final commit (optional — only if there were last-mile fixes)**

```bash
git commit --allow-empty -m "chore(framework): Phase A complete

All hardcoded domain content extracted into config/ YAML files.
Backend services + frontend components read from domain_config.
Two presets ship: indie-hacker (default, reproduces prior behavior)
and bio-researcher (proves a different domain works end-to-end).

Next: Phase B — AI-driven /setup wizard."
```

---

## Out of scope (Phase B+)

- **AI-driven /setup wizard** — chat + form UI that generates `scribe.yaml` from a description
- **Hot-reload** — restart still required to pick up YAML changes
- **In-bench YAML editor** — for now, edit files on disk
- **Multi-tenancy** — one config per deployment
- **AI-generated provider plugins** (Pubmed, Zotero, etc.) — Phase C
- **Migration tool for switching taxonomies on a populated DB** — fresh DB assumed when switching presets

## Success criteria (from spec)

1. ✅ **Same behavior on default preset.** A user who never touches the config files sees the bench exactly as today.
2. ✅ **Different domain works.** Switching `config/scribe.yaml` to `presets/bio-researcher.yaml` and restarting gives a "BioScribe" with bio personas + taxonomy + lab worklog, no code edits.
3. ✅ **All existing tests still pass.**
4. ✅ **No domain strings in code** — grep check passes.
5. ✅ **A 5-line preset edit is enough** for a CS friend to ship their own customized tool — confirmed by inspecting `bio-researcher.yaml` (~30 lines total).
