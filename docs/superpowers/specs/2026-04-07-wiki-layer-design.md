# LLM Wiki Layer: Auto-Maintained Project Summary Pages

**Date:** 2026-04-07
**Status:** Design Spec
**Author:** Chester Guan + Claude

---

## Problem

ProjectScribe's memory system stores flat entries — commit summaries, file content, narrative facts — but lacks a synthesized, always-current overview of each project. Users must mentally piece together what a project does, its tech stack, key decisions, and current status from dozens of individual memory entries. There's no single document that tells you "here's everything important about this project."

## Solution

After each GitHub sync, AI reads the project's memory entries and generates a comprehensive **project summary page** — a living wiki document stored as a special memory entry. This page is automatically updated on every sync, always current, and searchable via the existing RAG pipeline.

Inspired by Karpathy's LLM Wiki pattern: the AI maintains structured knowledge, not just raw data.

---

## Wiki Page Content Structure

The AI generates a markdown document with standardized sections:

```markdown
## Project Overview
One-paragraph description of what the project does, its purpose, and target users.

## Tech Stack
Languages, frameworks, databases, APIs, and key libraries used.

## Architecture
Key components, how they interact, data flow, deployment setup.

## Key Decisions
Important design decisions with rationale — extracted from commit patterns, 
memory entries, and narrative.

## Current Status
What's being actively worked on, recent changes in the last sync cycle.

## Milestones
Major releases, launches, or significant turning points in the project history.
```

The sections are consistent across all projects, making it easy to compare and navigate.

---

## Architecture

### Trigger

After `github_sync.run_sync()` completes successfully for a project, call `upsert_wiki_summary()` as a post-sync step. This piggybacks on the existing daily auto-sync (24h interval) so every project's wiki stays current without extra scheduling.

### Data Flow

```
GitHub Sync completes
  → Gather context: last 30 memory entries for the project
    (commits, files, narrative, releases, existing wiki summary)
  → Build AI prompt with all context
  → Cloud AI generates updated wiki summary (markdown)
  → Upsert as MemoryEntry:
      entry_type = "wiki_summary"
      metadata_ = {"page_type": "project_summary", "auto_generated": true}
  → Embedding generated automatically (existing add_entry handles this)
  → Searchable via RAG immediately
```

### Storage

The wiki summary is stored as a regular `MemoryEntry` with:
- `entry_type`: `"wiki_summary"`
- `content`: the full markdown summary
- `source_ref`: `"auto_sync"`
- `metadata_`: `{"page_type": "project_summary", "auto_generated": true, "updated_by": "sync"}`
- `embedding`: auto-generated (makes the summary searchable)

**Upsert logic:** Query for existing entry where `project_id = X AND entry_type = "wiki_summary"`. If found, update `content`, `metadata_`, and re-generate embedding. If not found, create new entry.

No new database table needed. No migration needed (metadata_ JSONB column already exists from migration 0011).

---

## Backend Changes

### New function: `upsert_wiki_summary()` in `backend/app/services/memory_service.py`

```python
async def upsert_wiki_summary(project_id: uuid.UUID, db: AsyncSession) -> MemoryEntry:
    """Generate or update the project's wiki summary page.
    
    Gathers recent memory entries, calls cloud AI to synthesize a 
    comprehensive project summary, and upserts it as a wiki_summary entry.
    """
```

Steps:
1. Fetch the last 30 memory entries for the project (excluding the existing wiki_summary to avoid self-reference)
2. Fetch the project's narrative (one-liner, origin story, etc.)
3. Build an AI prompt with all this context
4. Call cloud AI to generate the wiki summary markdown
5. Check if a `wiki_summary` entry already exists for the project
6. If exists: update content + re-embed
7. If not: create new entry via `add_entry()`

### AI Prompt for Wiki Generation

```
You are maintaining a living wiki page for a software project. Given the project's 
recent activity, narrative, and accumulated knowledge, generate a comprehensive 
project summary in markdown.

Sections to include:
## Project Overview — what it does, why, target users
## Tech Stack — languages, frameworks, databases, APIs
## Architecture — key components, data flow
## Key Decisions — important design choices with rationale
## Current Status — what's being worked on now
## Milestones — major releases or turning points

Rules:
- Be factual — only include information supported by the context
- Be concise — each section should be 2-5 sentences
- Use specific details (library names, version numbers, commit patterns)
- If information for a section is unavailable, write "No data available yet"
- Output ONLY the markdown content, no preamble
```

### Modified: `backend/app/services/github_sync.py`

After the sync completes successfully (after the existing `db.commit()`), add:

```python
# Update project wiki summary
try:
    from app.services.memory_service import upsert_wiki_summary
    await upsert_wiki_summary(project_id, db)
except Exception:
    logger.exception("Failed to update wiki summary for project %s", project_id)
```

This is fire-and-forget — wiki update failure should never block sync completion.

### New endpoint: `POST /projects/{id}/wiki/refresh`

A manual trigger for the wiki update, so users don't have to wait for the next sync.

Added to an existing router (e.g., `memory.py` router) or a small new router:

```python
@router.post("/projects/{project_id}/wiki/refresh")
async def refresh_wiki(project_id, db, _key):
    entry = await upsert_wiki_summary(project_id, db)
    return {"id": str(entry.id), "content": entry.content}
```

---

## Frontend Changes

### Memory page: pinned wiki summary card

On the project's Memory page (`/projects/{id}/memory`), if a `wiki_summary` entry exists, display it as a **pinned card at the top** — visually distinct from regular memory entries (different border color, "Wiki Summary" badge, last-updated timestamp).

### Project overview page: wiki summary section

On the project's overview/detail page, show the wiki summary content rendered as markdown. If no wiki summary exists yet, show a "Generate Wiki" button that calls the refresh endpoint.

### API additions

```typescript
export const wiki = {
  refresh(projectId: string): Promise<{ id: string; content: string }> {
    return apiFetch(`/projects/${projectId}/wiki/refresh`, { method: 'POST' });
  },
};
```

---

## Scope Boundaries

### In scope
- Auto-generated project summary page (wiki_summary entry type)
- Updated on every GitHub sync
- Manual refresh endpoint + UI button
- Pinned display on memory page
- Searchable via existing RAG

### Out of scope (future iterations)
- Entity pages (per-concept wiki pages)
- Cross-project entity linking
- Wiki lint / contradiction detection
- Wiki page versioning (history of changes)
- Custom wiki page templates
- Trigger on file upload / URL import (sync-only for now)

---

## Success Criteria

- [ ] After sync, project has a wiki_summary memory entry with structured markdown
- [ ] Wiki summary contains: Overview, Tech Stack, Architecture, Key Decisions, Status, Milestones
- [ ] POST /wiki/refresh manually triggers wiki generation
- [ ] Wiki summary appears pinned on the Memory page
- [ ] Wiki content is searchable via RAG (embedding generated)
- [ ] Existing sync flow not broken (wiki failure doesn't block sync)
- [ ] Second sync updates (not duplicates) the wiki summary
