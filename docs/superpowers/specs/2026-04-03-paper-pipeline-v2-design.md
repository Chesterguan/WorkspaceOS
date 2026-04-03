# Paper Pipeline v2: Multi-Agent Section-by-Section Generation + Edit/Condense + Venue-Aware

**Date:** 2026-04-03
**Status:** Design Spec
**Author:** Chester Guan + Claude

---

## Problem

The current paper pipeline generates the entire paper in a single AI call (~3,000 words max), then reviews the monolith. This has three limitations:

1. **Length ceiling** — single-call generation can't produce 20-50 page papers
2. **No editing** — once generated, users can't modify, condense, or expand individual sections
3. **Venue-blind** — the `target_venue` field is passed as a prompt hint but doesn't enforce page limits, section structure, or formatting requirements

## Solution

Replace the monolithic generate→review pipeline with a **multi-agent, section-by-section pipeline** that supports iterative backtracking, venue-aware constraints, and post-generation editing.

---

## Architecture

### Named Agents

| Agent ID | Model | Role | Logs As |
|----------|-------|------|---------|
| `gemini_planner` | Gemini Flash | Outline, page budget, section dependencies, backtracking decisions | `[gemini_planner]` |
| `gemini_writer` | Gemini Flash | Draft one section at a time, revise on editor instructions | `[gemini_writer]` |
| `openai_critic` | GPT-4o | Review each section, cross-check against all existing sections, score 1-10 | `[openai_critic]` |
| `gemini_editor` | Gemini Flash | Coherence pass, transitions, notation consistency, condense/expand | `[gemini_editor]` |
| `ollama_literature` | Ollama (local) | Citation search, reference verification, BibTeX generation | `[ollama_literature]` |

### Pipeline Flow

```
Phase 1: PLAN
  gemini_planner → outline + page budget per section + dependency graph
  ollama_literature → find relevant papers for context
  
Phase 2: DRAFT (sequential, with backtracking)
  For each section in dependency order:
    gemini_writer → draft section (sees: outline + all prior sections + literature)
    openai_critic → review section + cross-check all existing sections
    
    If critic score < 8:
      gemini_writer → revise section based on critic feedback
      openai_critic → re-review (max 2 retries per section)
    
    If critic flags upstream issue (e.g. "section 2 needs to define X"):
      gemini_planner → decide: revise upstream section or adjust current section?
      gemini_writer → revise the flagged section
      openai_critic → re-review affected sections
    
    If critic passes (score >= 8):
      Move to next section

Phase 3: MERGE + COHERENCE
  gemini_editor → assemble all sections, smooth transitions, normalize notation
  openai_critic → final full-paper review (coherence, flow, completeness)
  
Phase 4: FINALIZE
  ollama_literature → verify all citations, generate BibTeX
  Export LaTeX (pandoc) with venue template if specified
```

### Backtracking Logic

The `gemini_planner` maintains a **section dependency graph**. When `openai_critic` flags a cross-section issue:

```python
# Critic output includes optional upstream_issues
{
  "score": 7,
  "critique": "Section 4 references 'governance gap metric' not defined anywhere.",
  "upstream_issues": [
    {"target_section": "2. Background", "issue": "Define 'governance gap metric' before it's used in evaluation"}
  ]
}

# Planner decides action:
# - If target section already written: queue revision before continuing
# - If target section not yet written: add note to that section's context
```

Max backtrack depth: 2 levels (prevent infinite loops). If a section triggers more than 2 upstream revisions, the planner flags it for human review.

---

## Feature 1: Venue-Aware Generation

### Venue Resolution

When user provides `target_venue`, the system attempts to resolve submission guidelines:

```python
class VenueGuidelines:
    venue_name: str              # "TAIGR @ ICML 2026"
    page_limit: Optional[int]    # 8
    word_limit: Optional[int]    # ~4000
    template: Optional[str]      # "icml2026"
    anonymization: bool          # True (double-blind)
    deadline: Optional[str]      # "2026-04-24"
    topics: List[str]            # ["AI governance", "policy", ...]
    source: str                  # "auto" | "manual" | "cached"
```

### Resolution Strategy (ordered)

1. **Cache lookup** — check if venue was previously resolved (stored in DB or memory)
2. **Web fetch** — scrape the venue's CFP page or OpenReview for guidelines
3. **AI inference** — if web fetch fails, ask AI: "What are the typical submission guidelines for {venue_name}?" (less reliable, marked as `source: "ai_inferred"`)
4. **Manual fallback** — return empty guidelines, let user fill in via UI

### How Venue Affects the Pipeline

| Stage | Without Venue | With Venue |
|-------|---------------|------------|
| **Planner** | Default structure | Enforces page budget = `page_limit`, section structure matches venue norms |
| **Writer** | Writes freely | Each section given word target from page budget |
| **Critic** | Reviews quality only | Also checks: "Is this section within its word budget?" |
| **Editor** | Coherence only | Also condenses if total exceeds page limit |
| **Export** | Default arxiv template | Uses venue-specific LaTeX template |

### Venue Guidelines UI

Before generating, if a venue is specified:
1. System shows "Fetching submission guidelines for {venue}..."
2. Displays resolved guidelines (page limit, deadline, topics)
3. User can override any field
4. "Generate Paper" button shows constraints: "Generate (8 pages, ICML format)"

---

## Feature 2: Paper Edit/Condense Mode

### Edit Operations

After a paper is generated, users can:

| Operation | Input | What Happens |
|-----------|-------|--------------|
| **Edit section** | "Rewrite the introduction to emphasize the governance gap" | `gemini_writer` rewrites that section, `openai_critic` reviews, backtrack if needed |
| **Condense** | "Condense to 8 pages" or "Condense for TAIGR @ ICML" | `gemini_planner` redistributes page budget, `gemini_editor` condenses each section to target |
| **Expand** | "Expand section 3 with more related work" | `gemini_writer` expands that section, `openai_critic` reviews |
| **Add section** | "Add a section on threat model" | `gemini_planner` updates outline, `gemini_writer` drafts new section in context |
| **Remove section** | "Remove the appendix" | `gemini_planner` updates outline, `gemini_editor` adjusts transitions |
| **Free instruction** | "Make the tone more formal" or "Add more citations" | Routed to appropriate agent based on instruction type |

### Edit API

```
POST /projects/{project_id}/paper/{blog_post_id}/edit
{
  "instruction": "Condense to 8 pages for TAIGR @ ICML 2026",
  "target_section": null,          // null = whole paper, or "3. Methodology"
  "target_pages": 8,               // optional explicit page target
  "target_venue": "TAIGR @ ICML 2026"  // optional, triggers venue resolution
}

Response: PaperEditResponse {
  blog_post_id: str,
  updated_content: str,
  previous_version: int,
  new_version: int,
  changes_summary: str,            // "Condensed from 15 pages to 8. Removed 2 appendix sections, trimmed examples in methodology."
  agent_log: List[AgentLogEntry],  // Full trace of which agent did what
  sections_modified: List[str],    // ["1. Introduction", "3. Methodology", "Appendix"]
}

AgentLogEntry {
  agent: str,                      // "gemini_planner" | "gemini_writer" | "openai_critic" | ...
  action: str,                     // "plan" | "draft" | "review" | "revise" | "backtrack" | "coherence"
  section: Optional[str],          // "3. Methodology" or null for full-paper actions
  detail: str,                     // Human-readable summary of what the agent did
  score: Optional[int],            // Critic score if applicable
  timestamp: str,                  // ISO timestamp
}
```

### Edit UI

The paper page gets a new mode toggle: **View | Edit**

**Edit mode shows:**
- Paper rendered on left (same as now)
- Instruction input at top: text field + quick action buttons ("Condense", "Expand", "Add Section")
- Section picker: click a section heading to scope the edit to that section
- After submitting an edit instruction:
  - Shows agent log in real-time (like the current review timeline but for edit operations)
  - Shows diff when complete
  - User can accept or revert

### Version Management

Every edit creates a new `BlogPostVersion`:
- `version`: auto-incremented
- `content`: full paper at this version
- `change_note`: the user's instruction + agent summary
- Users can revert to any previous version

---

## Data Model Changes

### New: VenueCache table (optional, for caching resolved guidelines)

```python
class VenueCache(Base):
    __tablename__ = "venue_cache"
    
    id: UUID
    venue_name: str                 # "TAIGR @ ICML 2026"
    venue_url: Optional[str]        # "https://taigr-workshop.com/"
    page_limit: Optional[int]
    word_limit: Optional[int]
    template: Optional[str]         # "icml2026" | "neurips2024" | "acm-sigconf"
    anonymization: bool
    deadline: Optional[str]
    topics: Optional[List[str]]     # ARRAY(Text)
    source: str                     # "web" | "ai_inferred" | "manual"
    fetched_at: datetime
    created_at: datetime
```

### Existing tables — no changes needed

- `BlogPost` — already stores paper content + tags for progress
- `BlogPostVersion` — already stores version snapshots with change_note
- `PaperGenerateRequest` — already has `target_venue` field

---

## Agent Prompt Design

### gemini_planner — System Prompt

```
You are a research paper planner. Your job is to create a structured outline
with page budgets for each section.

Given:
- Paper title, type, and target venue (with constraints if available)
- Project context (narrative, repo, workspace)
- Available literature

Output a JSON outline:
{
  "sections": [
    {"number": "1", "title": "Introduction", "pages": 1.5, "depends_on": [], "key_points": ["...", "..."]},
    {"number": "2", "title": "Background", "pages": 1.5, "depends_on": ["1"], "key_points": ["...", "..."]},
    ...
  ],
  "total_pages": 8,
  "venue_constraints_applied": true
}

When asked to handle a backtrack:
- Evaluate the critic's upstream issue
- Decide: revise the upstream section OR adjust the current section
- Return: {"action": "revise", "target_section": "2", "instruction": "Add definition of X"}
```

### openai_critic — Cross-Check System Prompt

```
You are a senior academic reviewer. Review the given section in the context
of ALL existing sections of the paper.

Check for:
1. Quality of this section (clarity, rigor, evidence) — score 1-10
2. Consistency with other sections (terminology, notation, claims)
3. Upstream dependencies — does this section reference anything not yet defined?
4. Downstream impact — does this section introduce concepts that later sections need?

Output:
{
  "score": 8,
  "critique": "...",
  "upstream_issues": [{"target_section": "2", "issue": "..."}],  // empty if none
  "passed": true
}
```

---

## Migration Path from v1

The v2 pipeline is a **new function** (`generate_paper_v2`) that coexists with the existing `generate_paper`. The router checks a flag or uses a new endpoint:

- `POST /projects/{id}/paper/generate` — existing v1 pipeline (kept for backward compat)
- `POST /projects/{id}/paper/generate-v2` — new multi-agent pipeline
- `POST /projects/{id}/paper/{blog_post_id}/edit` — new edit endpoint (works on any paper, v1 or v2)

Once v2 is stable, the frontend switches to v2 by default. v1 remains available as a fast mode.

---

## Scope Boundaries

### In scope:
- Multi-agent section-by-section generation with backtracking
- Venue guideline fetching (web scrape + AI inference + cache)
- Paper edit/condense/expand via instruction-based API
- Agent logging with named agents
- Version management for edits

### Out of scope (future):
- Image/figure generation within the pipeline (use existing visual tools post-generation)
- Real-time collaborative editing (single user for now)
- Automated submission to OpenReview/arXiv
- Multi-language paper generation

---

## Success Criteria

- [ ] Generate a 20+ page technical report using section-by-section pipeline
- [ ] Condense a 20-page paper to 8 pages for a specific venue
- [ ] Venue guidelines auto-fetched for ICML, NeurIPS, AAAI workshops
- [ ] Edit a single section without regenerating the whole paper
- [ ] Agent logs show clear trace: which agent did what, when, and why
- [ ] Backtracking triggered and resolved correctly when critic flags upstream issues
- [ ] QA verifier passes all endpoint tests
