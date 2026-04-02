# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
AI PR Secretary — a multi-project content management platform that syncs GitHub activity, generates platform-adapted content drafts, writes academic papers, and acts as an AI co-founder and research assistant for developer projects.

## Architecture
- Frontend: Next.js 16 (App Router) + Tailwind + shadcn/ui → port 3989
- Backend: Python FastAPI (async) → port 8989
- Database: PostgreSQL 15 + pgvector (768-dim) → Docker internal
- AI: Hybrid — Ollama (local/privacy), Gemini Flash (generation), OpenAI GPT-4o (review)
- Deployment: Docker Compose with 3 services on `pr-secretary` network + backend_data volume

## Key Modules
- **Services** (19): ai_client, ai_generation, agentic_generation, github_sync, github_client, memory_service, narrative_service, draft_service, blog_service, chat_service, workspace_scanner, publish_service, linkedin_service, repo_context, extraction_service, consolidation_service, feedback_service, research_service, paper_service, scholar_service, diagram_service
- **Routers** (16): projects, narratives, sync, drafts, ai, memory, github, posting, blog, agentic, workspace, chat, publish, linkedin, research, paper
- **AI Pipeline**: Gemini generates → Ollama privacy-scans → OpenAI reviews → up to 4 rounds
- **Paper Pipeline**: Adaptive review — 5 aspects × retry until 8+/10 → final polish (max 12 rounds)
- **Memory**: pgvector 768-dim embeddings via Ollama nomic-embed-text, cosine similarity search
- **Publishing**: GitHub Releases (API), LinkedIn (OAuth 2.0), Twitter/Medium/Xiaohongshu (manual)
- **Research**: Semantic Scholar + OpenAlex + arXiv + Unpaywall + CrossRef BibTeX + Kroki.io diagrams

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
1. Production readiness (proper auth, env management)
2. Auto-sync on schedule
3. Dashboard analytics
4. More platform integrations

## Completed
- Core MVP: projects, narratives, sync, drafts, memory, blog, posting
- Agentic AI: 3-model pipeline (Gemini/OpenAI/Ollama) with privacy scan
- Deep repo context: file tree, configs, PRs, issues, commits (cached 10min)
- Co-Founder AI chat: YC-trained strategic advisor with 8 frameworks + GStack office hours
- Research Assistant: ARIS-powered academic writing with Semantic Scholar citations
- Paper Pipeline: adaptive 5-aspect review (retry until 8+/10, max 12 rounds), title suggestions, table/chart/figure generation
- Local workspace scanner with media asset discovery
- Publishing: GitHub Releases (API), LinkedIn (OAuth 2.0), Twitter/Medium/Xiaohongshu (manual)
- Portfolio: combined posts + papers across multiple projects with full publishing
- Global settings page for platform connections
- Agent harness system with custom commands (/next-task, /review-task, /plan-task, /status)
- UI/UX: loading skeletons, error states, sidebar groups, page animations, dashboard quick actions
- Embeddings: 768-dim native vectors, cosine similarity working
- Git repo: 25 commits

## Known Constraints
- Docker runs on OrbStack (macOS), DNS via 0.250.250.200
- Projects mounted read-only at /projects/ in backend container
- Demo projects (ProjectScribe, FastCache) have no local directories
- Medium API closed Jan 2025 — manual only
- Xiaohongshu has no public API — manual only
- Twitter/X API requires paid Basic tier ($100/mo) — manual only
- LinkedIn token persisted in DB, API version 202603
- GitHub token needs `repo` write scope for release publishing
- Repo context cached 10min to avoid GitHub API rate limits
- Semantic Scholar rate-limited (429) — retry with backoff + OpenAlex fallback
- Paper pipeline can take 3-10 minutes depending on rounds needed

Last updated: 2026-04-02
