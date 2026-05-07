# Bench UI: Single-Surface Workbench with Project as a Filter

**Date:** 2026-05-06
**Status:** Design Spec
**Author:** Chester Guan + Claude

---

## Problem

ProjectScribe today has 25+ routable frontend pages, mostly nested under `/projects/[projectId]/...`. The user has to commit to a project before they can do anything (chat, draft, paper, etc.), and then navigate again to pick the surface. New users see a wall of features without an obvious starting point. Power users feel friction switching between projects. The visual language is inconsistent across pages — each was added independently and reflects whoever built it.

The deeper aim, surfaced during Phase 1 brainstorming: **one execution bench** where context flows freely behind the scenes and "project" is a filter, not a navigation root. Phase 1 (the knowledge layer) built the substrate that makes this possible. This spec is the surface that uses it.

This branch (`feat/bench-ui`) ships as a public-facing demo with an opinionated, polished UX aimed at general users (mixed-tech audience). The user's personal main version stays separate.

## Solution

Replace the per-project navigation with a 4-column bench layout:

- **Rail (48px)** — five core surfaces always visible: Roundtable / Drafts / Papers / Knowledge / Worklog. Settings and command palette at the bottom.
- **Project inspector (240px, conditional)** — slides in between the rail and main when a specific project is filtered. Closes back to invisible when filter is "All projects".
- **Main (flex)** — the active surface.
- **TUI event log (32%)** — always-visible monospace panel on the right, tailing real-time events (extractions, AI calls, sync runs, errors).

Every existing feature is reachable. Surfaces that don't make the rail (Files, Memory raw, Portfolio, Settings) live in the ⌘K command palette. Project metadata pages (Overview, Narrative, Sync, Timeline) collapse into the inspector.

This is **primarily a frontend redesign**. The only backend addition is a small Server-Sent Events endpoint plus a few emit calls in existing services to feed the TUI log (see "TUI Event Log" below). No service logic changes, no schema changes, no refactoring of existing endpoints.

---

## Architecture

```
┌────────────────────────────── Bench layout ──────────────────────────────┐
│                                                                          │
│  ┌──────┬──────────────┬───────────────────────────────┬──────────────┐ │
│  │ Rail │  Inspector   │           Main                │   TUI log    │ │
│  │ 48px │   240px      │           flex                │     32%      │ │
│  │      │ (conditional)│                               │              │ │
│  │  R   │ Project name │   Active surface header       │   events     │ │
│  │  D   │ Overview     │   (Roundtable / Drafts /      │   12:04 …    │ │
│  │  P   │ Narrative    │    Papers / Knowledge /       │   12:04 …    │ │
│  │  K   │ Quick links  │    Worklog)                   │   12:03 …    │ │
│  │  W   │ Files / mem  │                               │              │ │
│  │      │ GitHub       │   ┌─────────────────────────┐ │              │ │
│  │ ─── │              │   │   Surface body          │ │              │ │
│  │  ⌕   │              │   │                         │ │              │ │
│  │  ⚙   │              │   │                         │ │              │ │
│  └──────┴──────────────┴───┴─────────────────────────┴─┴──────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Scope of changes

- **Backend:** one new SSE endpoint (`GET /api/v1/events/stream`) plus emit calls in `chat_service`, `research_service`, `knowledge_extractor`, `github_sync`, `paper_pipeline_v2`, `worklog_service`. No service logic changes, no schema changes.
- **Frontend:** new `/bench` page + new components under `components/bench/`, plus a small library `lib/bench/`. Existing per-domain components (`ChatWindow`, `DraftEditor`, `KnowledgeGraph`, etc.) are reused as-is — bench is a glue layer.
- **State management:** continue using SWR (the project's existing pattern). No new state library.
- **Routing:** `/bench` is the new home. Existing `/projects/[id]/*` routes redirect via Next.js middleware. **Verify the Next.js 16 patterns** for `useSearchParams` and `router.replace()` (`frontend/AGENTS.md` warns about breaking changes from training data).
- **`useBenchState` URL syncing:** active surface, project filter, inspector toggle, mode toggle (Roundtable cofounder/research), and overlay state all live in URL query params. Transient state (palette open/closed, modal open/closed) stays in component state.

### Component boundaries

```
frontend/
├── app/bench/
│   └── page.tsx                  ← new home
├── components/bench/
│   ├── BenchLayout.tsx           ← 4-column orchestrator
│   ├── Rail.tsx                  ← left rail with 5 surface icons
│   ├── ProjectInspector.tsx     ← conditional 240px sidebar
│   ├── ProjectFilter.tsx         ← project picker dropdown
│   ├── CommandPalette.tsx        ← ⌘K palette
│   ├── EventLog.tsx              ← right TUI panel
│   ├── NewProjectModal.tsx       ← lightweight create-project modal
│   └── surfaces/
│       ├── RoundtableSurface.tsx
│       ├── DraftsSurface.tsx
│       ├── PapersSurface.tsx
│       ├── KnowledgeSurface.tsx
│       └── WorklogSurface.tsx
└── lib/bench/
    ├── useBenchState.ts          ← active surface + project filter (URL-synced)
    ├── useEventStream.ts         ← SSE/poll feed for the TUI log
    └── surfaces.ts               ← surface registry (rail + off-rail)
```

Each surface component is a thin wrapper that calls the existing service-specific components (`ChatWindow`, `DraftEditor`, `KnowledgeGraph`, etc.). The bench is glue, not new functionality.

---

## Surfaces

### R · Roundtable

Combined Co-Founder + Research with a mode toggle in the header.

| Element | Behavior |
|---|---|
| Header | Title "Roundtable" · mode toggle (cofounder / research) · project filter inherited |
| Body | Reuses existing `ChatWindow` + `RoundtableGroup` components. Conversation history paginated, scoped to the active project filter. **When filter is "All projects": empty state with "Pick a project to start a conversation" + project picker shortcut.** (Existing chat-history endpoint is project-scoped; cross-project listing would require a backend change — out of scope for v1.) |
| Per-message | Bookmark icon (existing `PromoteButton`) for manual knowledge promotion. |
| Mode toggle | Switching modes preserves the typed message and project filter. Loads the appropriate advisor pool. |
| Empty state | "Start a conversation. Ask the roundtable about strategy, design, or research." with two starter chips. |

### D · Drafts

Drafts list + editor + publishing actions (folds in old `/blog` and `/posting`).

| Element | Behavior |
|---|---|
| Header | Title "Drafts" · platform filter chips (All / Blog / LinkedIn / Twitter / Dev.to / Hashnode / Medium / Xiaohongshu) · "+ New" |
| List | Existing `DraftCard` grid. **When filter is "All projects": empty state with "Pick a project" prompt** (existing drafts list endpoint is project-scoped; cross-project listing is a backend follow-up). |
| Detail | Existing `DraftEditor` + `DraftVersionHistory`. Selection-promote already in place. |
| Publish | Per-draft action button "Publish to …" that opens platform-specific dialog (existing `publish_service` calls). Was `/posting`. |
| Blog tab | Filter chip "Blog" lists published blog posts. Was `/blog`. |

### P · Papers

Single + portfolio paper generation, all 9 paper types.

| Element | Behavior |
|---|---|
| Header | Title "Papers" · scope toggle (single project / portfolio) · "+ New paper" |
| List | Recent generated papers (from `BlogPost` rows tagged `paper`). **When filter is "All projects" and scope = single: empty state.** Scope = portfolio is the path that supports cross-project listing. |
| Detail | Existing paper page (rendered markdown, agent log, roundtable review panel, version history, visual content tools, export buttons). |
| Multi-project | When scope = portfolio, the "+ New paper" modal lets the user select multiple projects. Uses existing `_build_portfolio_paper_context`. |

### K · Knowledge

The graph + manual promote, already shipped in Phase 1.

| Element | Behavior |
|---|---|
| Header | Title "Knowledge" · project filter · type filter chips · "+ New" (PromoteModal) |
| Body | Existing `KnowledgeGraph` (React Flow + dagre). Detail panel for selected node. |
| Memory tab | Inside the detail panel, a "Raw evidence" section lists linked memory entries (the source data behind the distilled node). |

### W · Worklog

Worklog reports + dashboard analytics.

| Element | Behavior |
|---|---|
| Header | Title "Worklog" · period selector (weekly / monthly / quarterly) · project scope (all or selected) |
| Body | Top: dashboard analytics chart (12-week stacked bars) — existing `ActivityChart`. Below: the generated report markdown with goals + knowledge-captured section. Export DOCX button. |

---

## Project Filter

Single-select dropdown at the top-right of the header (consistent across all surfaces). Default value is "All projects."

```
┌──────────────────────────────────┐
│ Project: [All projects        ▾] │
└──────────────────────────────────┘
```

Open state:

```
┌──────────────────────────────────┐
│ • All projects                   │  ← current selection
│   ─────────────────────          │
│   RECENT                         │
│   ProjectScribe                  │
│   FastCache                      │
│   veritas                        │
│   ─────────────────────          │
│   + New project                  │  ← opens NewProjectModal
└──────────────────────────────────┘
```

- Up to 5 most recent projects shown directly. Below that, "Show all" expands to the full list, alphabetical.
- Selection syncs to URL: `/bench?project=<id>&surface=<r|d|p|k|w>`.
- Switching to a specific project auto-opens the project inspector (240px sidebar). Switching back to "All projects" closes it.
- Multi-select is **out of scope for v1**; simple to add later if real usage demands it.

---

## Project Inspector

Secondary sidebar that occupies a 240px column between the rail and main, **only when a specific project is filtered.** Closes with the × button or ⌘[ keyboard shortcut.

### Sections (top to bottom)

| Section | Content |
|---|---|
| Header | Project name (large), close × |
| Overview | Focus notes (`focus_notes` from `Project`), one-liner from narrative, last-sync timestamp, last-activity summary (existing `ActivityFeed` condensed) |
| Narrative | Inline editor for narrative fields (one_liner, target_audience, origin_story, preferred_angles, tone_notes). Uses existing `narrative_service` API. |
| Quick links | Sync history (opens dialog with full list + manual trigger button), Timeline (opens an overlay panel listing `activity_events`), Files (filtered list of project files), Memory (filtered list of project memory entries) |
| GitHub | If `github_repo` is set: repo name + last sync stats. "Configure" opens existing `GitHubRepoSelector`. |
| Footer | Rename · Delete project (with confirm) |

### Behavior

- Inspector content is keyed on the active `project_id`. Switching projects re-fetches.
- Inspector is read-write for narrative; other sections (sync, timeline, files, memory) link out to dialogs/overlays rather than embedding the full UI.
- When inspector is closed manually, switching to another project keeps it closed; switching back to "All projects" then to a specific one re-opens it (state isn't pinned across "All projects" round-trips).

---

## Command Palette (⌘K)

Triggered by `⌘K` / `Ctrl+K` or by clicking the `⌕` icon at the bottom of the rail. Modal overlay centered on screen.

### What it lists (in order)

1. **Quick actions** — context-aware depending on current surface and project filter. E.g. "+ New paper on ProjectScribe", "+ New chat", "Promote selection to knowledge".
2. **Surfaces (off-rail)** — Files, Memory, Portfolio, Settings.
3. **Projects** — switch filter to any project; "+ New project" at the end.
4. **Search results** — when the user types, search across:
   - Knowledge nodes (title + content)
   - Drafts (title)
   - Papers (title)
   - Files (filename)
   - Top 3 of each kind, with type badges.

### Keyboard

- `↑↓` to navigate, `Enter` to select, `Esc` to close.
- `cmd+enter` on a project executes "switch and stay on current surface."

### Off-rail surfaces routing

Each off-rail surface opens **as a full-screen overlay** above the bench (not in the main column). URL state: `?overlay=files | memory | portfolio` (distinct from `?palette=...` which would conflict with the search palette concept). This keeps it distinct from the 5 core surfaces and signals "you're temporarily here, press Esc to return." Files, Memory, and Portfolio fit this pattern naturally. Settings stays as `/settings` for now (already a separate route).

---

## TUI Event Log

Right-docked, fixed 32% width. Always visible. Monospace, terminal aesthetic.

### Visual

```
╭─ events ────────────────────────────────╮
│ 12:04 extract  +2 nodes  ProjectScribe  │
│ 12:04 ai.complete  gemini-2.0  812ms    │
│ 12:04 ai.complete  openai-4o   1.4s     │
│ 12:03 sync  +3 commits  FastCache       │
│ 12:01 worklog  weekly generated         │
│ 12:00 cron  daily-backup OK             │
│ 11:58 error  embed 404 (recovered)      │
╰─────────────────────────────────────────╯
```

- Background `#0a0a0a`, foreground `#aaa`. Color codes events:
  - `#5a5` (green) — successful writes (extractions, syncs)
  - `#5aa` (cyan) — AI calls (info)
  - `#a85` (yellow) — generation milestones (worklog, paper)
  - `#a55` (red) — errors (recovered or not)
  - `#888` (gray) — cron / system
- Monospace font (Geist Mono, already loaded).
- Auto-scroll to bottom on new events. Pause-on-hover.

### Event sources

Backend already has `AgentLog` (paper pipeline) and per-service logging. New: a unified event stream endpoint at `GET /api/v1/events/stream` (Server-Sent Events) emitting JSON-line events.

```typescript
interface BenchEvent {
  ts: string;          // ISO timestamp
  level: 'info' | 'success' | 'warn' | 'error';
  source: string;      // 'extract' | 'ai' | 'sync' | 'worklog' | 'paper' | 'cron'
  summary: string;     // human-readable, max ~80 chars
  project_id?: string; // for filterable scoping
  meta?: object;       // optional extras (model, ms, etc.)
}
```

Backend implementation: a small in-memory ring buffer (last 200 events) populated by service-level emit calls (one new line per service). SSE endpoint replays the buffer on connect, then streams new events. **No persistence** — events are ephemeral runtime telemetry, not audit logs.

### Humanized labels (general-audience polish)

For the public-facing branch, the log uses friendly summaries by default:

| Event source | Default label |
|---|---|
| `extract` | "Saved 2 things from your roundtable" |
| `ai.complete` | "AI replied · gemini-2.0 · 812ms" |
| `sync` | "Pulled 3 commits from FastCache" |
| `worklog` | "Generated weekly report" |
| `cron` | "Daily backup OK" |
| `error` | "Hit a glitch (recovered)" or specific error label |

A "Show technical labels" setting (off by default) reverts to terse log lines for power users.

### Interaction

- Click a line → expands inline with metadata (event source, project, raw payload, related links).
- Right-click → "Show only this source" filter chip at the top of the panel.
- Top-of-panel chips: `all · errors · ai · sync · extract` (toggle filters).

---

## New Project Creation

Lightweight modal with two fields:

```
┌────────────────────────────┐
│ New project                │
│                            │
│ Name                       │
│ [my-new-project        ]  │
│                            │
│ GitHub repo (optional)     │
│ [owner/repo            ]  │
│                            │
│           [Cancel] [Create]│
└────────────────────────────┘
```

- Name is required; uses existing `POST /api/v1/projects` endpoint.
- GitHub repo is optional; if provided, calls `repo_import` after creation.
- After create, automatically:
  1. Switches the project filter to the new project.
  2. Opens the project inspector.
  3. Focuses the narrative one-liner field for editing.

Two ways to open the modal:
1. Project filter dropdown → "+ New project" at the bottom.
2. ⌘K palette → type "new project" or pick from quick actions.

---

## Visual System

Existing shadcn/ui theme is the foundation. The bench tightens it with:

### Typography

- **Sans-serif (UI):** Geist Sans (already loaded). 13px body, 14px labels, 11px captions.
- **Monospace (TUI log + code):** Geist Mono. 11px in the log.
- **Heading hierarchy:** 16px surface header, 14px section titles, 12px subsection labels.

### Color

- Existing dark theme (background `oklch(0.12 0 0)`, primary `oklch(0.70 0.18 265)`).
- Accent palette already used in nav cards (blue/violet/orange/teal/emerald) maps to surface identity:
  - R Roundtable — violet
  - D Drafts — orange
  - P Papers — blue
  - K Knowledge — teal
  - W Worklog — emerald
- Active rail icon uses surface accent at ~22% alpha background.

### Spacing & radius

- Existing `--radius` token (used by shadcn). Surface cards use `radius-lg` (~10px). Modal/dropdown use `radius-md`. Log panel uses `radius-sm` corners or none for the terminal feel.
- 8px grid throughout. 14px padding inside surface body, 18px on modals.

### Iconography

- `lucide-react` for everything except the rail letters and the TUI log.
- Rail uses single uppercase letters (R/D/P/K/W) inside rounded squares — visually distinctive, doesn't depend on icon recognition.
- ⌕ (search) and ⚙ (settings) at bottom of rail use lucide icons.

### Motion

- Inspector slide-in: 180ms ease-out.
- Modal/palette: 120ms fade + 4px lift.
- Surface change: instant (no transition — feels snappier).
- Event log: new lines fade in over 200ms then settle.

---

## Routing & Migration

### New routes

| Path | Purpose |
|---|---|
| `/bench` | Default landing — the bench itself |
| `/bench?project=<id>` | Bench with project filter |
| `/bench?surface=<r\|d\|p\|k\|w>` | Bench with surface selected |
| `/bench?overlay=<files\|memory\|portfolio>` | Bench with an off-rail overlay open (deep-linkable) |

### Old routes (compatibility)

All `/projects/[id]/*` and `/portfolio*` and `/knowledge` and `/worklog` routes redirect to `/bench` with the appropriate query params.

| Old | New |
|---|---|
| `/projects/[id]/chat` | `/bench?project=[id]&surface=r&mode=cofounder` |
| `/projects/[id]/research` | `/bench?project=[id]&surface=r&mode=research` |
| `/projects/[id]/research/paper` | `/bench?project=[id]&surface=p` |
| `/projects/[id]/drafts` | `/bench?project=[id]&surface=d` |
| `/projects/[id]/blog` | `/bench?project=[id]&surface=d&platform=blog` |
| `/projects/[id]/posting` | `/bench?project=[id]&surface=d` (publish actions inline) |
| `/projects/[id]/overview` | `/bench?project=[id]` (inspector auto-opens) |
| `/projects/[id]/narrative` | `/bench?project=[id]&inspector=narrative` |
| `/projects/[id]/sync` | `/bench?project=[id]&inspector=sync` |
| `/projects/[id]/timeline` | `/bench?project=[id]&inspector=timeline` |
| `/projects/[id]/files` | `/bench?project=[id]&overlay=files` (overlay) |
| `/projects/[id]/memory` | `/bench?project=[id]&overlay=memory` (overlay) |
| `/projects` | `/bench` (filter dropdown replaces the list) |
| `/portfolio` | `/bench?overlay=portfolio` (overlay) |
| `/portfolio/paper` | `/bench?surface=p&scope=portfolio` |
| `/knowledge` | `/bench?surface=k` |
| `/worklog` | `/bench?surface=w` |
| `/settings` | unchanged |

Old routes redirect via Next.js middleware so existing bookmarks keep working.

### State management

- Active surface + project filter + inspector open/closed all live in URL query params (single source of truth).
- `useBenchState()` hook reads/writes URL state via `useSearchParams` and `router.replace()`.
- Open palette and inline dialog state stays in component state (not URL) to avoid noisy navigation.

---

## Phasing

Six implementation slices, each shippable. Total estimate ~10-15 dev days.

### Phase 1 — Layout shell *(2 days)*
**Ships:** the four-column structure, rail, project filter, empty inspector + main + log placeholders. Old routes still work; `/bench` is just a skeleton.

### Phase 2 — Surface integrations *(3 days)*
**Ships:** R / D / P / K / W surfaces wired to existing components. Project filter actually filters. Old routes redirect to `/bench`.

### Phase 3 — Project inspector *(1-2 days)*
**Ships:** inspector with overview, narrative editor, quick-link dialogs.

### Phase 4 — Command palette + new project *(2 days)*
**Ships:** ⌘K palette with search + quick actions + off-rail surfaces. New project modal.

### Phase 5 — TUI event log *(2-3 days)*
**Ships:** backend SSE endpoint + ring buffer. Frontend log panel with filtering, click-to-expand, humanized labels. Service emit calls scattered through existing services.

### Phase 6 — Polish *(1-2 days)*
**Ships:** motion, focus states, keyboard shortcuts (`⌘K` palette, `⌘[` close inspector, `1`–`5` surface switching by position, `Esc` close overlay/modal), empty states, loading states, mobile fallback (rail collapses to a hamburger, inspector becomes a sheet, log hides under "Show events" tap on screens <1024px).

---

## Out of scope

- **Multi-project filter** (multi-select chips). Defer until usage shows it matters.
- **Customizable rail** (drag to reorder, hide surfaces). Five surfaces is non-negotiable for v1.
- **TUI log persistence / search history.** Ring buffer only.
- **Power-user mode toggle** for terse log labels. Default to humanized; add toggle if requested.
- **Mobile-first design.** Desktop-only for v1; mobile gets a graceful collapse but isn't optimized.
- **Backend changes beyond the SSE event stream + emit calls.** Cross-project listing endpoints (chat history, drafts list, papers list across all of a user's projects) are deferred — affected surfaces show a "Pick a project" empty state when filter is "All projects" for v1.

---

## Success criteria

The bench succeeds if, after one week of daily use:

1. **Coverage:** every action that took 2+ clicks in the old IA (project → page → action) takes ≤1 click in the bench (typically: open surface, do thing).
2. **Onboarding:** a fresh user can do all five core actions (chat with roundtable, write a draft, generate a paper, save a knowledge node, view a worklog report) within 5 minutes without reading docs.
3. **Cognitive load:** the user reports that the bench feels "calmer" than the old IA — fewer pages to remember, more visible feedback.
4. **No feature regression:** every action available in the old IA is still doable, surfaced via rail / inspector / palette.
5. **TUI log delivers:** the log is glanced at multiple times per session AND the user can recall at least one event from it without scrolling.

If any of these miss, we revisit the design before adding more surfaces or features.
