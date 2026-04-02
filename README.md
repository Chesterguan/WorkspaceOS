# ProjectScribe

AI co-founder platform for developer projects. Syncs GitHub activity, generates platform-adapted content, writes academic papers with adaptive review, manages project memory with hybrid RAG, and provides strategic advice via YC-trained chat.

## Architecture

- **Frontend**: Next.js 16 (App Router) + Tailwind CSS + shadcn/ui (base-ui) → port 3989
- **Backend**: Python FastAPI (async) → port 8989
- **Database**: PostgreSQL 15 + pgvector (768-dim) + tsvector full-text → Docker
- **AI**: Hybrid — Ollama (local/privacy), Gemini Flash (generation), OpenAI GPT-4o (review)
- **Deployment**: Docker Compose with 3 services on `projectscribe` network

## Quick Start

```bash
# Clone and configure
cp .env.example .env  # Edit with your API keys

# Start everything
docker compose up --build -d

# Frontend: http://localhost:3989
# Backend API: http://localhost:8989/docs
```

## Features

### Content Generation
- Multi-platform drafts: LinkedIn, Twitter/X, Xiaohongshu, Medium, GitHub Releases
- 3-model agentic pipeline: Gemini writes → Ollama privacy-scans → OpenAI reviews → up to 4 rounds
- Portfolio posts across multiple projects

### Research & Papers
- ARIS-powered research assistant with real citations
- Literature search: Semantic Scholar + OpenAlex + arXiv + Unpaywall
- Adaptive paper review: 5 aspects, retry until 8+/10, max 12 rounds
- Title suggestions, comparison tables, charts, diagrams (Kroki.io)
- LaTeX export + BibTeX generation (CrossRef + synthetic)

### Memory (Hybrid RAG)
- Dual retrieval: pgvector cosine similarity + BM25 full-text (tsvector)
- Reciprocal Rank Fusion + FlashRank cross-encoder reranking
- Contextual retrieval: AI-generated context descriptions on write
- Cross-project search across all memory entries

### Project Intelligence
- GitHub sync: commits, releases, README → memory entries + AI theme extraction
- Daily auto-sync scheduler (24h interval, runs all projects sequentially)
- Project timeline: chronological view of commits, releases, AI-extracted insights
- Co-Founder AI chat: YC-trained strategic advisor with 8 frameworks
- Local workspace scanner with media asset discovery

### Publishing
- GitHub Releases: API-based publishing
- LinkedIn: OAuth 2.0 (API version 202603)
- Twitter/X, Medium, Xiaohongshu: manual copy-paste (API limitations)

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async connection string |
| `GITHUB_TOKEN` | GitHub personal access token (needs `repo` scope) |
| `LOCAL_AI_PROVIDER` | `ollama` (default) |
| `CLOUD_AI_PROVIDER` | `gemini` (or `openai`, `anthropic`) |
| `OLLAMA_BASE_URL` | Ollama API URL (default: http://host.docker.internal:11434) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key (for review) |
| `API_SECRET_KEY` | API key for frontend auth |

### Frontend (build args in docker-compose.yml)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend URL (default: http://localhost:8989/api/v1) |
| `NEXT_PUBLIC_API_KEY` | Must match backend `API_SECRET_KEY` |

## Project Structure

```
backend/
  app/
    models/       # SQLAlchemy ORM models
    schemas/      # Pydantic request/response schemas
    routers/      # FastAPI route handlers (16 routers)
    services/     # Business logic (21 services)
    utils/        # Prompt templates
  alembic/        # Database migrations (6 versions)
  tests/          # Benchmark framework

frontend/
  app/            # Next.js App Router (21 pages)
  components/     # React components (shadcn/ui + custom)
  lib/            # API client, SWR hooks, types
```

## Key Workflows

1. **GitHub Sync**: Fetches commits, releases, README. Stores as memory entries with embeddings. AI extracts themes in background.
2. **Hybrid Search**: Query → pgvector cosine + BM25 tsvector → RRF fusion → FlashRank rerank → top-K results.
3. **Draft Generation**: Narrative + memory + repo context → Gemini generates → Ollama privacy-scans → OpenAI reviews → iterate.
4. **Paper Pipeline**: Topic → Gemini writes sections → OpenAI reviews 5 aspects → retry weak sections until 8+/10 → final polish.
5. **Timeline**: Commits + releases + extracted insights merged chronologically, grouped by month.
6. **Auto-Sync**: Background asyncio task syncs all projects daily with per-project timeout.

## Known Constraints

- Docker runs on OrbStack (macOS)
- Projects mounted read-only at /projects/ in backend container
- Semantic Scholar rate-limited (429) — retry with backoff + OpenAlex fallback
- Paper pipeline can take 3-10 minutes depending on rounds needed
- Twitter/X API requires paid Basic tier ($100/mo) — manual only
- Medium API closed to new integrations Jan 2025 — manual only

Last updated: 2026-04-02
