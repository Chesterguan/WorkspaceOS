# Agent State

## Current Status
idle — full QA passed, all docs + memory updated

## Last Completed Task
Session 4 complete: hybrid RAG memory, auto-sync, timeline, paper fixes (BibTeX/LaTeX/charts/visual tools), code deduplication, rebrand, QA verification

## Last Updated
2026-04-03

## Session Count
4

## Tasks Completed This Session
30+

## Next Session Priority
Production readiness: auth, env validation, dashboard analytics, unit tests

## Completed Features
- Core MVP (projects, narratives, sync, drafts, memory, blog, posting)
- GitHub repo selector (multi-select import), 11 projects synced
- Agentic AI (3-model pipeline: Gemini writes/OpenAI reviews/Ollama privacy-scans)
- Deep repo context (file tree, configs, PRs, issues, commits — cached 10min)
- Co-Founder AI chat (YC-trained advisor with 8 frameworks + GStack office hours)
- Research Assistant (ARIS-powered, Semantic Scholar + OpenAlex fallback + arXiv + Unpaywall)
- Paper Pipeline (adaptive 5-aspect review, retry until 8+/10, max 12 rounds)
- Paper tools: auto-title suggestions (5 styles on page load), comparison tables, charts (Mermaid/Kroki), architecture diagrams — on BOTH single-project and portfolio pages
- BibTeX generation (CrossRef + OpenAlex fallback) + LaTeX export (pandoc in Docker + Python fallback)
- Hybrid RAG memory: pgvector + BM25 tsvector + RRF fusion + FlashRank MiniLM-L-12-v2 reranking
- Contextual retrieval: AI-generated context descriptions on write
- Cross-project memory search + embedding backfill endpoint
- README upsert on sync (prevents duplicates), migration 0007 cleaned 40 old dupes
- Daily auto-sync scheduler (asyncio lifespan, 23h gap check, 300s timeout per project)
- Project timeline (commits + releases + AI insights grouped by month)
- Home page: global memory search, 6 stat cards, activity feed sidebar
- Dynamic browser tab titles (ProjectScribe | Project | Page)
- Shared frontend modules: markdown.ts, paper-utils.ts, useElapsedTimer, usePassSimulation, usePaperExport
- Local workspace scanner with media asset discovery
- Publishing: GitHub Releases (API), LinkedIn (OAuth 2.0), manual (Twitter/Medium/Xiaohongshu)
- Portfolio: combined posts + papers across multiple projects with visual tools
- Benchmark framework: precision@5, MRR, latency measurement
- Rebranded from "AI PR Secretary" to "ProjectScribe"
- 7 Alembic migrations, 21 frontend pages, 33 git commits
- Full QA: 12/12 API endpoints passing, 48/48 memory entries with embeddings, 0 duplicates
