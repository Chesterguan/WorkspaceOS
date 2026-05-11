# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
ProjectScribe — AI co-founder platform for developer projects. Multi-agent roundtable advisory (8 business + 6 academic advisors), paper pipeline with roundtable review, universal file ingest with AI auto-tagging, wiki layer (Karpathy LLM Wiki pattern), work log generator for supervisors, and publishing to 5 platforms.

## Architecture
- Frontend: Next.js 16 (App Router) + Tailwind + shadcn/ui → port 4000 (demo) / 3989 (main)
- Backend: Python FastAPI (async) → port 9000 (demo) / 8989 (main)
- Database: PostgreSQL 15 + pgvector (768-dim) → Docker internal
- AI: Hybrid — Ollama (local/privacy), Gemini Flash (generation), OpenAI GPT-4o (review)
- Deployment: Docker Compose with 3 services on `projectscribe` network + backend_data volume
- Auth: JWT (access + refresh tokens) + X-API-Key fallback for scripts

## Key Modules
- **Services** (28 in backend/app/services/): ai_client, ai_generation, agentic_generation, github_sync, github_client, memory_service, narrative_service, draft_service, blog_service, chat_service, workspace_scanner, publish_service, linkedin_service, repo_context, extraction_service, consolidation_service, feedback_service, research_service, paper_service, scholar_service, diagram_service, agents, advisors, paper_pipeline_v2, paper_reviewers, venue_service, file_ingest_service, template_service, latex_service, settings_service, encryption, usage_service, auth_service, worklog_service
- **Routers** (20): projects, narratives, sync, drafts, ai, memory, github, posting, blog, agentic, workspace, chat, publish, linkedin, research, paper, settings, auth, files, worklog
- **AI Pipeline**: Gemini generates → Ollama privacy-scans → OpenAI reviews → up to 4 rounds
- **Paper Pipeline v2**: Plan → section-by-section draft with backtracking → 6-reviewer roundtable review → coherence pass → finalize (BibTeX + LaTeX + PDF)
- **Co-Founder Roundtable**: 8 business advisors (YC, Elon, Hormozi, Isenberg, Gotch, McCoy, Growth Tribe, Dan Koe) — smart router picks 3-4 per question
- **Research Roundtable**: 6 academic reviewers (Bengio, LeCun, Pinker, Ng, Xie, Topol) — parallel critique from different perspectives
- **Memory**: Hybrid RAG — pgvector cosine + BM25 tsvector → RRF fusion → FlashRank reranking, contextual retrieval on write, cross-project search
- **Wiki Layer**: Auto-maintained project summary pages (Karpathy pattern) — regenerated on sync, accumulates knowledge
- **File Ingest**: Upload + URL import → text extraction (PDF, markdown, code, HTML) → AI auto-tagging → stored as enriched memory entries
- **Auto-Sync**: Daily asyncio scheduler syncs all projects (24h interval) + daily pg_dump backup (7-day retention)
- **Publishing**: GitHub Releases (API), LinkedIn (OAuth 2.0), Dev.to (API), Hashnode (GraphQL), Twitter/Medium/Xiaohongshu (manual)
- **Work Log**: Progress report generator for supervisors (weekly/monthly/quarterly) with goal tracking, DOCX export with tables + charts
- **Settings**: UI-editable API keys (Fernet-encrypted in DB), AI usage tracking with cost estimates, database backup management

## Commands
```bash
# Backend (from backend/)
uvicorn app.main:app --reload --port 8000
alembic upgrade head
alembic revision --autogenerate -m "description"
python seed.py
pytest tests/

# Frontend (from frontend/)
npm run dev
npm run build
npm run lint

# Docker (from root)
docker compose up --build -d
docker compose logs backend --tail 20
docker compose up --build -d backend  # rebuild single service

# Tests (inside Docker)
docker compose exec backend bash -c "cd /app/tests && python -m pytest test_endpoints.py -v"
```

## Rules
- Python 3.9+ compatible: use Optional[], List[], Dict[] from typing — NOT X | None
- Prefer minimal diffs — do not refactor surrounding code
- Do not rename public APIs unless task explicitly requires it
- All AI operations: local model for privacy-sensitive data, cloud for generation
- Paper reviews: OpenAI reviews, Gemini writes (separate models for genuine critique)
- Frontend: use shadcn/ui components, lucide-react icons, SWR hooks
- Follow existing patterns in adjacent files before writing new code
- Run tests before finishing any task
- Update agent/STATE.md and agent/NEXT_TASK.md after each task
- Security: HTML-escape all user input in HTML responses, validate URLs before fetching, scope queries by user_id for JWT auth
- Shared components: use TypingIndicator, ContextPill, AgentLogPanel, RoundtableReviewPanel, VisualContentDialogs, groupMessages() — do NOT duplicate

## Output Rules
- Be concise — do not explain unless asked
- Do not repeat context back
- Only output: code changes + minimal summary
- No emojis unless requested

## Agent Workflow
After each task:
1. Run tests if applicable
2. Update agent/STATE.md with completion status
3. Update agent/NEXT_TASK.md with next priority
4. If blocked, write to agent/BLOCKERS.md with exact reason and stop

## Stop Conditions
Stop if:
- Task completed successfully
- No clear next step
- Repeated failures detected (2+ consecutive)
- High-risk operation needs human approval (schema changes, public API changes, deployment)

## Current Priorities
1. Use the tool daily, find real pain points
2. Extract configurable framework for other users (WorkspaceOS)
3. Google Drive / Notion connectors (actual API integration)
4. LinkedIn OAuth CSRF state parameter

## Completed
- Core MVP: projects, narratives, sync, drafts, memory, blog, posting
- Agentic AI: 3-model pipeline (Gemini/OpenAI/Ollama) with privacy scan
- Deep repo context: file tree, configs, PRs, issues, commits (cached 10min)
- Co-Founder Roundtable: 8 business advisors with smart routing, parallel dispatch, DiceBear portraits
- Research Roundtable: 6 academic reviewers (Bengio, LeCun, Pinker, Ng, Xie, Topol) with portraits
- Paper Pipeline v1: adaptive 5-aspect review (retry until 8+/10, max 12 rounds)
- Paper Pipeline v2: multi-agent section-by-section with backtracking, venue-aware constraints, editing, resume
- Paper Roundtable Review: 6 reviewers parallel critique with avatars and colored badges
- Smart LaTeX templates: 8 venues (arxiv, ieee, acm, neurips, icml, iclr, acl, aaai) with auto-fetch
- PDF export: pdflatex compilation in Docker
- DOCX export: python-docx with tables, charts (matplotlib), embedded images
- Universal File Ingest: upload + URL import + AI auto-tagging + JSONB metadata
- LLM Wiki Layer: auto-maintained project summary pages, accumulates knowledge across syncs
- BibTeX generation (CrossRef + Semantic Scholar + OpenAlex), LaTeX export (pandoc + Python fallback)
- Local workspace scanner with media asset discovery
- Publishing: GitHub Releases (API), LinkedIn (OAuth 2.0), Dev.to (API), Hashnode (GraphQL), Twitter/Medium/Xiaohongshu (manual)
- Blog/Paper publishing to Dev.to + Hashnode directly from paper page
- Portfolio: combined posts + papers across multiple projects with v2 pipeline + visual tools
- Work Log: progress report generator (weekly/monthly/quarterly) with goal tracking + DOCX export
- JWT authentication: login, register, /me, refresh tokens (7-day), dual auth (Bearer + API key fallback)
- UI-editable API keys: Fernet-encrypted in DB, settings page, runtime overlay, .env fallback
- AI usage tracking: per-call logging with provider-specific cost estimates, settings dashboard
- Database backups: automated daily pg_dump with Fernet key backup, 7-day retention, manual trigger
- Startup config validation: fail-fast for missing required env vars, warn for optional
- Dashboard analytics: 12-week stacked bar chart (commits, papers, drafts, memory)
- Rate limiting: 120 req/min global via slowapi
- Health check: verifies DB connection with SELECT 1 probe
- User scoping: JWT users see only their own projects, API key = admin mode
- Shared frontend modules: TypingIndicator, ContextPill, AgentLogPanel, RoundtableReviewPanel, VisualContentDialogs, groupMessages, advisors.ts, paper-utils, markdown, hooks
- Security: XSS prevention (HTML escape), SSRF protection (private IP blocking), IDOR protection (user scoping), Fernet key permissions (0600), password length limits
- Integration test suite: 35 passing tests covering all major endpoints
- 13 Alembic migrations, 25 frontend pages, 40+ git commits

## Known Constraints
- Docker runs on OrbStack (macOS), DNS via 0.250.250.200
- DB name is `pr_secretary` (legacy — don't rename, it's in the Docker volume)
- Don't override DATABASE_URL in docker-compose `environment:` — use `env_file:` only
- Projects mounted read-only at /projects/ in backend container
- Demo projects (ProjectScribe, FastCache) have no local directories
- pgvector NULL columns can't be detected via SQLAlchemy ORM queries — use raw psql
- Semantic Scholar rate-limited (429) — OpenAlex fallback handles this automatically
- Paper pipeline v2 can take 5-15 minutes (section-by-section + roundtable review)
- Roundtable chat = 4-5 AI calls per message (router + 3-4 advisors)
- Token cost estimation is approximate (~15% error margin per provider)
- LinkedIn OAuth has no CSRF state parameter (needs session infrastructure)
- Docker backend image is ~3GB due to texlive + matplotlib

Last updated: 2026-04-08
