# Agent State

## Current Status
idle — auto-sync + timeline + extraction fix deployed

## Last Completed Task
Daily auto-sync scheduler, project timeline API + UI, background extraction race condition fix, all repos synced

## Last Updated
2026-04-02

## Session Count
4

## Tasks Completed This Session
17

## Next Session Priority
Production readiness: auth, env validation, dashboard analytics

## Completed Features
- Core MVP (projects, narratives, sync, drafts, memory, blog, posting)
- GitHub repo selector (multi-select import)
- Agentic AI (3-model pipeline: Gemini writes/OpenAI reviews/Ollama privacy-scans)
- Deep repo context (file tree, configs, PRs, issues, commits — cached 10min)
- Co-Founder AI chat (YC-trained advisor with 8 frameworks + GStack office hours)
- Research Assistant (ARIS-powered, Semantic Scholar + OpenAlex + arXiv + Unpaywall)
- Paper Pipeline (adaptive 5-aspect review, retry until 8+/10, max 12 rounds)
- Paper tools: title suggestions (5 styles), comparison tables, charts, diagrams
- LaTeX export (pandoc + fallback) + BibTeX generation (CrossRef + synthetic)
- Diagram rendering via Kroki.io (Mermaid/PlantUML/D2 → SVG)
- Local workspace scanner with media asset discovery
- Publishing: GitHub Releases (API), LinkedIn (OAuth 2.0), manual (Twitter/Medium/Xiaohongshu)
- Portfolio: combined posts + papers across multiple projects
- Global settings page for platform connections
- Agent harness system with 4 custom commands
- UI/UX: dashboard quick actions, loading skeletons, sidebar groups, page animations
- Hybrid RAG memory: pgvector + BM25 tsvector + RRF fusion + FlashRank reranking
- Contextual retrieval: AI-generated context descriptions on write
- Cross-project memory search: /memory/search-all endpoint + UI toggle
- Benchmark framework: precision@5, MRR, latency measurement
- **Daily auto-sync scheduler** (asyncio lifespan, 24h interval, sequential project sync)
- **Project Timeline** (GET /sync/timeline — commits + releases + AI insights grouped by month)
- **Timeline UI page** (vertical timeline with event type icons, month grouping)
- **Background extraction race condition fix** (explicit commit before spawning background tasks)
- All 11 projects synced with real GitHub data (57+ memory entries)
- Migrations 0005 + 0006 deployed (tsvector, GIN index, trigger, context_description fix)
- Home page refresh: global memory search, 6 stat cards, activity sidebar
- Rebranded from "AI PR Secretary" to "ProjectScribe"
- 29 git commits
