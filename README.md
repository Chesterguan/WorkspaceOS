# AI PR Secretary

Multi-project content management tool for developers. Sync GitHub activity, maintain project narratives, generate platform-adapted content drafts (LinkedIn, X/Twitter, Xiaohongshu, Medium, GitHub releases), and build long-term memory of each project's public story.

## Architecture

- **Frontend**: Next.js 14 (App Router) + Tailwind CSS + shadcn/ui
- **Backend**: Python FastAPI (async)
- **Database**: PostgreSQL + pgvector for semantic memory search
- **AI**: Switchable between OpenAI and Anthropic via env var

## Prerequisites

- Node.js 18+
- Python 3.11+
- PostgreSQL 15+ with pgvector extension

## Quick Start

### 1. Database

```bash
createdb pr_secretary
# Install pgvector extension (if not already):
psql pr_secretary -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your API keys
alembic upgrade head
python seed.py  # Load demo data
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

App: http://localhost:3000

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) |
| `GITHUB_TOKEN` | GitHub personal access token |
| `ACTIVE_AI_PROVIDER` | `openai` or `anthropic` |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `API_SECRET_KEY` | API key for frontend auth |
| `MAX_COMMITS_PER_SYNC` | Max commits per GitHub sync (default: 50) |

### Frontend (`frontend/.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend URL (default: http://localhost:8000/api/v1) |
| `NEXT_PUBLIC_API_KEY` | Must match backend `API_SECRET_KEY` |

## Project Structure

```
backend/
  app/
    models/       # SQLAlchemy ORM models
    schemas/      # Pydantic request/response schemas
    routers/      # FastAPI route handlers
    services/     # Business logic (github_sync, ai_generation, memory, drafts, narratives)
    utils/        # Prompt templates
  alembic/        # Database migrations
  seed.py         # Demo data seeder

frontend/
  app/            # Next.js App Router pages
  components/     # React components
  lib/            # API client, hooks, types
```

## Key Workflows

1. **GitHub Sync**: Fetches commits, releases, README from linked repo. AI generates an evolution summary stored as memory.
2. **Draft Generation**: Uses project narrative + memory context + sync data to generate platform-adapted content.
3. **Draft Studio**: Edit, version, and manage draft lifecycle (draft -> approved -> archived).
4. **Narrative Editor**: Maintain positioning, audience, tone, preferred/avoided angles, and FAQ.
5. **Memory**: Append-only log with vector embeddings for semantic retrieval during generation.

Last updated: 2026-03-27
