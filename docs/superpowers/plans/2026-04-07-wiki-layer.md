# Wiki Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each GitHub sync, auto-generate a comprehensive project summary wiki page stored as a special memory entry, searchable via RAG.

**Architecture:** New `upsert_wiki_summary()` function in memory_service gathers project context, calls cloud AI to generate a structured markdown summary, and upserts it as a `wiki_summary` memory entry. Called after sync and via a manual refresh endpoint. Frontend displays it as a pinned card.

**Tech Stack:** Python 3.9+ (SQLAlchemy async), Gemini Flash, Next.js 16

**Spec:** `docs/superpowers/specs/2026-04-07-wiki-layer-design.md`

---

## File Structure

### Modified files

| File | Changes |
|------|---------|
| `backend/app/services/memory_service.py` | Add `upsert_wiki_summary()` function |
| `backend/app/services/github_sync.py` | Call `upsert_wiki_summary()` after successful sync |
| `backend/app/routers/memory.py` | Add `POST /projects/{id}/wiki/refresh` endpoint |
| `frontend/lib/api.ts` | Add `wiki.refresh()` method |
| `frontend/app/projects/[projectId]/memory/page.tsx` | Pinned wiki summary card + refresh button |

---

## Task 1: upsert_wiki_summary + sync hook

**Files:**
- Modify: `backend/app/services/memory_service.py`
- Modify: `backend/app/services/github_sync.py`

- [ ] **Step 1: Add upsert_wiki_summary to memory_service.py**

Add at the end of `backend/app/services/memory_service.py` (after the existing `search_memory` function):

```python
# ---------------------------------------------------------------------------
# Wiki: auto-maintained project summary page
# ---------------------------------------------------------------------------

_WIKI_SYSTEM = """You are maintaining a living wiki page for a software project. \
Given the project's recent activity, narrative, and accumulated knowledge, generate \
a comprehensive project summary in markdown.

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
- Output ONLY the markdown content, no preamble or explanation"""


async def upsert_wiki_summary(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> MemoryEntry:
    """Generate or update the project's wiki summary page.

    Gathers recent memory entries + narrative, calls cloud AI to synthesize
    a comprehensive summary, and upserts it as a wiki_summary entry.
    """
    from app.services.ai_client import get_cloud_client
    from app.services.narrative_service import build_context_block, get_or_create

    # 1. Gather context — last 30 memory entries (exclude existing wiki_summary)
    context_result = await db.execute(
        select(MemoryEntry)
        .where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type != "wiki_summary",
        )
        .order_by(MemoryEntry.created_at.desc())
        .limit(30)
    )
    recent_entries = list(context_result.scalars().all())

    context_parts: List[str] = []

    # Add narrative
    try:
        narrative = await get_or_create(project_id, db)
        ctx = build_context_block(narrative)
        narrative_lines: List[str] = []
        if ctx.get("one_liner"):
            narrative_lines.append(f"One-liner: {ctx['one_liner']}")
        if ctx.get("target_audience"):
            narrative_lines.append(f"Target audience: {ctx['target_audience']}")
        if ctx.get("origin_story"):
            narrative_lines.append(f"Origin story: {ctx['origin_story']}")
        if narrative_lines:
            context_parts.append("## Narrative\n" + "\n".join(narrative_lines))
    except Exception:
        logger.debug("Wiki: could not load narrative for project %s", project_id)

    # Add recent memory entries
    if recent_entries:
        entry_lines: List[str] = []
        for entry in recent_entries:
            preview = entry.content[:300].replace("\n", " ")
            entry_lines.append(f"- [{entry.entry_type}] {preview}")
        context_parts.append(
            "## Recent Memory Entries\n" + "\n".join(entry_lines)
        )

    if not context_parts:
        logger.info("Wiki: no context available for project %s, skipping", project_id)
        # Return existing wiki or create minimal one
        existing = await db.execute(
            select(MemoryEntry).where(
                MemoryEntry.project_id == project_id,
                MemoryEntry.entry_type == "wiki_summary",
            )
        )
        entry = existing.scalar_one_or_none()
        if entry:
            return entry
        # Create minimal placeholder
        return await add_entry(
            project_id=project_id,
            entry_type="wiki_summary",
            content="## Project Overview\nNo data available yet.",
            source_ref="auto_sync",
            db=db,
        )

    # 2. Call AI to generate wiki summary
    ai = get_cloud_client()
    user_prompt = (
        "## Project Context\n\n"
        + "\n\n".join(context_parts)
        + "\n\n---\nGenerate the wiki summary now."
    )

    try:
        wiki_content = await ai.complete(system=_WIKI_SYSTEM, user=user_prompt)
    except Exception:
        logger.exception("Wiki: AI generation failed for project %s", project_id)
        wiki_content = "## Project Overview\nWiki generation failed. Will retry on next sync."

    # 3. Upsert — check for existing wiki_summary
    existing_result = await db.execute(
        select(MemoryEntry).where(
            MemoryEntry.project_id == project_id,
            MemoryEntry.entry_type == "wiki_summary",
        )
    )
    existing_entry = existing_result.scalar_one_or_none()

    metadata = {
        "page_type": "project_summary",
        "auto_generated": True,
        "updated_by": "sync",
    }

    if existing_entry:
        # Update existing entry
        existing_entry.content = wiki_content
        existing_entry.metadata_ = metadata

        # Re-generate embedding
        try:
            ai_local = get_local_client()
            context_desc = await _generate_context_description(wiki_content, "wiki_summary")
            embed_text = f"{context_desc}\n\n{wiki_content}" if context_desc else wiki_content
            existing_entry.embedding = await ai_local.embed(embed_text)
            existing_entry.context_description = context_desc or None
        except Exception:
            logger.debug("Wiki: embedding update failed, keeping old embedding")

        await db.flush()
        await db.refresh(existing_entry)
        logger.info("Wiki: updated summary for project %s", project_id)
        return existing_entry
    else:
        # Create new entry
        entry = await add_entry(
            project_id=project_id,
            entry_type="wiki_summary",
            content=wiki_content,
            source_ref="auto_sync",
            db=db,
        )
        entry.metadata_ = metadata
        await db.flush()
        await db.refresh(entry)
        logger.info("Wiki: created summary for project %s", project_id)
        return entry
```

- [ ] **Step 2: Hook into github_sync.py**

In `backend/app/services/github_sync.py`, find the block after `await db.commit()` where it schedules extraction (around line 246-249):

```python
    if sync_run.status == "completed":
        _schedule_extraction(sync_run.id)
        _schedule_evolution_summary(sync_run.id)
```

Add the wiki update right before this block (after the `db.commit()` but still inside the `if completed` check). Since `upsert_wiki_summary` needs a db session and the existing one was just committed, we need to open a new one:

```python
    if sync_run.status == "completed":
        # Update project wiki summary
        try:
            from app.services.memory_service import upsert_wiki_summary
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as wiki_db:
                await upsert_wiki_summary(project_id, wiki_db)
                await wiki_db.commit()
        except Exception:
            logger.exception("Wiki summary update failed for project %s (non-blocking)", project_id)

        _schedule_extraction(sync_run.id)
        _schedule_evolution_summary(sync_run.id)
```

- [ ] **Step 3: Verify import works**

```bash
docker compose exec backend python -c "from app.services.memory_service import upsert_wiki_summary; print('OK')"
```

---

## Task 2: Refresh endpoint + API

**Files:**
- Modify: `backend/app/routers/memory.py`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add refresh endpoint to memory router**

Read `backend/app/routers/memory.py` first to understand the existing structure, then add this endpoint. Find the existing router (should be `router = APIRouter(prefix="/projects/{project_id}/memory", ...)`) and add:

```python
@router.post(
    "/wiki/refresh",
    status_code=status.HTTP_200_OK,
    summary="Refresh the project wiki summary",
)
async def refresh_wiki(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> dict:
    """Manually trigger wiki summary generation/update."""
    from app.services.memory_service import upsert_wiki_summary

    # Verify project exists
    from app.models.project import Project
    result = await db.execute(select(Project).where(Project.id == project_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    entry = await upsert_wiki_summary(project_id, db)
    return {
        "id": str(entry.id),
        "content": entry.content,
        "updated_at": entry.created_at.isoformat() if entry.created_at else None,
    }
```

Make sure `select` is imported from sqlalchemy (check if it's already there).

- [ ] **Step 2: Add frontend API method**

In `frontend/lib/api.ts`, add after the `files` object:

```typescript
// ─── Wiki ────────────────────────────────────────────────────────────────────

export const wiki = {
  refresh(projectId: string): Promise<{ id: string; content: string; updated_at: string | null }> {
    return apiFetch(`/projects/${projectId}/memory/wiki/refresh`, { method: 'POST' });
  },
};
```

---

## Task 3: Frontend — pinned wiki card + refresh button

**Files:**
- Modify: `frontend/app/projects/[projectId]/memory/page.tsx`

- [ ] **Step 1: Add wiki summary display**

Read the memory page first to find the right insertion point. The page should:

1. Add imports:
```typescript
import { wiki as wikiApi } from "@/lib/api";
import { BookOpen, RefreshCw } from "lucide-react";
```

2. Add state for the wiki summary (after existing state declarations):
```typescript
const [wikiContent, setWikiContent] = useState<string | null>(null);
const [wikiLoading, setWikiLoading] = useState(false);
const [isRefreshingWiki, setIsRefreshingWiki] = useState(false);
```

3. Load wiki summary on mount — look for an existing memory entry with entry_type "wiki_summary" from the loaded memory data. Add a useEffect:
```typescript
useEffect(() => {
  if (data) {
    const wikiEntry = data.find((e: MemoryEntry) => e.entry_type === "wiki_summary");
    if (wikiEntry) {
      setWikiContent(wikiEntry.content);
    }
  }
}, [data]);
```

Where `data` is the memory entries from `useMemory()` hook.

4. Add refresh handler:
```typescript
async function handleRefreshWiki() {
  setIsRefreshingWiki(true);
  try {
    const res = await wikiApi.refresh(project.id);
    setWikiContent(res.content);
    toast.success("Wiki summary updated");
    mutate(); // refresh memory list
  } catch {
    toast.error("Failed to refresh wiki");
  } finally {
    setIsRefreshingWiki(false);
  }
}
```

5. Add the pinned wiki card JSX — insert at the TOP of the main content area, before the memory entry list. The card should:
- Have a distinct appearance (e.g. border-primary/30 background)
- Show "Wiki Summary" badge + BookOpen icon
- Render the wiki content as rendered markdown (use dangerouslySetInnerHTML with the existing markdown renderer or just whitespace-pre-wrap)
- Have a "Refresh" button in the corner
- Be collapsible (use `<details open>`)

```tsx
{/* Wiki Summary — pinned at top */}
{wikiContent && (
  <details open className="mb-6 border border-primary/20 rounded-lg bg-primary/5">
    <summary className="p-4 cursor-pointer flex items-center justify-between">
      <div className="flex items-center gap-2">
        <BookOpen className="w-4 h-4 text-primary" />
        <span className="text-sm font-semibold">Wiki Summary</span>
        <Badge variant="outline" className="text-[10px] text-primary border-primary/30">
          Auto-generated
        </Badge>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 text-xs gap-1.5 text-muted-foreground"
        onClick={(e) => { e.preventDefault(); handleRefreshWiki(); }}
        disabled={isRefreshingWiki}
      >
        {isRefreshingWiki ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <RefreshCw className="w-3.5 h-3.5" />
        )}
        Refresh
      </Button>
    </summary>
    <div className="px-4 pb-4 text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">
      {wikiContent}
    </div>
  </details>
)}
{!wikiContent && !isRefreshingWiki && data && data.length > 0 && (
  <div className="mb-6 border border-dashed border-border rounded-lg p-4 text-center">
    <p className="text-sm text-muted-foreground mb-2">No wiki summary yet</p>
    <Button
      variant="outline"
      size="sm"
      className="gap-1.5"
      onClick={handleRefreshWiki}
    >
      <BookOpen className="w-3.5 h-3.5" />
      Generate Wiki Summary
    </Button>
  </div>
)}
```

---

## Task 4: Verification

- [ ] **Step 1: Rebuild**
```bash
docker compose up --build -d backend frontend
```

- [ ] **Step 2: Test manual refresh**
```bash
curl -s -X POST http://localhost:8989/api/v1/projects/49a5854d-60dc-430f-8e81-88fa8db5ebdc/memory/wiki/refresh \
  -H "X-API-Key: dev-secret-key" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'id: {d[\"id\"]}')
print(f'content (first 300 chars): {d[\"content\"][:300]}')
"
```

- [ ] **Step 3: Verify it's searchable via RAG**
```bash
curl -s -X POST http://localhost:8989/api/v1/projects/49a5854d-60dc-430f-8e81-88fa8db5ebdc/memory/search \
  -H "X-API-Key: dev-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "project overview architecture", "limit": 3}' | python3 -c "
import sys, json
for e in json.load(sys.stdin):
    print(f'{e[\"entry_type\"]}: {e[\"content\"][:80]}...')
"
```

- [ ] **Step 4: Run test suite**
```bash
docker compose exec backend bash -c "cd /app/tests && python -m pytest test_endpoints.py -q"
```

---

## Summary

| Task | Component | Files | Complexity |
|------|-----------|-------|-----------|
| 1 | Wiki generation + sync hook | Modify: `memory_service.py`, `github_sync.py` | Medium |
| 2 | Refresh endpoint + API | Modify: `memory.py` (router), `api.ts` | Low |
| 3 | Frontend display | Modify: `memory/page.tsx` | Medium |
| 4 | Verification | No code | Low |

Total: 0 new files, 5 modified files, 0 migrations.
