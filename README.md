# WorkspaceOS

A configurable single-surface workbench framework. Personas, taxonomies, prompts, and surface layout are domain config (`config/domain.yaml` + the trees it points at) rather than hardcoded UI.

**ProjectScribe** — the maintainer's daily-driver AI co-founder platform — is the reference instance. Its `config/` tree (cofounder/research persona pools, startup taxonomy, paper/worklog prompts) is what ships in this repo; swap in your own to retarget the same surfaces at a different domain.

This branch (`feat/bench-ui`) collapses ProjectScribe's legacy 25-page UI into **one bench** where "project" is a filter, not a navigation root. Many of the full tool's features (publishing flows, paper editor, file ingest, raw memory, multi-platform integrations) are intentionally not surfaced — the goal is to show how the IA *feels* when a dense developer tool collapses into a single execution surface.

---

## What's in the bench

Five surfaces on the rail (press `1`–`5` or click):

| Letter | Surface     | What it does                                                                |
|--------|-------------|-----------------------------------------------------------------------------|
| **R**  | Roundtable  | Co-Founder (8 business advisors) + Research (6 academic reviewers), with a mode toggle |
| **D**  | Drafts      | Blog and social drafts list per project                                     |
| **P**  | Papers      | Generated research papers (single + portfolio)                              |
| **K**  | Knowledge   | Cross-project knowledge graph — decisions, claims, hypotheses, rejections auto-extracted from your conversations |
| **W**  | Worklog     | Periodic progress reports (weekly / monthly / quarterly)                    |

Plus a `⌘K` command palette, a slide-in project inspector (one-liner narrative editing), and a right-side TUI event log streaming every AI call, sync, and extraction.

## The interesting part: the knowledge layer

Every Co-Founder + Research roundtable reply runs silently through a two-stage extractor and writes typed nodes to a user-scoped graph: `decision`, `claim`, `hypothesis`, `question`, `rejection`, `blocker`, `insight`. Connected by typed edges (`supports`, `contradicts`, `refines`, `rejects`, `related_to`).

The graph is **cross-project by default** — a decision saved in Project A surfaces when you write a paper about Project B. Paper, draft, and worklog generation all pull relevant nodes into their LLM context automatically. The Karpathy "LLM Wiki" pattern, applied to roundtable transcripts.

## Quick start

```bash
git clone https://github.com/Chesterguan/ProjectScribe.git ProjectScribe-bench
cd ProjectScribe-bench
git checkout feat/bench-ui

cp .env.example .env
# Edit .env — only GEMINI_API_KEY is required. Everything else is optional.

docker compose up --build -d

# Bench:  http://localhost:4000
# API:    http://localhost:9000/docs
```

First load redirects you into `/bench`. Pick or create a project from the top-right filter, click the Roundtable icon, start a conversation.

## What you need to set up

| Required | Optional |
|---|---|
| **Gemini API key** (chat, drafts, papers, extraction, embeddings) | OpenAI key (paper roundtable reviewers — papers still generate without it) |
| | Ollama running locally for free local embeddings (fallback: Gemini) |

The full ProjectScribe also supports Twitter / LinkedIn / GitHub sync / Anthropic. **None of those are surfaced in this demo**, so their keys are omitted from `.env.example`. If you want to extend the demo to use them, the backend services are still present — just add the env vars and wire UI yourself.

## Architecture

- **Frontend** — Next.js 16 (App Router, Suspense-wrapped state, `proxy.ts` middleware), Tailwind v4, shadcn/ui, React Flow + dagre for the knowledge graph. Port **4000**.
- **Backend** — FastAPI (async), PostgreSQL 15 + pgvector (768-dim IVFFlat), Server-Sent Events for the live log. Port **9000**.
- **AI** — Hybrid. Local Ollama (`nomic-embed-text`) for embeddings when available; Gemini (`gemini-2.0-flash`) for generation; OpenAI (`gpt-4o`) for paper roundtable reviews.
- **Deployment** — Docker Compose, three services (`db`, `backend`, `frontend`), DB volume isolated per compose project so you can run alongside the full ProjectScribe (which uses 3989/8989).

## What's narrowed vs. the full tool

These are intentionally placeholder in the bench (the full tool's UIs for them live on `main` in the parent repo):

- **Files** overlay — upload + URL import + AI auto-tagging
- **Memory** overlay — raw memory CRUD
- **Portfolio** overlay — multi-project combined view
- **Draft editor** — clicking a draft card does nothing yet
- **Paper editor** — paper detail view (diagrams, tables, regenerate, version history, DOCX export) is not embedded
- **Per-draft publishing** — LinkedIn / Dev.to / Hashnode / Twitter UIs not surfaced
- **Project create** — bench modal captures name + GitHub repo only; the full form lives at `/projects/new`

The backend services exist for all of these and work — the demo just doesn't wire them into the bench.

## Differences from the parent project

| | ProjectScribe (`main`) | This demo (`feat/bench-ui`) |
|---|---|---|
| IA | 25 per-project pages | One bench, project = filter |
| Ports | 3989 / 8989 | 4000 / 9000 |
| Audience | Personal daily-driver | Public demo |
| Coverage | Full functionality | Five core surfaces + placeholders |
| Routing | Direct routes | Aggressive proxy → bench |

## Tech notes for the curious

- **Next.js 16 conformance:** uses `proxy.ts` (not the deprecated `middleware.ts`), `useSearchParams` wrapped in `<Suspense>`, dynamic params via `use()`
- **Knowledge dedup:** per-user `asyncio.Lock` serializes concurrent advisor extractions so cosine-near nodes from one roundtable turn merge instead of duplicating
- **Event SSE auth:** falls back to a `?api_key=` query string because EventSource can't set custom headers — fine for the single-tenant demo, not safe for shared deployment
- **Reduced motion respected** — WCAG 2.3.3 honored globally

## Credits

Built on top of [Chester Guan's ProjectScribe](https://github.com/Chesterguan/ProjectScribe). See the parent repo for the full feature set, the paper pipeline internals, and the design specs under `docs/superpowers/specs/`.

## License

MIT — see the parent repo.
