# Key Decisions Log

Append-only log of significant decisions made during development.

## Format
- [DATE] DECISION: description | WHY: reason | IMPACT: what it affects

## Decisions
- [2026-03-27] DECISION: Hybrid AI architecture (Ollama local + Gemini cloud + OpenAI review) | WHY: Privacy for code, quality for content, strong review | IMPACT: All AI services
- [2026-03-27] DECISION: Three-model agentic pipeline with privacy scan | WHY: No private data leaks to cloud | IMPACT: Draft generation flow
- [2026-03-27] DECISION: Mount local projects as read-only Docker volume | WHY: Workspace scanner needs filesystem access without write risk | IMPACT: Docker compose, scanner service
- [2026-03-29] DECISION: Twitter/X switched to manual copy-paste | WHY: Free tier API returns 402, Basic costs $100/mo | IMPACT: Publishing flow
- [2026-03-29] DECISION: Deep repo context fetches file tree, configs, PRs, issues — not just README | WHY: User found drafts were hallucinating without real project understanding | IMPACT: ai_generation, agentic_generation, repo_context
- [2026-03-29] DECISION: Agent harness pattern with state files + custom commands | WHY: Reduce token usage, enable task-executor workflow across sessions | IMPACT: Development workflow
- [2026-03-29] DECISION: All 50 API endpoints tested and passing | WHY: User wanted production-level reliability before moving on | IMPACT: Confidence in codebase
- [2026-03-29] DECISION: Embeddings changed from 1536-dim (zero-padded) to native 768-dim | WHY: Zero-padding destroyed cosine similarity making semantic search useless | IMPACT: memory_service, ai_client, migration 0004
- [2026-03-29] DECISION: Repo context cached 10min with reused HTTP client | WHY: Was making 10+ GitHub API calls per generation, risking rate limits | IMPACT: repo_context.py
- [2026-03-31] DECISION: Portfolio post feature for multi-project combined drafts | WHY: User wanted to post about multiple projects in one update | IMPACT: New /portfolio page, portfolio_template, generate_portfolio_draft
- [2026-03-31] DECISION: Global settings page for platform connections | WHY: User didn't want to re-connect LinkedIn per draft, connections should be configured once | IMPACT: /settings page, PublishButton links to settings
- [2026-04-01] DECISION: LinkedIn API version updated to 202603 | WHY: Versions 202401 and 202501 were expired (HTTP 426) | IMPACT: linkedin_service.py
- [2026-04-01] DECISION: YC-trained Co-Founder with 8 frameworks + GStack office hours | WHY: User wanted strategic advisor, not just coding assistant | IMPACT: chat_service system prompt
- [2026-04-01] DECISION: Research Assistant as separate chat role (ARIS-powered) | WHY: User needed academic writing help with real citations, separate from business advice | IMPACT: New research_service, scholar_service, research router
- [2026-04-02] DECISION: Semantic Scholar + OpenAlex + arXiv + Unpaywall + CrossRef for literature | WHY: Single source (Semantic Scholar) was rate-limited; need citation depth + open access PDFs | IMPACT: scholar_service.py
- [2026-04-02] DECISION: Paper pipeline with 5-aspect adaptive review (retry until 8+/10) | WHY: Fixed 5 rounds couldn't guarantee quality; user wanted all sections ≥ 8/10 | IMPACT: paper_service.py
- [2026-04-02] DECISION: OpenAI reviews papers, Gemini writes (separate models) | WHY: Same model reviewing itself gives inflated scores | IMPACT: paper_service reviewer separation
- [2026-04-02] DECISION: Kroki.io for diagram rendering (Mermaid/PlantUML → SVG) | WHY: Need figures for papers; Kroki is free, no auth, supports multiple diagram types | IMPACT: diagram_service.py
- [2026-04-02] DECISION: Title generation analyzes top-cited papers for patterns | WHY: Good academic titles follow field conventions; AI learns from successful examples | IMPACT: paper_service generate_paper_titles
- [2026-04-02] DECISION: Hybrid RAG pipeline (pgvector + BM25 + RRF + FlashRank) for memory search | WHY: Cosine-only search misses keyword matches; hybrid catches both semantic and lexical relevance | IMPACT: memory_service.py, migration 0005
- [2026-04-02] DECISION: FlashRank ms-marco-MiniLM-L-6-v2 for reranking (4MB model) | WHY: Lightweight cross-encoder that runs locally, no API calls needed | IMPACT: memory_service.py, requirements.txt
- [2026-04-02] DECISION: Contextual retrieval — AI generates context descriptions on write, embeds content+context | WHY: Anthropic research shows 49% fewer retrieval failures with contextual chunk descriptions | IMPACT: memory_service.py add_entry
- [2026-04-02] DECISION: Cross-project search via /memory/search-all (separate global_router) | WHY: User needs to find insights across all projects, not just current one | IMPACT: memory router, frontend api.ts, memory page UI
- [2026-04-02] DECISION: TSVector type as UserDefinedType in SQLAlchemy model | WHY: SQLAlchemy doesn't natively support tsvector; custom type maps cleanly without extra dependencies | IMPACT: memory.py model
- [2026-04-02] DECISION: Daily auto-sync via asyncio lifespan (zero new dependencies) | WHY: Imported repos had no data until manually synced; daily sync keeps memory fresh | IMPACT: main.py lifespan, all projects
- [2026-04-02] DECISION: Explicit db.commit() before spawning background tasks | WHY: Background tasks open their own session and couldn't see uncommitted SyncRun data (race condition) | IMPACT: github_sync.py run_sync
- [2026-04-02] DECISION: Timeline endpoint on /sync/timeline (before /{sync_run_id} routes) | WHY: Merges commits + releases + AI insights into one chronological view per project | IMPACT: sync router, new timeline page
