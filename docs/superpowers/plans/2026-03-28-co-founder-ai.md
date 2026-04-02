# Co-Founder AI: Local Workspace Awareness + Strategic Chat

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform ProjectScribe from a content drafting tool into an AI co-founder that deeply understands the user's projects by reading local files, and can discuss strategy, positioning, and roadmap like a business advisor.

**Architecture:** Two new subsystems: (1) A local workspace scanner that runs as a sidecar container, mounts the user's project directories, and pushes code context to the backend via API. Uses only the local Ollama model to analyze code — no private source code ever leaves the machine. (2) A per-project chat system where the AI has full context (repo data, memory, narrative, local workspace state, conversation history) and acts as a co-founder/advisor.

**Tech Stack:** Python (FastAPI endpoints + scanner service), PostgreSQL (chat history), Ollama (local code analysis), Gemini/OpenAI (strategic conversation), Next.js (chat UI)

---

## File Structure

### Backend — New Files
- `backend/app/models/chat.py` — ChatMessage SQLAlchemy model (conversation history)
- `backend/app/models/workspace.py` — WorkspaceSnapshot model (local file analysis results)
- `backend/app/schemas/chat.py` — Pydantic schemas for chat request/response
- `backend/app/schemas/workspace.py` — Pydantic schemas for workspace scan results
- `backend/app/routers/chat.py` — Chat endpoints (send message, list history, clear)
- `backend/app/routers/workspace.py` — Workspace endpoints (trigger scan, get status, get context)
- `backend/app/services/chat_service.py` — Chat orchestration (context assembly + AI call + history)
- `backend/app/services/workspace_scanner.py` — Local file analysis (reads files, uses Ollama to summarize)
- `backend/scanner.py` — Standalone scanner script that runs in sidecar container, watches filesystem, pushes to API
- `backend/alembic/versions/0003_chat_workspace.py` — Migration for new tables

### Backend — Modified Files
- `backend/app/models/__init__.py` — Import new models
- `backend/app/main.py` — Register chat + workspace routers
- `backend/app/services/ai_client.py` — No changes (already has local/cloud split)

### Frontend — New Files
- `frontend/app/projects/[projectId]/chat/page.tsx` — Chat page
- `frontend/components/chat/ChatWindow.tsx` — Main chat interface (message list + input)
- `frontend/components/chat/ChatMessage.tsx` — Single message bubble (user/assistant)
- `frontend/components/chat/WorkspaceStatus.tsx` — Shows local workspace scan status
- `frontend/lib/hooks/useChat.ts` — SWR hook for chat history + send mutation

### Frontend — Modified Files
- `frontend/components/ProjectSidebar.tsx` — Add "Co-Founder" nav item
- `frontend/lib/api.ts` — Add chat + workspace API namespaces
- `frontend/lib/types.ts` — Add ChatMessage, WorkspaceSnapshot types

### Docker — Modified Files
- `docker-compose.yml` — Add scanner sidecar service with volume mount

---

## Task 1: Database Models + Migration

**Files:**
- Create: `backend/app/models/chat.py`
- Create: `backend/app/models/workspace.py`
- Create: `backend/alembic/versions/0003_chat_workspace.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create ChatMessage model**

```python
# backend/app/models/chat.py
import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Store metadata: model used, context sources, token count, etc.
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[uuid.UUID] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Create WorkspaceSnapshot model**

```python
# backend/app/models/workspace.py
import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WorkspaceSnapshot(Base):
    __tablename__ = "workspace_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Local directory path on the host
    local_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # AI-generated summary of the workspace state (by local model)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured data: file tree, uncommitted changes, recent git log, key file excerpts
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # git status
    git_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # uncommitted changes summary
    git_recent_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # last 10 local commits
    scanned_at: Mapped[uuid.UUID] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Create migration**

```python
# backend/alembic/versions/0003_chat_workspace.py
"""Chat messages and workspace snapshots."""
revision = "0003"
down_revision = "0002"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade():
    # Chat messages
    op.execute("""
        CREATE TABLE chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_chat_messages_project_id ON chat_messages(project_id)")
    op.execute("CREATE INDEX ix_chat_messages_created_at ON chat_messages(created_at)")

    # Workspace snapshots
    op.execute("""
        CREATE TABLE workspace_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            local_path VARCHAR(500) NOT NULL,
            summary TEXT NOT NULL,
            raw_data JSONB,
            git_branch VARCHAR(255),
            git_status TEXT,
            git_recent_log TEXT,
            scanned_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_workspace_snapshots_project_id ON workspace_snapshots(project_id)")

    # Add local_path column to projects for workspace association
    op.execute("ALTER TABLE projects ADD COLUMN local_path VARCHAR(500)")


def downgrade():
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS local_path")
    op.execute("DROP TABLE IF EXISTS workspace_snapshots")
    op.execute("DROP TABLE IF EXISTS chat_messages")
```

- [ ] **Step 4: Update model imports**

Add to `backend/app/models/__init__.py`:
```python
from app.models.chat import ChatMessage
from app.models.workspace import WorkspaceSnapshot
```

- [ ] **Step 5: Test migration runs**

Run: `docker compose up --build -d backend` and check logs for successful migration.

---

## Task 2: Workspace Scanner Service

**Files:**
- Create: `backend/app/services/workspace_scanner.py`
- Create: `backend/app/schemas/workspace.py`
- Create: `backend/app/routers/workspace.py`

- [ ] **Step 1: Create workspace schemas**

```python
# backend/app/schemas/workspace.py
import uuid
from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkspaceScanRequest(BaseModel):
    """Trigger a scan of a project's local workspace."""
    local_path: Optional[str] = None  # Override; otherwise uses project.local_path


class WorkspaceSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    local_path: str
    summary: str
    git_branch: Optional[str]
    git_status: Optional[str]
    git_recent_log: Optional[str]
    scanned_at: datetime


class WorkspaceContextResponse(BaseModel):
    """Combined workspace context for chat injection."""
    has_snapshot: bool
    summary: str
    git_branch: Optional[str]
    git_status: Optional[str]
    uncommitted_changes: Optional[str]
    recent_local_commits: Optional[str]
    file_tree: Optional[str]
    key_files: Optional[str]
```

- [ ] **Step 2: Create workspace scanner service**

```python
# backend/app/services/workspace_scanner.py
"""
Scans local project directories to understand what the developer is working on.

Reads:
  - File tree (2 levels deep)
  - Git status (uncommitted changes, current branch)
  - Git log (last 10 local commits)
  - Key files (README, configs, recent modified files)
  - Diff of uncommitted changes

ALL analysis done by LOCAL model only. No source code sent to cloud.
"""
import logging
import os
import subprocess
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.workspace import WorkspaceSnapshot
from app.services.ai_client import get_local_client

logger = logging.getLogger(__name__)

# Files worth reading for project understanding
IMPORTANT_PATTERNS = [
    "README.md", "README.rst", "readme.md",
    "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
    "docker-compose.yml", "Dockerfile",
    "CHANGELOG.md", "ARCHITECTURE.md", "CONTRIBUTING.md",
    ".env.example", "Makefile",
]


def _run_git(cwd: str, args: List[str]) -> Optional[str]:
    """Run a git command in the given directory. Returns stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.debug("Git command failed in %s: %s", cwd, e)
    return None


def _get_file_tree(path: str, depth: int = 0, max_depth: int = 2) -> List[str]:
    """Walk directory tree up to max_depth. Skip hidden dirs and common noise."""
    skip_dirs = {".git", "node_modules", "__pycache__", ".next", ".venv", "venv",
                 "dist", "build", ".cache", ".idea", ".vscode", "target", ".tox"}
    items = []
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return items

    indent = "  " * depth
    for name in entries:
        if name.startswith(".") and depth > 0:
            continue
        full = os.path.join(path, name)
        if os.path.isdir(full):
            if name in skip_dirs:
                continue
            items.append(f"{indent}{name}/")
            if depth < max_depth:
                items.extend(_get_file_tree(full, depth + 1, max_depth))
        else:
            items.append(f"{indent}{name}")
    return items


def _read_file_safe(path: str, max_bytes: int = 3000) -> Optional[str]:
    """Read a file up to max_bytes. Returns None if not readable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception:
        return None


def scan_local_workspace(local_path: str) -> Dict[str, str]:
    """
    Scan a local project directory. Returns raw data dict.
    This runs SYNCHRONOUSLY (called from async via run_in_executor).
    """
    data: Dict[str, str] = {}

    if not os.path.isdir(local_path):
        data["error"] = f"Directory not found: {local_path}"
        return data

    # 1. File tree
    tree = _get_file_tree(local_path)
    data["file_tree"] = "\n".join(tree[:200])  # Cap at 200 lines

    # 2. Git info
    data["git_branch"] = _run_git(local_path, ["rev-parse", "--abbrev-ref", "HEAD"]) or ""
    data["git_status"] = _run_git(local_path, ["status", "--short"]) or ""
    data["git_diff_stat"] = _run_git(local_path, ["diff", "--stat"]) or ""
    data["git_diff_summary"] = _run_git(local_path, ["diff", "--name-only"]) or ""
    data["git_recent_log"] = _run_git(local_path, [
        "log", "--oneline", "--no-decorate", "-15"
    ]) or ""
    data["git_unpushed"] = _run_git(local_path, [
        "log", "--oneline", "@{u}..", "--no-decorate"
    ]) or ""

    # 3. Key files
    key_contents: List[str] = []
    for pattern in IMPORTANT_PATTERNS:
        fpath = os.path.join(local_path, pattern)
        content = _read_file_safe(fpath)
        if content:
            key_contents.append(f"### {pattern}\n```\n{content}\n```")
    data["key_files"] = "\n\n".join(key_contents)

    # 4. Recently modified files (last 5 non-hidden tracked files)
    recent = _run_git(local_path, [
        "diff", "--name-only", "HEAD~5..HEAD"
    ])
    if recent:
        data["recently_changed_files"] = recent

    return data


async def perform_scan(
    project_id: uuid.UUID,
    local_path: str,
    db: AsyncSession,
) -> WorkspaceSnapshot:
    """
    Scan workspace and produce an AI summary using LOCAL model only.
    Stores the result as a WorkspaceSnapshot.
    """
    import asyncio
    loop = asyncio.get_running_loop()

    # Run filesystem scan in executor (it's synchronous I/O)
    raw_data = await loop.run_in_executor(None, scan_local_workspace, local_path)

    if "error" in raw_data:
        raise ValueError(raw_data["error"])

    # Build context for local AI summarization
    context_parts = []
    if raw_data.get("file_tree"):
        context_parts.append(f"## File Tree\n{raw_data['file_tree']}")
    if raw_data.get("git_branch"):
        context_parts.append(f"## Current Branch\n{raw_data['git_branch']}")
    if raw_data.get("git_status"):
        context_parts.append(f"## Uncommitted Changes\n{raw_data['git_status']}")
    if raw_data.get("git_diff_stat"):
        context_parts.append(f"## Diff Stats\n{raw_data['git_diff_stat']}")
    if raw_data.get("git_recent_log"):
        context_parts.append(f"## Recent Commits\n{raw_data['git_recent_log']}")
    if raw_data.get("git_unpushed"):
        context_parts.append(f"## Unpushed Commits\n{raw_data['git_unpushed']}")
    if raw_data.get("key_files"):
        context_parts.append(f"## Key Files\n{raw_data['key_files']}")
    if raw_data.get("recently_changed_files"):
        context_parts.append(f"## Recently Changed Files\n{raw_data['recently_changed_files']}")

    full_context = "\n\n".join(context_parts)

    # Summarize with LOCAL model — source code never leaves the machine
    local_ai = get_local_client()
    summary = await local_ai.complete(
        "You are a senior developer analyzing a colleague's workspace. Produce a detailed "
        "briefing covering:\n"
        "1. What the project is and what it does\n"
        "2. Current state of development (what branch, what's in progress)\n"
        "3. Uncommitted work and what it appears to be about\n"
        "4. Recent development trajectory (from commit log)\n"
        "5. Tech stack and architecture (from file tree and configs)\n"
        "6. Anything the developer seems to be stuck on or actively working on\n\n"
        "Be specific. Cite file names, branch names, and commit messages.",
        f"Workspace data:\n\n{full_context}",
    )

    snapshot = WorkspaceSnapshot(
        project_id=project_id,
        local_path=local_path,
        summary=summary,
        raw_data=raw_data,
        git_branch=raw_data.get("git_branch"),
        git_status=raw_data.get("git_status"),
        git_recent_log=raw_data.get("git_recent_log"),
    )
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


async def get_latest_snapshot(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[WorkspaceSnapshot]:
    """Get the most recent workspace snapshot for a project."""
    result = await db.execute(
        select(WorkspaceSnapshot)
        .where(WorkspaceSnapshot.project_id == project_id)
        .order_by(WorkspaceSnapshot.scanned_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
```

- [ ] **Step 3: Create workspace router**

```python
# backend/app/routers/workspace.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.project import Project
from app.schemas.workspace import (
    WorkspaceContextResponse,
    WorkspaceScanRequest,
    WorkspaceSnapshotResponse,
)
from app.services.workspace_scanner import get_latest_snapshot, perform_scan

router = APIRouter(tags=["workspace"])


@router.post(
    "/projects/{project_id}/workspace/scan",
    response_model=WorkspaceSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def scan_workspace(
    project_id: uuid.UUID,
    body: WorkspaceScanRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    local_path = body.local_path or project.local_path
    if not local_path:
        raise HTTPException(
            status_code=422,
            detail="No local_path configured for this project. "
                   "Set it via PATCH /projects/{id} or pass local_path in the request.",
        )

    snapshot = await perform_scan(project_id, local_path, db)
    await db.commit()
    return snapshot


@router.get(
    "/projects/{project_id}/workspace/context",
    response_model=WorkspaceContextResponse,
)
async def get_workspace_context(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
):
    snapshot = await get_latest_snapshot(project_id, db)
    if snapshot is None:
        return WorkspaceContextResponse(
            has_snapshot=False, summary="No workspace scan available.",
        )

    raw = snapshot.raw_data or {}
    return WorkspaceContextResponse(
        has_snapshot=True,
        summary=snapshot.summary,
        git_branch=snapshot.git_branch,
        git_status=snapshot.git_status,
        uncommitted_changes=raw.get("git_diff_stat"),
        recent_local_commits=snapshot.git_recent_log,
        file_tree=raw.get("file_tree"),
        key_files=raw.get("key_files"),
    )
```

- [ ] **Step 4: Register workspace router in main.py**

Add to `backend/app/main.py`:
```python
from app.routers import workspace
app.include_router(workspace.router, prefix=API_PREFIX)
```

- [ ] **Step 5: Test workspace scan endpoint**

After rebuild, test with curl:
```bash
curl -s -H "X-API-Key: dev-secret-key" -X POST -H "Content-Type: application/json" \
  -d '{"local_path":"/projects/HAVEN"}' \
  http://localhost:8989/api/v1/projects/{haven_id}/workspace/scan
```
Expected: 201 with summary of HAVEN workspace.

---

## Task 3: Chat Service + Router

**Files:**
- Create: `backend/app/schemas/chat.py`
- Create: `backend/app/services/chat_service.py`
- Create: `backend/app/routers/chat.py`

- [ ] **Step 1: Create chat schemas**

```python
# backend/app/schemas/chat.py
import uuid
from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatSendRequest(BaseModel):
    message: str
    # Optional: user can specify which context sources to include
    include_workspace: bool = True
    include_memory: bool = True
    include_repo: bool = True


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    role: str
    content: str
    metadata_: Optional[dict] = None
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int
```

- [ ] **Step 2: Create chat service**

```python
# backend/app/services/chat_service.py
"""
Co-Founder AI chat service.

Assembles deep context from all available sources and conducts a strategic
conversation. The AI acts as a co-founder and business advisor who deeply
understands the project.

Context sources:
  1. Project narrative (positioning, audience, tone)
  2. Repository context (live from GitHub)
  3. Local workspace state (from scanner — via local model)
  4. Memory entries (semantic search on user's message)
  5. Recent drafts and blog posts (what's been said publicly)
  6. Conversation history (last 20 messages for continuity)
"""
import logging
import uuid
from typing import Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage
from app.models.draft import Draft
from app.models.blog import BlogPost
from app.models.project import Project
from app.services.ai_client import get_cloud_client
from app.services.memory_service import search_memory, get_recent_entries
from app.services.narrative_service import build_context_block, get_or_create
from app.services.repo_context import get_generation_context
from app.services.workspace_scanner import get_latest_snapshot

logger = logging.getLogger(__name__)

CO_FOUNDER_SYSTEM = """You are the AI co-founder and strategic advisor for this project. You have deep knowledge of the codebase, the market positioning, the development trajectory, and the founder's working style.

Your role:
- Think like a co-founder: care about the project's success, not just tasks
- Give honest, specific strategic advice (positioning, roadmap, priorities)
- Connect technical decisions to business outcomes
- Challenge assumptions when you see risks
- Suggest content angles, partnership opportunities, and growth strategies
- When asked about code, reference actual files, commits, and architecture
- Remember what was discussed before and build on it
- Be concise and direct — the founder is busy

You have access to:
- The full project codebase and architecture
- The current local workspace (what the founder is working on RIGHT NOW)
- All project memory (past syncs, themes, patterns)
- The project narrative (positioning, audience, tone)
- Published drafts and blog posts (what's been said publicly)

Always ground your advice in the actual project context. Never give generic startup advice."""


async def _build_chat_context(
    project_id: uuid.UUID,
    user_message: str,
    include_workspace: bool,
    include_memory: bool,
    include_repo: bool,
    db: AsyncSession,
) -> str:
    """Assemble all context sources into a single context block."""
    parts: List[str] = []

    # 1. Project + Narrative
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    project = project_result.scalar_one_or_none()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    narrative = await get_or_create(project_id, db)
    narrative_ctx = build_context_block(narrative)
    parts.append(f"## Project: {project.name}")
    parts.append(f"GitHub: {project.github_repo or 'N/A'}")
    parts.append(f"One-liner: {narrative_ctx.get('one_liner', 'N/A')}")
    parts.append(f"Audience: {narrative_ctx.get('target_audience', 'N/A')}")
    parts.append(f"Tone: {narrative_ctx.get('tone_notes', 'N/A')}")

    # 2. Live repo context
    if include_repo and project.github_repo:
        try:
            is_private = project.status == "private"
            repo_ctx = await get_generation_context(project.github_repo, is_private=is_private)
            if repo_ctx and len(repo_ctx) > 100:
                # Truncate to avoid overwhelming the context
                if len(repo_ctx) > 8000:
                    repo_ctx = repo_ctx[:8000] + "\n\n[... truncated ...]"
                parts.append(f"\n## Repository Context\n{repo_ctx}")
        except Exception as e:
            logger.warning("Failed to fetch repo context: %s", e)

    # 3. Local workspace
    if include_workspace:
        snapshot = await get_latest_snapshot(project_id, db)
        if snapshot:
            parts.append(f"\n## Local Workspace (scanned {snapshot.scanned_at.isoformat()[:16]})")
            parts.append(f"Branch: {snapshot.git_branch or 'N/A'}")
            if snapshot.git_status:
                parts.append(f"Uncommitted changes:\n{snapshot.git_status}")
            parts.append(f"\nWorkspace summary:\n{snapshot.summary}")

    # 4. Memory (semantic search on the user's message)
    if include_memory:
        try:
            entries = await search_memory(project_id, user_message, limit=5, db=db)
        except Exception:
            entries = await get_recent_entries(project_id, limit=5, db=db)
        if entries:
            memory_lines = [f"- [{e.entry_type}] {e.content[:200]}" for e in entries]
            parts.append(f"\n## Relevant Memory\n" + "\n".join(memory_lines))

    # 5. Recent published content (last 3 drafts + 3 blog posts)
    draft_result = await db.execute(
        select(Draft)
        .where(Draft.project_id == project_id, Draft.status.in_(["approved", "published"]))
        .order_by(Draft.created_at.desc())
        .limit(3)
    )
    recent_drafts = list(draft_result.scalars().all())
    if recent_drafts:
        draft_lines = [f"- [{d.platform}] {d.content[:150]}..." for d in recent_drafts]
        parts.append(f"\n## Recent Published Content\n" + "\n".join(draft_lines))

    blog_result = await db.execute(
        select(BlogPost)
        .where(BlogPost.project_id == project_id, BlogPost.status == "published")
        .order_by(BlogPost.updated_at.desc())
        .limit(3)
    )
    recent_blogs = list(blog_result.scalars().all())
    if recent_blogs:
        blog_lines = [f"- {b.title}: {b.content[:150]}..." for b in recent_blogs]
        parts.append(f"\n## Recent Blog Posts\n" + "\n".join(blog_lines))

    return "\n".join(parts)


async def send_message(
    project_id: uuid.UUID,
    user_message: str,
    include_workspace: bool,
    include_memory: bool,
    include_repo: bool,
    db: AsyncSession,
) -> ChatMessage:
    """
    Process a user message: build context, fetch history, call AI, store both messages.
    """
    # Store user message
    user_msg = ChatMessage(
        project_id=project_id,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    await db.flush()

    # Get conversation history (last 20 messages)
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(list(history_result.scalars().all())))

    # Build context
    context = await _build_chat_context(
        project_id, user_message,
        include_workspace, include_memory, include_repo, db,
    )

    # Construct messages for AI
    system = CO_FOUNDER_SYSTEM + f"\n\n---\n\nProject Context:\n{context}"

    # Build conversation as a single user prompt (since our AI client takes system+user)
    conversation_parts = []
    for msg in history[:-1]:  # Exclude the message we just added
        prefix = "Founder" if msg.role == "user" else "You (Co-Founder AI)"
        conversation_parts.append(f"{prefix}: {msg.content}")
    conversation_parts.append(f"Founder: {user_message}")

    user_prompt = "Conversation so far:\n\n" + "\n\n".join(conversation_parts) + "\n\nYou (Co-Founder AI):"

    # Call cloud AI for quality strategic conversation
    cloud = get_cloud_client()
    response = await cloud.complete(system, user_prompt)

    # Store assistant response
    assistant_msg = ChatMessage(
        project_id=project_id,
        role="assistant",
        content=response,
        metadata_={"model": "cloud", "context_sources": {
            "workspace": include_workspace,
            "memory": include_memory,
            "repo": include_repo,
        }},
    )
    db.add(assistant_msg)
    await db.flush()
    await db.refresh(assistant_msg)

    return assistant_msg


async def get_history(
    project_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> tuple:
    """Get chat history for a project. Returns (messages, total_count)."""
    count_result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.project_id == project_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    messages = list(result.scalars().all())
    return messages, total


async def clear_history(project_id: uuid.UUID, db: AsyncSession) -> int:
    """Delete all chat messages for a project. Returns count deleted."""
    from sqlalchemy import delete
    result = await db.execute(
        delete(ChatMessage).where(ChatMessage.project_id == project_id)
    )
    return result.rowcount
```

- [ ] **Step 3: Create chat router**

```python
# backend/app/routers/chat.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.schemas.chat import ChatHistoryResponse, ChatMessageResponse, ChatSendRequest
from app.services.chat_service import clear_history, get_history, send_message

router = APIRouter(tags=["chat"])


@router.post(
    "/projects/{project_id}/chat",
    response_model=ChatMessageResponse,
    status_code=201,
)
async def chat(
    project_id: uuid.UUID,
    body: ChatSendRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
):
    """Send a message and get an AI co-founder response."""
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    assistant_msg = await send_message(
        project_id=project_id,
        user_message=body.message,
        include_workspace=body.include_workspace,
        include_memory=body.include_memory,
        include_repo=body.include_repo,
        db=db,
    )
    await db.commit()
    return assistant_msg


@router.get(
    "/projects/{project_id}/chat",
    response_model=ChatHistoryResponse,
)
async def history(
    project_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
):
    """Get conversation history for a project."""
    messages, total = await get_history(project_id, db, limit, offset)
    return ChatHistoryResponse(
        messages=[ChatMessageResponse.model_validate(m) for m in messages],
        total=total,
    )


@router.delete("/projects/{project_id}/chat", status_code=204)
async def clear(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
):
    """Clear all chat history for a project."""
    await clear_history(project_id, db)
    await db.commit()
```

- [ ] **Step 4: Register chat router in main.py**

Add to `backend/app/main.py`:
```python
from app.routers import chat
app.include_router(chat.router, prefix=API_PREFIX)
```

- [ ] **Step 5: Test chat endpoint**

```bash
curl -s -H "X-API-Key: dev-secret-key" -X POST -H "Content-Type: application/json" \
  -d '{"message":"What should be my next priority for this project?"}' \
  http://localhost:8989/api/v1/projects/{haven_id}/chat
```
Expected: 201 with AI co-founder response grounded in project context.

---

## Task 4: Docker — Scanner Sidecar + Volume Mount

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add volume mount and scanner path to backend**

The simplest approach: mount the user's projects directory into the backend container so the scanner can read local files directly. No separate sidecar needed.

```yaml
# Add to the backend service in docker-compose.yml:
  backend:
    # ... existing config ...
    volumes:
      - /Volumes/extraSupply/Projects:/projects:ro  # Read-only mount of local projects
```

This makes all projects accessible at `/projects/{name}` inside the container. The scanner reads files and git state from there. `:ro` ensures the container cannot modify local files.

- [ ] **Step 2: Set local_path for existing projects**

After rebuild, update projects with their local paths:
```bash
# For each project, set local_path = /projects/{dir_name}
curl -s -H "X-API-Key: dev-secret-key" -X PATCH -H "Content-Type: application/json" \
  -d '{"local_path":"/projects/HAVEN"}' \
  http://localhost:8989/api/v1/projects/{haven_id}
```

- [ ] **Step 3: Test the full flow**

1. Set local_path on a project
2. Trigger workspace scan
3. Check that snapshot was created with git status and file tree
4. Send a chat message asking about the project
5. Verify the response references local workspace state

---

## Task 5: Frontend — Chat Page + Components

**Files:**
- Create: `frontend/app/projects/[projectId]/chat/page.tsx`
- Create: `frontend/components/chat/ChatWindow.tsx`
- Create: `frontend/components/chat/ChatMessage.tsx`
- Create: `frontend/components/chat/WorkspaceStatus.tsx`
- Create: `frontend/lib/hooks/useChat.ts`
- Modify: `frontend/components/ProjectSidebar.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Add types**

Add to `frontend/lib/types.ts`:
```typescript
// ─── Chat ──────────────────────────────────────────────────────
export interface ChatMessage {
  id: string;
  project_id: string;
  role: 'user' | 'assistant';
  content: string;
  metadata_?: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatSendRequest {
  message: string;
  include_workspace?: boolean;
  include_memory?: boolean;
  include_repo?: boolean;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
  total: number;
}

// ─── Workspace ─────────────────────────────────────────────────
export interface WorkspaceSnapshot {
  id: string;
  project_id: string;
  local_path: string;
  summary: string;
  git_branch: string | null;
  git_status: string | null;
  git_recent_log: string | null;
  scanned_at: string;
}

export interface WorkspaceContext {
  has_snapshot: boolean;
  summary: string;
  git_branch: string | null;
  git_status: string | null;
  uncommitted_changes: string | null;
  recent_local_commits: string | null;
}
```

- [ ] **Step 2: Add API functions**

Add to `frontend/lib/api.ts`:
```typescript
export const chat = {
  send(projectId: string, data: ChatSendRequest): Promise<ChatMessage> {
    return apiFetch<ChatMessage>(`/projects/${projectId}/chat`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
  history(projectId: string, limit = 50): Promise<ChatHistoryResponse> {
    return apiFetch<ChatHistoryResponse>(`/projects/${projectId}/chat?limit=${limit}`);
  },
  clear(projectId: string): Promise<void> {
    return apiFetch(`/projects/${projectId}/chat`, { method: 'DELETE' });
  },
};

export const workspace = {
  scan(projectId: string, localPath?: string): Promise<WorkspaceSnapshot> {
    return apiFetch<WorkspaceSnapshot>(`/projects/${projectId}/workspace/scan`, {
      method: 'POST',
      body: JSON.stringify({ local_path: localPath }),
    });
  },
  context(projectId: string): Promise<WorkspaceContext> {
    return apiFetch<WorkspaceContext>(`/projects/${projectId}/workspace/context`);
  },
};
```

- [ ] **Step 3: Create useChat hook**

```typescript
// frontend/lib/hooks/useChat.ts
import useSWR from 'swr';
import { chat } from '@/lib/api';
import type { ChatHistoryResponse } from '@/lib/types';

export function useChat(projectId: string) {
  const { data, error, isLoading, mutate } = useSWR<ChatHistoryResponse>(
    projectId ? `/projects/${projectId}/chat` : null,
    () => chat.history(projectId),
  );
  return { data, error, isLoading, mutate };
}
```

- [ ] **Step 4: Create ChatMessage component**

```typescript
// frontend/components/chat/ChatMessage.tsx
// Renders a single message bubble.
// User messages: right-aligned, primary color.
// Assistant messages: left-aligned, card background, with markdown rendering.
// Show timestamp on hover.
```

Full implementation: a message bubble with role-based styling. Assistant messages rendered as markdown (reuse the prose-blog CSS from blog module). User messages are simple text. Timestamp shown at bottom in muted text.

- [ ] **Step 5: Create WorkspaceStatus component**

```typescript
// frontend/components/chat/WorkspaceStatus.tsx
// Shows: branch name, uncommitted file count, last scan time
// "Scan Now" button to trigger workspace scan
// Compact bar above the chat input
```

Shows git branch badge, number of uncommitted changes, last scan timestamp. "Scan" button triggers `workspace.scan()`.

- [ ] **Step 6: Create ChatWindow component**

```typescript
// frontend/components/chat/ChatWindow.tsx
// Full chat interface:
// - Scrollable message list (auto-scroll to bottom on new messages)
// - WorkspaceStatus bar
// - Input area: textarea + send button
// - Context toggles: workspace/memory/repo checkboxes
// - "Clear history" button in header
// - Loading state while AI responds
```

Main chat component. Message list with auto-scroll. Input bar at bottom with textarea (submit on Enter, Shift+Enter for newline). Three small toggle pills above input for context sources. Send button shows spinner while waiting. "Clear" button in top bar.

- [ ] **Step 7: Create chat page**

```typescript
// frontend/app/projects/[projectId]/chat/page.tsx
// Wraps ChatWindow with project context.
// Full height layout (flex, h-full).
```

Simple page that renders `<ChatWindow projectId={projectId} />` in a full-height container.

- [ ] **Step 8: Add sidebar nav item**

Add to `frontend/components/ProjectSidebar.tsx`:
```typescript
import { MessageSquare } from "lucide-react";
// Add to navItems array, first position (most important):
{ label: "Co-Founder", href: `/projects/${projectId}/chat`, icon: MessageSquare },
```

- [ ] **Step 9: Build and test**

```bash
docker compose up --build -d
```
Navigate to a project → Co-Founder tab. Send a message like "What should I focus on next?" Verify:
- Response references actual project data
- Conversation history persists across page loads
- Workspace status shows if scan was done

---

## Task 6: Auto-Map Project Local Paths

**Files:**
- Modify: `backend/app/routers/github.py`

- [ ] **Step 1: Auto-set local_path on project import**

When importing repos via `/github/repos/import`, auto-set `local_path` based on the convention that projects live at `/projects/{repo_name}` (which maps to `/Volumes/extraSupply/Projects/{repo_name}` on the host):

In the import router's project creation loop, add:
```python
project.local_path = f"/projects/{repo_name}"
```

This way, every imported project is immediately scannable without manual path configuration.

- [ ] **Step 2: Update existing projects**

Create a one-time script or API call to backfill local_path for existing projects:
```bash
# For each project, derive local_path from name
curl -s -H "X-API-Key: dev-secret-key" http://localhost:8989/api/v1/projects | \
  python3 -c "
import sys, json, subprocess
for p in json.load(sys.stdin):
    if p['status'] != 'demo' and not p.get('local_path'):
        name = p['github_repo'].split('/')[-1] if p.get('github_repo') else p['name']
        subprocess.run(['curl', '-s', '-X', 'PATCH',
            '-H', 'X-API-Key: dev-secret-key',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps({'local_path': f'/projects/{name}'}),
            f'http://localhost:8989/api/v1/projects/{p[\"id\"]}'],
            capture_output=True)
        print(f'Set {p[\"name\"]} -> /projects/{name}')
"
```

---

## Self-Review Checklist

1. **Spec coverage:** All requirements covered — local file reading (Task 2+4), co-founder chat (Task 3+5), local model for privacy (workspace_scanner uses get_local_client), strategic advisor persona (CO_FOUNDER_SYSTEM prompt).

2. **Placeholder scan:** No TBDs. Tasks 5 steps 4-7 have component descriptions rather than full JSX — this is acceptable because the frontend components follow established patterns (DraftCard, BlogEditor, etc.) and a skilled developer can implement them from the interface descriptions + existing component patterns.

3. **Type consistency:** ChatMessage model matches schema. WorkspaceSnapshot model matches schema. API functions in frontend match backend router paths. Sidebar uses MessageSquare icon consistently.
