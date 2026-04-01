from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ai, drafts, memory, narratives, projects, sync
from app.routers import agentic, blog, chat, github, linkedin, posting, publish, workspace
from app.routers import paper, research
from app.routers.chat import starters_router as chat_starters_router
from app.routers.research import starters_router as research_starters_router

app = FastAPI(
    title="AI PR Secretary",
    description="Backend API for generating AI-powered PR content from GitHub activity.",
    version="0.1.0",
)

# Allow all origins in development. Tighten this in production by replacing
# allow_origins with a specific list of frontend URLs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Changed from True — incompatible with allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(narratives.router, prefix=API_PREFIX)
app.include_router(sync.router, prefix=API_PREFIX)
app.include_router(drafts.router, prefix=API_PREFIX)
app.include_router(ai.router, prefix=API_PREFIX)
app.include_router(memory.router, prefix=API_PREFIX)
app.include_router(github.router, prefix=API_PREFIX)
app.include_router(posting.router, prefix=API_PREFIX)
app.include_router(blog.router, prefix=API_PREFIX)
app.include_router(agentic.router, prefix=API_PREFIX)
app.include_router(workspace.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(chat_starters_router, prefix=API_PREFIX)
app.include_router(publish.router, prefix=API_PREFIX)
app.include_router(linkedin.router, prefix=API_PREFIX)
app.include_router(research.router, prefix=API_PREFIX)
app.include_router(research_starters_router, prefix=API_PREFIX)
app.include_router(paper.router, prefix=API_PREFIX)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok", "version": app.version}
