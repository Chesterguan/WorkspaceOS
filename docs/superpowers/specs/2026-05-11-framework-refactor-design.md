# Framework Refactor — Phase A: Domain-Blind Bench + YAML Config

**Date:** 2026-05-11
**Status:** Design Spec
**Author:** Chester Guan + Claude
**Branch:** `feat/bench-ui` (continues evolving the demo)

---

## Problem

The bench UI (`feat/bench-ui`) is currently a single-purpose app: every domain assumption — the 8 YC-style cofounder personas, the 6 academic research reviewers, the 7 startup-flavored knowledge node types (decision / claim / rejection / …), the worklog templates, the rail surface labels — is hardcoded in code. To use it for a different domain (bio research, sales tracking, music production, anything else) requires forking the code and editing dozens of files.

The framework's two target audiences can't work with that:
- CS-background friends comfortable with YAML but not with cross-file Python refactors.
- Non-CS users (e.g. wife doing bio lab work) who need a working tool out of the box, customized to their domain.

This phase makes the bench code **domain-blind**: every domain assumption moves into YAML files under `config/`. The same compiled code can become a startup tool, a bio-research tool, a sales tracker, or anything else, by swapping config files. A later phase (Phase B, separate spec) adds an in-bench `/setup` wizard that AI-generates the config from a natural-language description.

## Solution

Two structural changes plus one user-facing change:

1. **Extract all hardcoded domain content into YAML.** Personas, knowledge taxonomy, extraction prompts, paper-type hints, worklog templates, surface labels, app name and theme — all moved to files under `config/`. Code reads them at startup.
2. **Add a domain-config service** that loads, validates, and serves the config to every consumer (backend services, frontend). One source of truth.
3. **Ship 2 preset packs** that demonstrate the framework works: `indie-hacker.yaml` (reproduces the current bench experience verbatim) and `bio-researcher.yaml` (proves a meaningfully different domain works with the same code).

Out of scope for this phase: the AI-driven `/setup` wizard, in-bench config editing, hot reload, plugin code generation. All of those are Phase B+.

---

## Architecture

```
┌──────────────── boot ────────────────┐
│  backend starts                       │
│    → config_loader reads config/      │
│    → resolves $refs (./personas/…)    │
│    → validates against schemas        │
│    → exposes singleton                │
│                                       │
│  if config/scribe.yaml missing:       │
│    → copy presets/indie-hacker.yaml   │
│      to config/scribe.yaml            │
└───────────────────────────────────────┘
              │
              ▼
┌────── runtime ──────────────────────────────────────────────┐
│  Backend services call domain_config.get_xxx()              │
│  Frontend fetches /api/v1/config/domain on mount             │
│  Bench surfaces / rail render from the response             │
│  Extraction / paper / worklog read prompts from config       │
└──────────────────────────────────────────────────────────────┘
```

### Component boundaries

| Component | Responsibility | Reads from |
|---|---|---|
| `domain_config.py` (new service) | Load + validate YAML at boot; expose typed accessors | `config/` filesystem |
| `GET /api/v1/config/domain` (new endpoint) | Serve sanitized domain config to the frontend | `domain_config` |
| Existing services | Replace hardcoded constants with `domain_config.get_xxx()` calls | `domain_config` |
| Frontend `useDomainConfig()` hook (new) | Fetch + cache the domain config once per session | `/api/v1/config/domain` |
| Existing components | Replace hardcoded values (SURFACES, ACCENT_CLASS, etc.) with hook values | `useDomainConfig` |

---

## Config schema

### Layout on disk

```
config/
├── scribe.yaml                    # MAIN — references everything else
│
├── personas/                      # persona pools
│   └── cofounder.yaml             # example: list of advisors
│
├── taxonomies/                    # knowledge node + edge type sets
│   └── startup.yaml
│
├── prompts/                       # named LLM prompts
│   ├── extraction/
│   │   ├── stage1-classifier.txt
│   │   └── stage2-extractor.txt
│   ├── worklog/
│   │   ├── weekly.txt
│   │   ├── monthly.txt
│   │   └── quarterly.txt
│   └── paper/
│       └── type-hints.yaml        # paper_type → description map
│
├── render-templates/              # output templates
│   └── latex/
│       ├── neurips.tex
│       └── … (existing 8 venue templates)
│
└── presets/                       # ready-to-copy main configs
    ├── indie-hacker.yaml          # reproduces current bench verbatim
    └── bio-researcher.yaml        # demonstrates a different domain
```

### `scribe.yaml` (main)

```yaml
app:
  name: "ProjectScribe"
  tagline: "AI co-founder for builders"
  accent: "#7c3aed"               # tailwind violet-600

surfaces:
  - type: roundtable
    id: cofounder
    letter: "R"
    label: "Roundtable"
    accent: "violet"
    personas: ./personas/cofounder.yaml
    extraction:
      stage1: ./prompts/extraction/stage1-classifier.txt
      stage2: ./prompts/extraction/stage2-extractor.txt
      taxonomy: ./taxonomies/startup.yaml

  - type: list
    id: drafts
    letter: "D"
    label: "Drafts"
    accent: "orange"

  - type: list
    id: papers
    letter: "P"
    label: "Papers"
    accent: "blue"
    paper_types: ./prompts/paper/type-hints.yaml

  - type: graph
    id: knowledge
    letter: "K"
    label: "Knowledge"
    accent: "teal"
    taxonomy: ./taxonomies/startup.yaml

  - type: report
    id: worklog
    letter: "W"
    label: "Worklog"
    accent: "emerald"
    templates:
      weekly:    ./prompts/worklog/weekly.txt
      monthly:   ./prompts/worklog/monthly.txt
      quarterly: ./prompts/worklog/quarterly.txt

integrations:
  github:        false
  google_drive:  false
  google_gmail:  false
  outlook:       false
```

### `personas/<pool>.yaml`

```yaml
pool_id: cofounder
label: "Co-Founder Roundtable"
mode_label: "Co-Founder"               # used in mode toggle
description: "8 business advisors modeled after well-known thinkers"
routing:
  strategy: smart_select               # smart_select | all | manual
  max_concurrent: 4
personas:
  - id: yc_partner
    name: "YC Partner"
    tagline: "Startup Strategy & PMF"
    color: "#3b82f6"
    avatar: "/avatars/yc_partner.png"  # or dicebear seed string
    expertise: [startup, pmf, fundraising, metrics]
    system_prompt: |
      You are a YC partner with deep PMF expertise…
  - id: elon_musk
    name: "Elon Musk"
    …
```

### `taxonomies/<name>.yaml`

```yaml
name: startup
description: "Decisions, claims, rejections, etc. from startup-builder conversations"
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
    description: "Something explicitly ruled out, with reasoning"
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
  - id: rejects
  - id: depends_on
  - id: derives_from
  - id: follows_up
  - id: related_to
```

### `prompts/extraction/stage2-extractor.txt`

Plain-text file. Free-form prompt body with placeholders that the loader substitutes before passing to the LLM. Available placeholders depend on which prompt type:

| Prompt type | Available placeholders |
|---|---|
| `prompts/extraction/*` | `{taxonomy_summary}`, `{taxonomy_node_type_ids}`, `{taxonomy_edge_type_ids}` — substituted from the referenced taxonomy |
| `prompts/worklog/*` | `{period_label}`, `{project_summary}` — substituted from runtime context |
| `prompts/paper/*` | `{paper_type_hint}`, `{venue_constraints}` — substituted from request |

Example `prompts/extraction/stage2-extractor.txt`:

```
You extract structured knowledge from conversation turns.

Output ONLY valid JSON with this shape:
{
  "nodes": [{"node_type": "<one of: {taxonomy_node_type_ids}>", "title": "…", "content": "…", "confidence": 0..1}],
  "edges_within_turn": [{"from_idx": int, "to_idx": int, "edge_type": "<one of: {taxonomy_edge_type_ids}>"}]
}

Node types and what each means:
{taxonomy_summary}

If nothing meaningful, return {"nodes": [], "edges_within_turn": []}.
```

Unknown placeholders are left as literal text (no template error). This lets users write simpler prompts that don't reference any framework-provided context if they don't need to.

### `prompts/paper/type-hints.yaml`

```yaml
- id: conference
  label: "Conference Paper"
  hint: "A peer-reviewed conference paper (typical length: 8-12 pages). Include: Abstract, Introduction, Related Work, Methodology, …"
- id: workshop
  …
- id: grant_proposal
  …
```

### `presets/`

Each preset is a full `scribe.yaml` that can be copied to `config/scribe.yaml` to take effect. The pieces it references (under `personas/`, `taxonomies/`, `prompts/`) ship alongside the preset.

`indie-hacker.yaml` reproduces what the current bench looks like:
```yaml
app:
  name: "ProjectScribe"
  accent: "#7c3aed"
surfaces:
  - { type: roundtable, id: cofounder, letter: R, label: "Roundtable",
      personas: ./personas/cofounder.yaml, ...}
  - { type: list, id: drafts, ... }
  …
```

`bio-researcher.yaml` is a hand-crafted demo:
```yaml
app:
  name: "BioScribe"
  accent: "#5a9fa7"
surfaces:
  - { type: roundtable, id: lab, letter: L, label: "Lab Discussion",
      personas: ./personas/bio-lab.yaml,
      extraction: { taxonomy: ./taxonomies/bio-research.yaml, ... } }
  - { type: graph, id: findings, letter: F, label: "Findings",
      taxonomy: ./taxonomies/bio-research.yaml }
  - { type: report, id: progress, letter: P, label: "Lab Progress",
      templates: { weekly: ./prompts/worklog/lab-weekly.txt } }
integrations:
  google_drive: true     # for papers + datasets
```

---

## Backend changes

### New file: `backend/app/services/domain_config.py`

```python
"""Loads the domain config at boot. Exposes typed accessors.

Lifecycle:
  - Read config/scribe.yaml from disk
  - Resolve $refs (e.g. ./personas/cofounder.yaml → load + parse)
  - Substitute {taxonomy_summary} placeholders in prompts
  - Validate against Pydantic schemas
  - Cache in module-level singleton

If config/scribe.yaml is missing on startup:
  - Copy presets/indie-hacker.yaml to config/scribe.yaml
  - Log "No config found; installed default preset"

Public API:
  get_app() -> AppConfig
  get_surfaces() -> List[SurfaceConfig]
  get_personas(pool_id) -> PersonaPoolConfig
  get_taxonomy(name) -> TaxonomyConfig
  get_prompt(path) -> str
  get_paper_type_hints() -> Dict[str, str]
  get_worklog_template(period) -> str
  get_integration_enabled(name) -> bool
"""
```

The service is a thin wrapper around PyYAML + Pydantic. ~200 lines.

### New router: `backend/app/routers/config.py`

`GET /api/v1/config/domain` — returns the JSON-serialized domain config for frontend consumption. Excludes secrets (system prompts are NOT secrets and can be sent; API keys are NOT in the domain config). Auth: any valid user.

### Services to refactor (replace hardcoded values)

| File | What changes |
|---|---|
| `services/advisors.py` | Delete the hardcoded `ADVISOR_REGISTRY` and `route_to_advisors`. Move to `domain_config.get_personas('cofounder')`. Routing logic stays (it's a structural atom). |
| `services/paper_reviewers.py` | Same — load from `domain_config.get_personas('research')`. |
| `services/paper_service.py` | Replace `_PAPER_TYPE_HINTS` with `domain_config.get_paper_type_hints()`. |
| `services/knowledge_extractor.py` | Replace `_CLASSIFIER_SYSTEM` / `_EXTRACTION_SYSTEM` constants with `domain_config.get_prompt(...)`. Replace `NODE_TYPES` / `EDGE_TYPES` frozensets with values from the active taxonomy. |
| `services/worklog_service.py` | Replace `_TEMPLATES` dict with `domain_config.get_worklog_template(period)`. |
| `services/chat_service.py` | Persona pool resolution moves through `domain_config.get_personas(...)`. |
| `services/research_service.py` | Same. |
| `routers/paper.py` | `_VALID_PAPER_TYPES` derives from `domain_config.get_paper_type_hints().keys()` (already done on `main` via the `0a13584` fix; mirror on the bench branch). |
| `models/knowledge.py` | Remove `NODE_TYPES` / `EDGE_TYPES` frozensets. Validation moves to a runtime check against the active taxonomy via `domain_config`. |
| `schemas/knowledge.py` | Field validators (`@field_validator("node_type")`) call `domain_config.get_taxonomy(active).node_type_ids` instead of importing the frozenset. |

### What stays unchanged

Atoms layer (LLM client, graph DB, SSE, auth, file storage, scheduling). All "framework" infrastructure. No domain leaks there to fix.

---

## Frontend changes

### New hook: `frontend/lib/bench/useDomainConfig.ts`

```typescript
export interface DomainConfig {
  app: { name: string; accent: string; tagline?: string };
  surfaces: SurfaceConfig[];
  integrations: Record<string, boolean>;
}

export function useDomainConfig() {
  return useSWR<DomainConfig>('/config/domain', () => domain.get(), {
    revalidateOnFocus: false,
  });
}
```

Fetches once per session. The bench layout, rail, and surface components all read from this instead of the hardcoded `SURFACES` array.

### Files to refactor

| File | What changes |
|---|---|
| `lib/bench/surfaces.ts` | DELETE the hardcoded `SURFACES` constant + `ACCENT_CLASS` map. Both become functions that take the config response and return derived values. |
| `components/bench/Rail.tsx` | Render `surfaces` from the hook. The accent-class derivation moves to a util that maps the configured accent name → tailwind classes (still needs a static map of allowed accents — `violet/orange/blue/teal/emerald/red/yellow/cyan` — so Tailwind purge keeps them). |
| `components/bench/surfaces/RoundtableSurface.tsx` | Mode label / persona pool come from config. |
| `components/knowledge/KnowledgeFilters.tsx` | Node type list comes from config taxonomy, not hardcoded. |
| `lib/knowledge-style.ts` | `NODE_COLORS` / `EDGE_STYLES` derive from the taxonomy in config; the static defaults move into a fallback util. |
| `app/bench/page.tsx` | Use `useDomainConfig()` to render the layout; show a "Loading config…" state while fetching (very brief — once-per-session). |
| `lib/types.ts` | Remove `NodeType` / `EdgeType` as TS literal unions (`'claim' \| 'decision' \| …`). Replace with `type NodeType = string` since types are taxonomy-defined at runtime. |

---

## First-install handling

```
boot sequence:
  1. Check config/scribe.yaml exists
  2. If missing:
     - Copy config/presets/indie-hacker.yaml → config/scribe.yaml
     - Log: "No domain config found. Installed default preset."
  3. Load + validate
  4. If validation fails:
     - Log error with the validation path
     - Refuse to start (no silent fallback — explicit failure surfaces problems early)
  5. Cache + serve
```

The user can replace `config/scribe.yaml` (and the referenced files) at any time; restart picks up changes.

---

## Migration of the current bench experience

The current hardcoded domain content (8 cofounder advisors, 6 research reviewers, 9 paper types, 7 knowledge node types, 8 edge types, 3 worklog templates) is **moved verbatim** into `presets/indie-hacker.yaml` and the files it references. Behavior is identical for a user who keeps the default preset. The refactor is internally invisible.

For `bio-researcher.yaml`: hand-crafted with placeholder personas (PI, Postdoc, Methodology Critic, Statistics Reviewer) and a bio-research taxonomy (gene_finding, protocol_step, hypothesis, negative_result, observation). The exact content is approximate — Phase B's AI wizard will replace this with user-described content. The preset just proves the framework supports another domain.

---

## Testing

- **Smoke test**: `domain_config_test.py` loads the default preset, verifies all accessors return non-empty values.
- **Schema validation tests**: each preset under `presets/` is loaded + validated as a CI check; broken presets fail the test.
- **Refactor regression**: existing backend tests stay green (the change is internally invisible when the default preset is loaded).
- **Frontend**: existing `useDomainConfig()` consumers tested via a mocked response.

---

## Phasing

Single phase (this spec covers everything before /setup). Implementation breaks into roughly:

1. Backend `domain_config_service` + config files + presets
2. Backend service refactor (advisors, paper_reviewers, knowledge_extractor, worklog_service, paper_service, …)
3. `GET /api/v1/config/domain` endpoint
4. Frontend `useDomainConfig` hook + surface refactor
5. Frontend taxonomy-driven UI (KnowledgeFilters, accent classes, etc.)
6. Documentation: how to write a preset, how the placeholders work
7. Hand-craft `bio-researcher.yaml` and verify it works end-to-end

Estimated ~5-8 days for a focused implementation.

---

## Out of scope

- **AI-driven /setup wizard** — Phase B, separate spec
- **In-bench YAML editor** — Phase B+
- **Hot reload of config without restart** — defer
- **Multi-user / multi-tenant configs** (one user sees startup, another sees bio) — defer; one config per deploy
- **Plugin code generation** (AI writes new L4 implementations) — Phase C
- **Backward-compatible migrations of existing knowledge_nodes data** when switching taxonomy — out of scope (switching domain assumes a clean DB)
- **Configurable integrations beyond on/off toggle** — Phase B+ (oauth scopes, sync intervals, etc.)

---

## Success criteria

The refactor succeeds when:

1. **Same behavior on default preset.** A user who never touches the config files sees the bench exactly as today.
2. **Different domain works.** Switching `config/scribe.yaml` to `presets/bio-researcher.yaml` (and restarting) yields an app named "BioScribe" with bio personas, a bio knowledge taxonomy, and a lab-progress worklog — without any code edits.
3. **All existing tests still pass.** The refactor preserves backend behavior.
4. **No domain strings in code** — `grep -rE "(yc_partner|elon_musk|claim|decision|rejection)" backend/app/services/` returns zero hits (excluding migrations and `domain_config.py` itself).
5. **A 5-line preset edit is enough** for a CS friend to ship their own customized tool.

If any of these miss, the refactor isn't done.
