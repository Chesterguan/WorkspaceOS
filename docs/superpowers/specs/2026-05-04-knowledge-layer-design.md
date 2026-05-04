# Knowledge Layer: Cross-Project Graph from Roundtable Conversations

**Date:** 2026-05-04
**Status:** Design Spec
**Author:** Chester Guan + Claude

---

## Problem

Roundtable conversations (Co-Founder + Research) generate genuine signal — decisions, claims, hypotheses, rejections, open questions — but every insight dies in the `chat_messages` transcript. When the user moves to write a paper, draft a blog, or generate a worklog, none of that context follows them. The paper pipeline doesn't even query memory; the draft service starts from zero. The user re-explains the same context across features and across projects.

The deeper aim is a **single execution bench**: one workspace where context flows freely behind the scenes and "project" is a filter, not a navigation root. That bench is impossible without a substrate that stitches context together. This spec is that substrate.

This spec covers Phase 1 only (the knowledge layer). The bench UI redesign and project-creation-in-bench-world are deferred to a separate Phase 2 spec.

## Solution

Build a user-scoped, cross-project **knowledge graph** populated by automatic per-turn extraction from both roundtables, with manual promotion as a safety valve. Nodes are typed (claim, decision, question, hypothesis, rejection, blocker, insight) and connected by typed edges (supports, contradicts, refines, follows_up, depends_on, derives_from, rejects, related_to). Every consumer of context (paper pipeline, draft service, worklog, future chats) queries this layer in addition to the existing `memory_entries`.

Memory tables stay untouched. The new layer is purely additive.

---

## Architecture

```
┌─ Roundtable AI response (chat_service / research_service) ─┐
│                                                             │
│   on_message_complete hook (fire-and-forget)                │
│         ▼                                                   │
│   KnowledgeExtractor.extract_from_chat_turn(...)            │
│         │                                                   │
│         ├─ Stage 1: cheap classifier (YES/NO)               │
│         ├─ Stage 2 (only on YES): structured extraction     │
│         ├─ Embed each new node (existing 768-dim pipeline)  │
│         ├─ Dedup against recent nodes (cosine ≥ 0.92 merge) │
│         └─ Link edges (within-turn from JSON; cross-turn    │
│            via dedup neighbor: refines / related_to)        │
│         ▼                                                   │
│   knowledge_nodes + knowledge_edges                         │
└─────────────────────────────────────────────────────────────┘

   ▲                                                       ▲
   │                                                       │
Manual "🔖 Save as knowledge" on chat msgs,            Consumers:
draft passages, file excerpts                          - paper_pipeline_v2._build_paper_context
                                                       - draft_service generation
                                                       - worklog_service narratives
                                                       - chat_service._build_context
                                                       - /knowledge graph UI
```

### Key design choices

- **New tables, not extending `memory_entries`.** Memory stays as raw evidence (commits, files, transcripts). Knowledge is the distilled, typed, cross-project, graph-connected layer. Different lifecycle, different queries, different UI.
- **User-scoped, not project-scoped.** `project_id` is provenance (nullable), not a fence. Search defaults to "all my projects." This is bench-ready from day one.
- **One shared `KnowledgeExtractor`** called from cofounder chat, research roundtable, and the manual-promote endpoint. No duplication.
- **Existing RAG infra reused.** Nodes get the same 768-dim embeddings + tsvector + RRF fusion + reranking. `memory_service._hybrid_search` is refactored into a shared helper that both `search_memory` and `search_knowledge` call.
- **Fire-and-forget extraction.** Extractor uses its own DB session; chat response returns immediately; failures are logged but never bubble to the user.

---

## Schema

### Table: `knowledge_nodes`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK→users, NOT NULL, indexed | scope is user, not project |
| `project_id` | uuid FK→projects, **nullable**, indexed | provenance only; multi-project nodes have NULL |
| `node_type` | string(40), NOT NULL | enum below |
| `title` | string(160), NOT NULL | short label for graph viz |
| `content` | text, NOT NULL | full statement (1–3 sentences) |
| `source_refs` | jsonb, NOT NULL default `[]` | array of `{kind, id, excerpt}` |
| `embedding` | vector(768) | reuse existing pipeline (Gemini text-embedding-004 / nomic-embed-text) |
| `search_vector` | tsvector | reuse existing trigger pattern from `memory_entries` |
| `metadata` | jsonb default `{}` | extensible: `confidence`, `advisor_quotes`, `extraction_model`, `reinforcement_count` |
| `archived` | bool default false | manual archive (staleness v1) |
| `created_by` | string(40) | `'auto_extractor'` \| `'manual_promote'` \| `'merged_from:<uuid>'` |
| `created_at` | timestamptz default now() | |
| `updated_at` | timestamptz default now() | trigger-updated |

### Table: `knowledge_edges`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK→users, NOT NULL, indexed | denormalized for fast user-scoped traversal |
| `source_node_id` | uuid FK→knowledge_nodes ON DELETE CASCADE | |
| `target_node_id` | uuid FK→knowledge_nodes ON DELETE CASCADE | |
| `edge_type` | string(40), NOT NULL | enum below |
| `weight` | float default 1.0 | for graph layout / relevance ranking |
| `source_refs` | jsonb default `[]` | provenance for the edge itself |
| `created_by` | string(40) | same enum as nodes |
| `created_at` | timestamptz default now() | |

UNIQUE(`source_node_id`, `target_node_id`, `edge_type`) — dedup.

### Node types (7)

| Type | Meaning | Example |
|---|---|---|
| `claim` | Assertion about reality | "Transformer attention scales as O(n²)" |
| `decision` | Choice made | "Use pgvector instead of Pinecone" |
| `question` | Open question to revisit | "Does FlashRank justify its cost?" |
| `hypothesis` | To test | "Caching repo context for 30 min cuts latency 50%" |
| `rejection` | Ruled out *with reason* | "Considered Notion as backend, rejected — no SQL access" |
| `blocker` | Current obstacle | "LinkedIn OAuth needs CSRF state parameter" |
| `insight` | Observation / finding | "Users skip the edit step and accept first draft" |

### Edge types (8)

| Type | Meaning |
|---|---|
| `supports` | A backs up B |
| `contradicts` | A and B can't both hold |
| `refines` | B is a more specific version of A |
| `follows_up` | B is a next step from A |
| `depends_on` | A requires B |
| `derives_from` | A originated from B (e.g., claim from a chat turn) |
| `rejects` | rejection-of (paired with `node_type='rejection'`) |
| `related_to` | Fallback when none of the above fit (lower weight) |

### Indexes

- `ivfflat (embedding vector_cosine_ops)` on nodes — semantic search
- `gin (search_vector)` on nodes — BM25
- `btree (user_id, archived, created_at desc)` — bench feed query
- `btree (project_id)` — project-filter
- `btree (node_type)` — type-filter / graph color
- `btree (user_id)` on edges — user-scoped traversal

### Migration

Single additive Alembic migration: `add_knowledge_layer.py`. No changes to existing tables. Rollback = drop both tables.

---

## Extraction Service

### Module: `backend/app/services/knowledge_extractor.py`

Two entry points:

```python
async def extract_from_chat_turn(
    user_id: UUID,
    project_id: UUID | None,
    user_message: ChatMessage,
    ai_message: ChatMessage,
    conversation_kind: str,  # 'cofounder' | 'research'
    db: AsyncSession,
) -> ExtractionResult

async def promote_manual(
    user_id: UUID,
    project_id: UUID | None,
    source: dict,           # {kind, id, excerpt}
    suggested_type: str | None,
    db: AsyncSession,
) -> KnowledgeNode
```

### Trigger

`chat_service.send_message()` and `research_service` already persist the AI response, then return. Add fire-and-forget at the end:

```python
asyncio.create_task(
    knowledge_extractor.extract_from_chat_turn(
        user_id, project_id, user_msg, ai_msg, "cofounder",
        db_session_factory(),  # OWN session
    )
)
```

### Two-stage extraction

**Stage 1 — Cheap classifier (Gemini Flash, ~50 input + 1 output token):**

```
Does this turn contain any extractable knowledge?
A turn is extractable if it states a decision, claim, hypothesis,
question to revisit, rejection, blocker, or insight.
Pure greeting / acknowledgment / restating context = NOT extractable.
Reply with one word: YES or NO.
```

If `NO` → skip. ~80% of conversational turns expected to skip.

**Stage 2 — Structured extraction (only on YES):**

JSON schema response from Gemini Flash:

```json
{
  "nodes": [
    {
      "node_type": "decision",
      "title": "≤120 chars",
      "content": "1–3 sentences",
      "confidence": 0.85,
      "rationale": "..."
    }
  ],
  "edges_within_turn": [
    {"from_idx": 0, "to_idx": 1, "edge_type": "supports"}
  ]
}
```

Prompt includes the last 5 turns for context, plus `conversation_kind`, which biases types: research turns → more `claim`/`hypothesis`; cofounder turns → more `decision`/`rejection`.

### Dedup

For each new node:
1. Embed it (existing pipeline).
2. Vector search top-3 existing nodes for this user, same `node_type`, cosine similarity.
3. If best match ≥ **0.92** → merge: append source_ref to existing node, increment `metadata.reinforcement_count`. Do NOT create new.
4. If 0.80 ≤ best match < 0.92 → create new + add `refines` (if node_type identical) or `related_to` edge.
5. If < 0.80 → create as standalone.

The 0.92 threshold is a starting estimate; will be tuned from Phase 1a data before 1c ships. Stored as a settings constant.

### Source refs

Every auto-extracted node:
```json
"source_refs": [
  {"kind": "chat_message", "id": "<ai_msg_id>", "excerpt": "<first 200 chars>"}
]
```

Manual promotion:
```json
"source_refs": [
  {"kind": "manual", "from": "<draft_id|chat_message_id|memory_entry_id>", "excerpt": "..."}
]
```

### Cost estimate

- Stage 1: ~$0.000005/turn
- Stage 2 (only ~20% of turns): ~$0.0003/turn
- Embedding: free (local) or ~$0.00002/node (cloud)
- **Per active conversation (~10 turns): ~$0.001** — negligible

### Failure modes

- LLM timeout / 5xx → log, drop, no retry (next turn likely re-surfaces the insight)
- Gemini quota exhausted → fall back to Ollama with same prompt
- JSON parse failure → log raw output, drop
- DB write failure → log, drop (best-effort, never blocks user)

---

## Consumer Wiring

### New module: `backend/app/services/knowledge_service.py`

Public query API:

```python
async def search_knowledge(
    user_id: UUID,
    query: str,
    project_id: UUID | None = None,
    node_types: list[str] | None = None,
    limit: int = 10,
    include_archived: bool = False,
    db: AsyncSession,
) -> list[KnowledgeHit]

async def get_node_with_neighbors(
    node_id: UUID,
    user_id: UUID,
    depth: int = 1,
    db: AsyncSession,
) -> NodeGraph

async def list_recent_nodes(
    user_id: UUID,
    project_id: UUID | None,
    limit: int = 50,
    db: AsyncSession,
) -> list[KnowledgeNode]
```

`search_knowledge` reuses the RRF + FlashRank pipeline by calling a refactored `_hybrid_search` helper extracted from `memory_service`.

### Wiring points

| Consumer | Where | What it pulls | Format injected |
|---|---|---|---|
| `chat_service._build_context` | already builds context block | top-5 hits for current message | `## Relevant Knowledge\n- [decision] ...` |
| `paper_pipeline_v2` | `_build_paper_context` (paper_service.py) — currently misses memory entirely | top-15 hits, prefer types: `claim`, `insight`, `hypothesis`, `decision` | section in `context_block` between repo + workspace |
| `draft_service` generation | wherever draft AI prompt is assembled | top-10 hits scoped to draft's project | `## Project knowledge` block |
| `worklog_service` | progress report generation | nodes created in date range, grouped by `node_type` | structured table (decisions / questions / blockers) |
| `research_service` | parallel to chat — and writes back via extractor | top-5 hits | same as chat |

### Refactor

- `memory_service._hybrid_search` → private helper taking table name + user/project scope. Both `search_memory` and `search_knowledge` become thin callers. ~50 lines moved.
- Consumer changes: ~10 lines each (1 service call + 1 context block append). ~50 lines across 5 files.

### Unchanged

- `memory_service` external API stays identical (no consumer breakage)
- No changes to existing memory tables, sync logic, or wiki layer
- No changes to chat persistence — extractor reads chat messages, doesn't replace them

---

## Frontend Graph UI

### New page: `/knowledge`

Single bench-ready page (NOT under `/projects/[id]`).

```
┌────────────────────────────────────────────────────────────┐
│  Knowledge                                          [+ Add]│
│  ┌─────────────┐ ┌────────────────────────────────────────┐│
│  │ Filters     │ │           Graph canvas                 ││
│  │             │ │       (react-flow + dagre layout)      ││
│  │ Project: ▾ │ │                                        ││
│  │ Type: ☑ ... │ │     ┌──────┐                          ││
│  │ Archived: ☐ │ │     │claim │──supports──┐              ││
│  │ Search: [_] │ │     └──────┘            ▼              ││
│  └─────────────┘ │                    ┌──────────┐         ││
│                  │                    │ decision │         ││
│                  └────────────────────────────────────────┘│
│  ┌────────────────────────────────────────────────────────┐│
│  │ Selected node detail: title, type, project, sources,   ││
│  │ neighbor edges. [Edit] [Archive] [Delete]              ││
│  └────────────────────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────┘
```

### Tech

- **React Flow** (`@xyflow/react`) — fits Next.js 16, supports custom node renderers
- **dagre** for auto-layout (top-down)
- Node colors by type: claim=blue, decision=green, question=amber, hypothesis=purple, rejection=red, blocker=orange, insight=teal
- Edge styles by type: `supports`=solid, `contradicts`=red dashed, `refines`=thin solid, etc.

### Routes

- `GET  /api/knowledge/nodes` — paginated list with filters
- `GET  /api/knowledge/graph?root=<id>&depth=2` — subgraph for canvas
- `POST /api/knowledge/nodes` — manual create
- `PATCH /api/knowledge/nodes/{id}` — edit / archive
- `DELETE /api/knowledge/nodes/{id}`
- `POST /api/knowledge/promote` — manual promotion from chat msg / draft / file

### Manual promote UX

- "🔖 Save as knowledge" button on every chat message (hover menu)
- Selection-based on draft pages: highlight text → floating "Save as knowledge"
- Modal lets user pick `node_type`, optionally edit `title` / `content`, and link existing nodes via search

### Deferred to Phase 2

- Drag-to-create edges in the canvas
- Inline node editing (v1 is read-only canvas; edits via side panel)
- Cluster / community detection
- Timeline / "evolution of an idea" view

---

## Phasing

Four slices, ~7–11 dev days total. Each is useful on its own.

### Phase 1a — Foundation *(2-3 days)*
**Ships:** invisible (backend only).
- Alembic migration: tables + indexes
- `knowledge_extractor.py` (two-stage, dedup, within-turn edges)
- `knowledge_service.py` query API
- Fire-and-forget hook in `chat_service.send_message` + `research_service`
- **Validation:** run 5–10 roundtable sessions, inspect DB rows. Tune dedup threshold from real data.
- **Gate:** `node_type` distribution looks reasonable, dedup not over-merging.

### Phase 1b — Consumer integration *(1-2 days)*
**Ships:** invisible improvement to paper / draft / worklog quality.
- Refactor `memory_service._hybrid_search` into shared helper
- Wire `search_knowledge` into all 5 consumers above
- **Validation:** generate a paper after a roundtable about it — confirm decisions/claims appear in the draft.

### Phase 1c — Graph UI + manual promote on chat *(3-4 days)*
**Ships:** the visible feature.
- `/knowledge` page (react-flow + dagre, filters, detail panel)
- Backend routes (list, graph, CRUD, promote)
- "🔖 Save as knowledge" on roundtable chat messages
- **Validation:** end-to-end — chat → auto-extracted node appears → user can find / edit / archive.

### Phase 1d — Manual promote on drafts & files *(1-2 days)*
**Ships:** completes the manual-promote story.
- Text selection → floating "Save as knowledge" on drafts, blogs, file ingest pages
- **Validation:** promote 3 different source kinds, confirm provenance.

---

## Phase 2 (separate spec)

Deferred — to be designed once Phase 1 is in daily use:

- **Bench UI redesign** + project-creation-in-bench-world flow
- **Cross-turn edge inference** (heavier "find supports/contradicts across all history")
- **Drag-to-create edges** in canvas
- **Auto-decay / staleness scoring**
- **Mail / calendar / draft auto-extraction** (Outlook, Gmail, Google Calendar bridges)
- **Cluster / community detection, timeline view**
- **Per-project visibility firewall** (currently every node is user-visible across projects; sensitive client work might want a `visibility` column)
- **Conflict resolution** for manual-edit vs. later auto-merge (current v1: auto-extraction always loses to manual edits)
- **Stage-1 classifier false-negative recovery** — log stage-1 decisions, sample-review weekly, tune prompt
- **React Flow perf at scale** — fine for hundreds of nodes; thousands needs clustering

---

## Out of scope (Phase 1)

- Paper-pipeline-v2 reviewer feedback extraction (user decision: useless after review pass)
- Draft / blog / worklog auto-extraction (high redundancy with roundtable; manual promote covers gaps)
- Auto-decay or confidence scoring beyond `metadata.reinforcement_count`
- Bench UI redesign (substrate first; UI on top later)

---

## Success criteria

Phase 1 succeeds if, after one week of daily roundtable use:

1. **Coverage:** ≥ 80% of decisions / claims / rejections the user remembers from sessions are findable in `/knowledge`.
2. **Precision:** ≤ 10% of auto-extracted nodes are noise the user wants archived.
3. **Consumer impact:** the user can name at least 2 papers / drafts / worklogs that were measurably better because they pulled in roundtable context.
4. **Cost:** total extraction cost < $1/month under normal use.
5. **Latency:** chat response time unchanged (extraction is fire-and-forget).

If any of these miss, Phase 1c gates Phase 2.
