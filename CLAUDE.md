# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repo.

## Project Overview

**WorkspaceOS** is a configurable single-surface workbench framework for
people who do focused, long-running creative work — researchers,
founders, writers, builders. The framework ships the bench (rail, six
surfaces, knowledge graph, event log) and the customization layer
(domain config, onboarding wizard, extension packs). Domain content
(personas, taxonomies, prompts, worklog templates) is plug-and-play
via `config/extensions/<id>/`.

The reference instance — **ProjectScribe** — is the maintainer's
daily-driver AI co-founder platform. Its full feature set
(multi-agent paper pipeline, file ingest, wiki layer, multi-platform
publishing) is wired in the backend services; the bench UI surfaces a
focused subset and treats those services as the domain implementation.

OSS-targeted. Contributions in extensions especially welcomed
— see CONTRIBUTING.md.

## Architecture

- **Frontend**: Next.js 16 (App Router, Suspense-wrapped state,
  `proxy.ts` middleware), Tailwind v4, shadcn/ui, motion (Framer),
  React Flow + dagre for the knowledge graph. Port **4000**.
- **Backend**: FastAPI (async), PostgreSQL 15 + pgvector (768-dim
  IVFFlat), Server-Sent Events for the bench log + wizard generation.
  Port **9000**.
- **AI**: Hybrid. Local Ollama (`nomic-embed-text`) for embeddings
  when available; Gemini (`gemini-2.0-flash`) for generation +
  long-tail wizard fallback; OpenAI (`gpt-4o`) for paper roundtable
  reviewers (optional).
- **Deployment**: Docker Compose, three services (`db`, `backend`,
  `frontend`) on the `workspaceos` network. Volume names are pinned
  via `name: workspaceos` in compose.
- **Auth**: JWT (access + refresh) for user routes; `X-API-Key` for
  scripts / SSE query-param. Per-user scoping enforced in routers.

## The bench

Six surfaces on the rail, each opt-in via domain config:

| Letter | Surface     | Type        | What |
|--------|-------------|-------------|------|
| **R**  | Roundtable  | roundtable  | Cofounder persona pool — chat with 3–4 of 4–8 advisors per message |
| **A**  | Research    | roundtable  | Academic / domain reviewer pool — parallel critique from 5–6 reviewers |
| **D**  | Drafts      | list        | Blog and social drafts (per-project, paginated) |
| **P**  | Papers      | list        | Research papers (single + portfolio v2 pipeline) |
| **K**  | Knowledge   | graph       | Cross-project node graph — decisions, claims, hypotheses extracted from chat |
| **W**  | Worklog     | report      | Weekly / monthly / quarterly progress reports |

Plus a `⌘K` command palette, slide-in project inspector, right-side TUI
event log streaming every AI call / sync / extraction.

## Extension framework (Phase 1: content)

Extensions live under `config/extensions/<id>/` and are pure data — no
code. Each is a folder containing:

```
config/extensions/<id>/
├── manifest.yaml        # id, name, version, matches{}, paths
├── personas/
│   ├── cofounder.yaml   # cofounder persona pool
│   └── research.yaml    # research reviewer pool
├── taxonomies/extra.yaml  # node types ADDED to the base 7
└── prompts/worklog/{weekly,monthly,quarterly}.txt
```

`manifest.matches` declares scoring rules — `domain_keywords` (+2 per
substring hit), `audience_any` (+1 per overlap), `outputs_any` (+1 per
overlap). Threshold = 2.

Shipped extensions:
- `ai-research` — Bengio, LeCun, Pinker, Ng, Xie, Topol + frontier-AI
  cofounders. Taxonomy adds Paper / Benchmark / Ablation / Experiment.
- `bio-research` — Drew Endy, George Church, Jay Keasling, Doudna,
  Topol, Tim Lu + biotech operators. Taxonomy adds Strain / Construct /
  Assay / Experiment / Interview.

## Extension framework (Phase 2: capabilities — declared, not active)

The manifest schema reserves a `capabilities: List[Capability]` field
for Phase 2. Capability kinds: `ingest_source` (Gmail, Calendar,
Slack), `slash_command` (⌘K palette entry), `action_button` (per-item
context action), `surface_widget` (sub-component in a surface).
Loader stores capability entries verbatim today; runtime ignores
them. Schema is stable so extension authors can write
forward-compatible manifests now.

## Onboarding wizard

7-question wizard at `/onboarding`:
1. Domain (free text)
2. Primary outputs (multi-select: papers, blog, code, internal reports, social)
3. Audience (multi-select: peer researchers, customers, investors, internal team, public)
4. Dream advisor panel (free text or "let AI pick")
5. Tracked artifacts (free text — drives knowledge taxonomy)
6. Cadence (weekly/monthly/quarterly/none)
7. Stage (early/mid/late, optional)

Backend SSE-streams progress while the generator runs. Generation flow:
**extension match** (extension-first) → **Gemini synthesis**
(GEMINI_API_KEY required) → **deterministic bucket stub** (final
fallback). 5-chapter SVG tutorial animation plays during wait. Preview
pane shows generated config + an "Extension: X" badge if matched.
Apply writes files to `config/`, reloads loader live, marks user's
`tutorial_completed=true`.

## Commands

```bash
# Docker (from repo root)
docker compose up --build -d
docker compose logs backend --tail 20
docker compose up --build -d backend       # rebuild single service

# Backend (from backend/)
uvicorn app.main:app --reload --port 8000
alembic upgrade head
alembic revision --autogenerate -m "msg"
SEED_DEMO_DATA=true python seed.py         # demo seed is opt-in
pytest tests/

# Frontend (from frontend/)
npm run dev
npm run build
npm run lint

# Tests (inside Docker)
docker compose exec backend bash -c "cd /app && python -m pytest tests/test_domain_config.py -v"
```

## Rules

- Python 3.9+ compatible: `Optional[]`, `List[]`, `Dict[]` from
  `typing` — not `X | None`.
- Minimal diffs. Don't refactor surrounding code unless the task
  requires it.
- Don't rename public APIs without an explicit ask.
- AI ops: local model for privacy / classification, cloud for
  generation. Paper reviewers and writers use different providers for
  genuine critique.
- Frontend: shadcn/ui components, lucide-react icons, SWR for fetching,
  motion for animation.
- Follow patterns in adjacent files before writing new ones.
- Run relevant tests before finishing.
- Security: HTML-escape user input in HTML responses, validate URLs
  before fetching, scope queries by `user_id` for JWT auth, never log
  secrets.
- Shared frontend modules — don't duplicate: `TypingIndicator`,
  `ContextPill`, `AgentLogPanel`, `RoundtableReviewPanel`,
  `VisualContentDialogs`, `PersonaAvatar`, `groupMessages`,
  `usePersonaPool`.

## Output rules

- Concise. Don't explain unless asked.
- Don't repeat context back.
- Only output: code changes + minimal summary.
- No emojis unless requested.

## Current priorities

1. Daily-driver use — find real pain points.
2. Ship more content extensions (indie-founder, phd-student).
3. Phase 2: capability extensions (Gmail ingest first — easiest to
   prove the pattern).
4. Settings UI for "Personalize" re-run of the wizard.

## Phase 1 completed (shipped, working today)

- WorkspaceOS rebrand: framework name + Docker network +
  pyproject + UI titles. ProjectScribe kept as reference instance.
- Bench UI: rail, 6 surfaces (R/A/D/P/K/W), command palette, project
  inspector, TUI event log, files/memory/portfolio overlays.
- Domain config: `config/domain.yaml` loader, `/api/v1/config/domain`
  endpoint, surface registry driven by config, persona pools served
  from YAML.
- Chat UIs read personas from domain config via `usePersonaPool`
  — wizard-generated personas flow live into the bench without
  hardcoded fallbacks blocking them. SVG-initials avatar fallback
  for personas without image URLs.
- Roundtable surface routing fixed (each surface = its own pool, no
  redundant mode toggle).
- Onboarding wizard: 7 questions, SSE streaming generation, 5-chapter
  SVG tutorial animation, preview pane with apply/regenerate.
- Generator: extension-first → Gemini → bucket stub.
- Two extensions shipped (`ai-research`, `bio-research`) with personas,
  taxonomy, worklog prompts.
- Event stream: wizard generation / apply events flow into the bench
  TUI log in real time.
- Demo seed gated behind `SEED_DEMO_DATA` env var — fresh deploys
  boot empty for real users.

## Phase 1 also completed (services available, not all surfaced)

- Paper pipeline v2 (section-by-section + 6-reviewer roundtable, PDF
  + DOCX export).
- Hybrid RAG memory (pgvector + BM25 + RRF + FlashRank rerank).
- File ingest (PDF, markdown, code, HTML → auto-tagged memory).
- Wiki layer (auto-maintained project summary pages, Karpathy
  pattern).
- Multi-platform publishing (GitHub Releases, LinkedIn, Dev.to,
  Hashnode, Twitter/Medium/Xiaohongshu manual).
- JWT auth, Fernet-encrypted runtime API key overlay, daily pg_dump
  backups, rate limiting, usage tracking.
- 19 Alembic migrations.

## Known constraints

- Docker runs on OrbStack (macOS); DNS via `0.250.250.200`.
- DB name `pr_secretary` is legacy — don't rename, it's persisted in
  the Docker volume.
- Don't override `DATABASE_URL` in docker-compose `environment:` —
  use `env_file:` only.
- `config/domain.yaml` is gitignored (runtime artifact). Active config
  is written by the wizard or copied from a preset on first boot.
- The wizard's Gemini fallback path is **inert without a real
  `GEMINI_API_KEY`** — extension match handles common domains;
  unmatched domains fall through to the bucket stub when the key
  isn't valid.
- `RESEARCH_REVIEWERS` and `ADVISORS` legacy hardcoded constants in
  `lib/advisors.ts` are still imported by `usePersonaPool` as a
  fallback. They render only when domain config has no personas
  configured.
- LinkedIn OAuth has no CSRF state parameter — needs session
  infrastructure before non-demo use.
- Paper pipeline v2 can take 5–15 minutes (LLM-bound).
- Docker backend image is ~3GB due to texlive + matplotlib.

Last updated: 2026-05-13
