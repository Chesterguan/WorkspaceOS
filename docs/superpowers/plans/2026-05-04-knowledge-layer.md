# Knowledge Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a user-scoped, cross-project knowledge graph populated by per-turn extraction from Co-Founder + Research roundtables, with manual promotion. Wires into paper pipeline, draft service, worklog, and chat for shared context across features.

**Architecture:** Two new tables (`knowledge_nodes` + `knowledge_edges`) — additive, no changes to existing memory/chat tables. Fire-and-forget extractor with two-stage LLM call (cheap classifier → structured extraction). Existing RAG infra (`memory_service._hybrid_search`) refactored into a shared helper consumed by both `search_memory` and new `search_knowledge`. `/knowledge` page with React Flow canvas.

**Tech Stack:** FastAPI · SQLAlchemy 2 (async) · Alembic · pgvector · Pydantic · pytest · Next.js 16 (App Router) · React Flow (`@xyflow/react`) · dagre · Tailwind · shadcn/ui · SWR.

**Spec:** `docs/superpowers/specs/2026-05-04-knowledge-layer-design.md`

---

## File Structure

### Backend — new files
| File | Responsibility |
|---|---|
| `backend/alembic/versions/0018_knowledge_layer.py` | Migration: tables + indexes |
| `backend/app/models/knowledge.py` | `KnowledgeNode` + `KnowledgeEdge` SQLAlchemy models |
| `backend/app/schemas/knowledge.py` | Pydantic request/response models |
| `backend/app/services/knowledge_extractor.py` | Two-stage extractor, dedup, edge inference |
| `backend/app/services/knowledge_service.py` | Query API: search, get-with-neighbors, list-recent |
| `backend/app/services/_hybrid_search.py` | Shared RRF + reranking helper extracted from memory_service |
| `backend/app/routers/knowledge.py` | REST routes: list/CRUD/graph/promote |
| `backend/tests/test_knowledge_extractor.py` | Extractor unit tests |
| `backend/tests/test_knowledge_service.py` | Query API tests |
| `backend/tests/test_knowledge_routes.py` | Endpoint integration tests |

### Backend — modified files
| File | Change |
|---|---|
| `backend/app/main.py:222` | Register knowledge router |
| `backend/app/models/__init__.py` | Export new models |
| `backend/app/models/project.py` | Add `knowledge_nodes` relationship |
| `backend/app/models/user.py` | Add `knowledge_nodes` relationship |
| `backend/app/services/memory_service.py:254-302` | Refactor to call `_hybrid_search` |
| `backend/app/services/chat_service.py:end of send_message` | Fire-and-forget extraction hook + add knowledge to `_build_context` |
| `backend/app/services/research_service.py` | Same pattern as chat_service |
| `backend/app/services/paper_service.py` (in `_build_paper_context`) | Inject knowledge block |
| `backend/app/services/draft_service.py` | Inject knowledge block when generating |
| `backend/app/services/worklog_service.py` | Pull knowledge for date-range narratives |

### Frontend — new files
| File | Responsibility |
|---|---|
| `frontend/app/knowledge/page.tsx` | Main `/knowledge` page |
| `frontend/components/knowledge/KnowledgeGraph.tsx` | React Flow canvas |
| `frontend/components/knowledge/KnowledgeFilters.tsx` | Sidebar filters |
| `frontend/components/knowledge/NodeDetailPanel.tsx` | Selected-node detail card |
| `frontend/components/knowledge/PromoteButton.tsx` | "🔖 Save as knowledge" button |
| `frontend/components/knowledge/PromoteModal.tsx` | Modal for manual node creation |
| `frontend/lib/knowledge.ts` | Types + SWR hooks |

### Frontend — modified files
| File | Change |
|---|---|
| `frontend/components/chat/ChatMessage.tsx` | Add `<PromoteButton />` |
| `frontend/components/Header.tsx` (or wherever nav lives) | Add `/knowledge` link |
| `frontend/components/DraftEditor.tsx` | Add selection-based promote (Phase 1d) |

---

## Phase 1a — Foundation (Tasks 1–11)

Backend-only. After this phase the extractor is running silently. No UI yet.

### Task 1: Create Alembic migration

**Files:**
- Create: `backend/alembic/versions/0018_knowledge_layer.py`

- [ ] **Step 1: Write the migration**

```python
"""Add knowledge_nodes + knowledge_edges — user-scoped cross-project graph.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-04

Rationale:
  Roundtable conversations produce decisions, claims, hypotheses, etc.
  Today they die in chat_messages. This adds a user-scoped graph layer
  populated by per-turn extraction. Memory tables stay untouched.

  See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector exists (safe no-op if already created)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_refs", JSONB, server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("search_vector", sa.Text, nullable=True),  # placeholder; rewritten below
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.Column("archived", sa.Boolean, server_default=sa.text("false"),
                  nullable=False),
        sa.Column("created_by", sa.String(40), nullable=False,
                  server_default="auto_extractor"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )

    # Replace the placeholder embedding/search_vector columns with proper types.
    op.execute("ALTER TABLE knowledge_nodes DROP COLUMN embedding")
    op.execute("ALTER TABLE knowledge_nodes ADD COLUMN embedding vector(768)")
    op.execute("ALTER TABLE knowledge_nodes DROP COLUMN search_vector")
    op.execute("ALTER TABLE knowledge_nodes ADD COLUMN search_vector tsvector")

    # tsvector trigger (mirrors memory_entries pattern)
    op.execute("""
        CREATE FUNCTION knowledge_nodes_tsv_trigger() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector :=
            setweight(to_tsvector('english', coalesce(NEW.title,'')), 'A') ||
            setweight(to_tsvector('english', coalesce(NEW.content,'')), 'B');
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER knowledge_nodes_tsv_update
        BEFORE INSERT OR UPDATE OF title, content
        ON knowledge_nodes
        FOR EACH ROW EXECUTE FUNCTION knowledge_nodes_tsv_trigger();
    """)

    op.create_index("ix_knowledge_nodes_user_id", "knowledge_nodes", ["user_id"])
    op.create_index("ix_knowledge_nodes_project_id", "knowledge_nodes", ["project_id"])
    op.create_index("ix_knowledge_nodes_node_type", "knowledge_nodes", ["node_type"])
    op.create_index(
        "ix_knowledge_nodes_user_archived_created",
        "knowledge_nodes",
        ["user_id", "archived", sa.text("created_at DESC")],
    )
    op.execute(
        "CREATE INDEX ix_knowledge_nodes_search_vector "
        "ON knowledge_nodes USING gin (search_vector)"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_nodes_embedding "
        "ON knowledge_nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "knowledge_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("target_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("edge_type", sa.String(40), nullable=False),
        sa.Column("weight", sa.Float, server_default=sa.text("1.0"), nullable=False),
        sa.Column("source_refs", JSONB, server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("created_by", sa.String(40), nullable=False,
                  server_default="auto_extractor"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_node_id", "target_node_id", "edge_type",
                            name="uq_knowledge_edges_triple"),
    )
    op.create_index("ix_knowledge_edges_user_id", "knowledge_edges", ["user_id"])


def downgrade() -> None:
    op.drop_table("knowledge_edges")
    op.execute("DROP TRIGGER IF EXISTS knowledge_nodes_tsv_update ON knowledge_nodes")
    op.execute("DROP FUNCTION IF EXISTS knowledge_nodes_tsv_trigger()")
    op.drop_table("knowledge_nodes")
```

- [ ] **Step 2: Apply migration**

```bash
docker compose exec backend alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 0017 -> 0018, Add knowledge_nodes + knowledge_edges`

- [ ] **Step 3: Verify schema**

```bash
docker compose exec db psql -U postgres -d pr_secretary -c "\d knowledge_nodes"
docker compose exec db psql -U postgres -d pr_secretary -c "\d knowledge_edges"
```

Expected: both tables exist with all columns; embedding is `vector(768)`; tsvector trigger present.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0018_knowledge_layer.py
git commit -m "feat: knowledge layer migration (nodes + edges)"
```

---

### Task 2: SQLAlchemy models

**Files:**
- Create: `backend/app/models/knowledge.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/project.py`
- Modify: `backend/app/models/user.py`

- [ ] **Step 1: Create the models**

```python
# backend/app/models/knowledge.py
import uuid
from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.memory import TSVector


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    node_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768), nullable=True)
    search_vector = mapped_column(TSVector(), nullable=True)
    metadata_: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(40), nullable=False, default="auto_extractor")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type: Mapped[str] = mapped_column(String(40), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(40), nullable=False, default="auto_extractor")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "edge_type",
                         name="uq_knowledge_edges_triple"),
    )


# Valid type sets — single source of truth for validation
NODE_TYPES = frozenset({
    "claim", "decision", "question", "hypothesis", "rejection", "blocker", "insight",
})
EDGE_TYPES = frozenset({
    "supports", "contradicts", "refines", "follows_up",
    "depends_on", "derives_from", "rejects", "related_to",
})
```

- [ ] **Step 2: Add to models/__init__.py**

Open `backend/app/models/__init__.py` and add:
```python
from app.models.knowledge import KnowledgeNode, KnowledgeEdge, NODE_TYPES, EDGE_TYPES  # noqa: F401
```
(Append to the existing imports — don't replace the file.)

- [ ] **Step 3: Verify imports work**

```bash
docker compose exec backend python -c "from app.models.knowledge import KnowledgeNode, KnowledgeEdge, NODE_TYPES; print(len(NODE_TYPES))"
```
Expected: `7`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/knowledge.py backend/app/models/__init__.py
git commit -m "feat: KnowledgeNode + KnowledgeEdge ORM models"
```

---

### Task 3: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/knowledge.py`

- [ ] **Step 1: Write schemas**

```python
# backend/app/schemas/knowledge.py
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.knowledge import EDGE_TYPES, NODE_TYPES


class SourceRef(BaseModel):
    kind: str = Field(..., description="chat_message | memory_entry | manual | draft | file_ingest")
    id: Optional[str] = None
    excerpt: Optional[str] = None
    note: Optional[str] = None


class KnowledgeNodeOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    node_type: str
    title: str
    content: str
    source_refs: List[SourceRef]
    metadata_: dict = Field(alias="metadata", default_factory=dict)
    archived: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True


class KnowledgeEdgeOut(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    edge_type: str
    weight: float
    created_at: datetime

    class Config:
        from_attributes = True


class NodeCreateRequest(BaseModel):
    project_id: Optional[uuid.UUID] = None
    node_type: str
    title: str = Field(..., max_length=160)
    content: str
    source_refs: List[SourceRef] = Field(default_factory=list)
    metadata_: dict = Field(alias="metadata", default_factory=dict)

    @field_validator("node_type")
    @classmethod
    def validate_node_type(cls, v: str) -> str:
        if v not in NODE_TYPES:
            raise ValueError(f"node_type must be one of {sorted(NODE_TYPES)}")
        return v


class NodeUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=160)
    content: Optional[str] = None
    node_type: Optional[str] = None
    archived: Optional[bool] = None
    project_id: Optional[uuid.UUID] = None

    @field_validator("node_type")
    @classmethod
    def validate_node_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in NODE_TYPES:
            raise ValueError(f"node_type must be one of {sorted(NODE_TYPES)}")
        return v


class PromoteRequest(BaseModel):
    project_id: Optional[uuid.UUID] = None
    source: SourceRef
    suggested_type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None  # if absent, extractor proposes one


class GraphResponse(BaseModel):
    nodes: List[KnowledgeNodeOut]
    edges: List[KnowledgeEdgeOut]


class SearchResultItem(BaseModel):
    node: KnowledgeNodeOut
    score: float
```

- [ ] **Step 2: Verify imports**

```bash
docker compose exec backend python -c "from app.schemas.knowledge import KnowledgeNodeOut, NodeCreateRequest; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/knowledge.py
git commit -m "feat: knowledge layer Pydantic schemas"
```

---

### Task 4: Stage 1 classifier — test first

**Files:**
- Create: `backend/tests/test_knowledge_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_knowledge_extractor.py
import pytest
from unittest.mock import AsyncMock, patch

from app.services.knowledge_extractor import _classify_extractable


class FakeAI:
    def __init__(self, response: str):
        self._r = response

    async def complete(self, system: str, user: str) -> str:
        return self._r


@pytest.mark.asyncio
async def test_classify_extractable_yes():
    ai = FakeAI("YES")
    result = await _classify_extractable(ai, user="we should ditch Pinecone", ai_response="agreed, use pgvector")
    assert result is True


@pytest.mark.asyncio
async def test_classify_extractable_no():
    ai = FakeAI("NO")
    result = await _classify_extractable(ai, user="hi", ai_response="hello, what's up?")
    assert result is False


@pytest.mark.asyncio
async def test_classify_extractable_normalizes_whitespace_and_case():
    ai = FakeAI("  yes.  ")
    result = await _classify_extractable(ai, user="x", ai_response="y")
    assert result is True


@pytest.mark.asyncio
async def test_classify_extractable_falls_back_to_no_on_garbage():
    ai = FakeAI("I don't know")
    result = await _classify_extractable(ai, user="x", ai_response="y")
    assert result is False
```

- [ ] **Step 2: Run — should fail (module not yet created)**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py::test_classify_extractable_yes -v
```
Expected: `ImportError: cannot import name '_classify_extractable' from 'app.services.knowledge_extractor'`

- [ ] **Step 3: Implement minimal classifier**

```python
# backend/app/services/knowledge_extractor.py
"""Knowledge extractor — pulls structured nodes from roundtable turns.

See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


_CLASSIFIER_SYSTEM = (
    "You are a precision classifier. Reply with exactly one word: YES or NO. "
    "Nothing else."
)
_CLASSIFIER_TEMPLATE = (
    "Does this conversation turn contain extractable knowledge?\n"
    "Extractable = states a decision, claim, hypothesis, question to revisit, "
    "rejection, blocker, or insight.\n"
    "NOT extractable = greeting, acknowledgment, restating provided context, "
    "pure question with no answer.\n\n"
    "USER: {user}\n\nAI: {ai}\n\n"
    "Reply YES or NO."
)


async def _classify_extractable(ai: Any, user: str, ai_response: str) -> bool:
    """Stage 1: cheap YES/NO check. Anything that doesn't normalize to YES → False."""
    try:
        raw = await ai.complete(
            _CLASSIFIER_SYSTEM,
            _CLASSIFIER_TEMPLATE.format(user=user[:1500], ai=ai_response[:3000]),
        )
    except Exception:
        logger.exception("knowledge classifier failed")
        return False
    token = (raw or "").strip().rstrip(".").upper()
    return token == "YES"
```

- [ ] **Step 4: Run all classifier tests**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py -v -k classify
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge_extractor.py backend/tests/test_knowledge_extractor.py
git commit -m "feat(knowledge): stage-1 extractable classifier + tests"
```

---

### Task 5: Stage 2 extraction — test first

**Files:**
- Modify: `backend/tests/test_knowledge_extractor.py`
- Modify: `backend/app/services/knowledge_extractor.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_knowledge_extractor.py`:

```python
import json
from app.services.knowledge_extractor import _extract_structured, ExtractedNode


@pytest.mark.asyncio
async def test_extract_structured_parses_json():
    payload = {
        "nodes": [
            {"node_type": "decision", "title": "Use pgvector",
             "content": "Use pgvector instead of Pinecone for vector search.",
             "confidence": 0.9, "rationale": "user said so"},
            {"node_type": "rejection", "title": "Pinecone",
             "content": "Pinecone rejected — managed-only.",
             "confidence": 0.85, "rationale": "..."},
        ],
        "edges_within_turn": [{"from_idx": 1, "to_idx": 0, "edge_type": "rejects"}],
    }
    ai = FakeAI(json.dumps(payload))
    result = await _extract_structured(ai, user="...", ai_response="...",
                                       conversation_kind="cofounder", recent_turns=[])
    assert len(result.nodes) == 2
    assert result.nodes[0].node_type == "decision"
    assert result.edges_within_turn[0]["edge_type"] == "rejects"


@pytest.mark.asyncio
async def test_extract_structured_handles_garbage():
    ai = FakeAI("not even close to json")
    result = await _extract_structured(ai, user="x", ai_response="y",
                                       conversation_kind="cofounder", recent_turns=[])
    assert result.nodes == []
    assert result.edges_within_turn == []


@pytest.mark.asyncio
async def test_extract_structured_ignores_invalid_node_types():
    payload = {
        "nodes": [
            {"node_type": "decision", "title": "ok", "content": "valid"},
            {"node_type": "wishful_thinking", "title": "bad", "content": "invalid type"},
        ],
        "edges_within_turn": [],
    }
    ai = FakeAI(json.dumps(payload))
    result = await _extract_structured(ai, user="x", ai_response="y",
                                       conversation_kind="cofounder", recent_turns=[])
    assert len(result.nodes) == 1
    assert result.nodes[0].node_type == "decision"
```

- [ ] **Step 2: Run — should fail**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py::test_extract_structured_parses_json -v
```
Expected: `ImportError: cannot import name '_extract_structured'`.

- [ ] **Step 3: Implement extractor**

Append to `backend/app/services/knowledge_extractor.py`:

```python
import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any

from app.models.knowledge import NODE_TYPES, EDGE_TYPES


@dataclass
class ExtractedNode:
    node_type: str
    title: str
    content: str
    confidence: float = 0.7


@dataclass
class ExtractionResult:
    nodes: List[ExtractedNode] = field(default_factory=list)
    edges_within_turn: List[Dict[str, Any]] = field(default_factory=list)


_EXTRACTION_SYSTEM = (
    "You extract structured knowledge from conversation turns. "
    "Output ONLY valid JSON, no prose, no fences. "
    "Schema:\n"
    '{"nodes":[{"node_type":"<one of: claim|decision|question|hypothesis|rejection|blocker|insight>",'
    '"title":"<=120 chars","content":"1-3 sentences","confidence":0..1,'
    '"rationale":"why this type"}],'
    '"edges_within_turn":[{"from_idx":int,"to_idx":int,'
    '"edge_type":"<one of: supports|contradicts|refines|follows_up|depends_on|derives_from|rejects|related_to>"}]}'
    "\nIf nothing meaningful, return {\"nodes\":[],\"edges_within_turn\":[]}."
)


def _build_extraction_user(user: str, ai_response: str, kind: str,
                           recent_turns: List[Dict[str, str]]) -> str:
    history = ""
    if recent_turns:
        lines = [f"{t['role'].upper()}: {t['content'][:400]}" for t in recent_turns[-5:]]
        history = "## Recent context\n" + "\n".join(lines) + "\n\n"
    bias = (
        "This is a Co-Founder roundtable; expect more decisions/rejections/insights."
        if kind == "cofounder"
        else "This is an academic Research roundtable; expect more claims/hypotheses/questions."
    )
    return (
        f"{history}{bias}\n\n"
        f"## Current turn\nUSER: {user[:2000]}\n\nAI: {ai_response[:4000]}\n\n"
        "Extract any extractable nodes per the schema."
    )


def _strip_json_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s


async def _extract_structured(
    ai: Any, user: str, ai_response: str, conversation_kind: str,
    recent_turns: List[Dict[str, str]],
) -> ExtractionResult:
    """Stage 2. JSON parse failure → empty result, never raises."""
    try:
        raw = await ai.complete(
            _EXTRACTION_SYSTEM,
            _build_extraction_user(user, ai_response, conversation_kind, recent_turns),
        )
    except Exception:
        logger.exception("knowledge structured extraction failed")
        return ExtractionResult()

    try:
        data = json.loads(_strip_json_fences(raw))
    except (ValueError, TypeError):
        logger.warning("knowledge extractor: non-JSON output, dropping. raw=%r", raw[:300])
        return ExtractionResult()

    nodes: List[ExtractedNode] = []
    for n in data.get("nodes", []):
        if not isinstance(n, dict):
            continue
        nt = n.get("node_type")
        if nt not in NODE_TYPES:
            continue
        title = (n.get("title") or "")[:160].strip()
        content = (n.get("content") or "").strip()
        if not title or not content:
            continue
        nodes.append(ExtractedNode(
            node_type=nt, title=title, content=content,
            confidence=float(n.get("confidence", 0.7)),
        ))

    edges: List[Dict[str, Any]] = []
    for e in data.get("edges_within_turn", []):
        if not isinstance(e, dict):
            continue
        et = e.get("edge_type")
        if et not in EDGE_TYPES:
            continue
        try:
            from_idx = int(e["from_idx"])
            to_idx = int(e["to_idx"])
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= from_idx < len(nodes) and 0 <= to_idx < len(nodes) and from_idx != to_idx:
            edges.append({"from_idx": from_idx, "to_idx": to_idx, "edge_type": et})

    return ExtractionResult(nodes=nodes, edges_within_turn=edges)
```

- [ ] **Step 4: Run extractor tests**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py -v -k extract_structured
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge_extractor.py backend/tests/test_knowledge_extractor.py
git commit -m "feat(knowledge): stage-2 structured extraction + JSON parse hardening"
```

---

### Task 6: Dedup logic — test first

**Files:**
- Modify: `backend/tests/test_knowledge_extractor.py`
- Modify: `backend/app/services/knowledge_extractor.py`

- [ ] **Step 1: Add failing tests**

Append to `backend/tests/test_knowledge_extractor.py`:

```python
from app.services.knowledge_extractor import _decide_dedup_action, DedupAction


def test_dedup_above_high_threshold_merges():
    action = _decide_dedup_action(best_score=0.95, same_type=True)
    assert action.kind == "merge"


def test_dedup_mid_threshold_creates_with_refines_edge_when_same_type():
    action = _decide_dedup_action(best_score=0.85, same_type=True)
    assert action.kind == "create_with_edge"
    assert action.edge_type == "refines"


def test_dedup_mid_threshold_creates_with_related_when_diff_type():
    action = _decide_dedup_action(best_score=0.85, same_type=False)
    assert action.kind == "create_with_edge"
    assert action.edge_type == "related_to"


def test_dedup_below_low_threshold_creates_standalone():
    action = _decide_dedup_action(best_score=0.5, same_type=False)
    assert action.kind == "create"
    assert action.edge_type is None


def test_dedup_no_match_creates_standalone():
    action = _decide_dedup_action(best_score=None, same_type=False)
    assert action.kind == "create"
```

- [ ] **Step 2: Run — should fail**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py -v -k dedup
```
Expected: `ImportError`.

- [ ] **Step 3: Implement dedup decision**

Append to `backend/app/services/knowledge_extractor.py`:

```python
from typing import Optional

# Stored as constants here; can be moved to settings later if tuning is needed
DEDUP_HIGH = 0.92  # at/above → merge
DEDUP_LOW = 0.80   # at/above → create with linking edge


@dataclass
class DedupAction:
    kind: str  # "merge" | "create_with_edge" | "create"
    edge_type: Optional[str] = None


def _decide_dedup_action(best_score: Optional[float], same_type: bool) -> DedupAction:
    if best_score is None:
        return DedupAction(kind="create")
    if best_score >= DEDUP_HIGH:
        return DedupAction(kind="merge")
    if best_score >= DEDUP_LOW:
        return DedupAction(
            kind="create_with_edge",
            edge_type="refines" if same_type else "related_to",
        )
    return DedupAction(kind="create")
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py -v -k dedup
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge_extractor.py backend/tests/test_knowledge_extractor.py
git commit -m "feat(knowledge): dedup decision logic + thresholds"
```

---

### Task 7: Persistence — write nodes + edges with embedding & dedup

**Files:**
- Modify: `backend/app/services/knowledge_extractor.py`
- Modify: `backend/tests/test_knowledge_extractor.py`

- [ ] **Step 1: Add failing integration test**

Append to `backend/tests/test_knowledge_extractor.py`:

```python
import uuid
from app.services.knowledge_extractor import extract_from_chat_turn
from app.models.knowledge import KnowledgeNode, KnowledgeEdge
from app.models.chat import ChatMessage
from sqlalchemy import select


@pytest.mark.asyncio
async def test_extract_persists_nodes_and_within_turn_edges(db_session, sample_user, sample_project):
    """End-to-end: chat turn produces nodes + within-turn edges in DB."""
    user_msg = ChatMessage(
        project_id=sample_project.id, role="user",
        content="should we use pgvector or pinecone?",
    )
    ai_msg = ChatMessage(
        project_id=sample_project.id, role="assistant",
        content="Use pgvector — Pinecone is managed-only and we want SQL access.",
    )
    db_session.add_all([user_msg, ai_msg])
    await db_session.commit()

    payload = {
        "nodes": [
            {"node_type": "decision", "title": "Use pgvector",
             "content": "Use pgvector for vector search.",
             "confidence": 0.9, "rationale": "..."},
            {"node_type": "rejection", "title": "Pinecone rejected",
             "content": "Pinecone rejected — managed-only, no SQL.",
             "confidence": 0.85, "rationale": "..."},
        ],
        "edges_within_turn": [{"from_idx": 1, "to_idx": 0, "edge_type": "rejects"}],
    }

    fake_ai = FakeAI("YES")  # stage 1
    fake_extract_ai = FakeAI(json.dumps(payload))  # stage 2

    with patch("app.services.knowledge_extractor.get_cloud_client", return_value=fake_ai), \
         patch("app.services.knowledge_extractor._extract_structured",
               new=AsyncMock(return_value=__import__("app.services.knowledge_extractor",
                                                     fromlist=["ExtractionResult"])
                                       .ExtractionResult(
                                           nodes=[__import__("app.services.knowledge_extractor",
                                                  fromlist=["ExtractedNode"]).ExtractedNode(
                                               node_type="decision", title="Use pgvector",
                                               content="Use pgvector for vector search.",
                                               confidence=0.9),
                                           __import__("app.services.knowledge_extractor",
                                                  fromlist=["ExtractedNode"]).ExtractedNode(
                                               node_type="rejection", title="Pinecone rejected",
                                               content="Pinecone rejected — managed-only, no SQL.",
                                               confidence=0.85)],
                                           edges_within_turn=[
                                               {"from_idx": 1, "to_idx": 0, "edge_type": "rejects"}],
                                       ))), \
         patch("app.services.knowledge_extractor._embed", new=AsyncMock(return_value=[0.0]*768)):
        await extract_from_chat_turn(
            user_id=sample_user.id, project_id=sample_project.id,
            user_message=user_msg, ai_message=ai_msg,
            conversation_kind="cofounder", db=db_session,
        )

    nodes = (await db_session.execute(
        select(KnowledgeNode).where(KnowledgeNode.user_id == sample_user.id)
    )).scalars().all()
    assert len(nodes) == 2
    assert {n.node_type for n in nodes} == {"decision", "rejection"}

    edges = (await db_session.execute(
        select(KnowledgeEdge).where(KnowledgeEdge.user_id == sample_user.id)
    )).scalars().all()
    assert len(edges) == 1
    assert edges[0].edge_type == "rejects"
```

(Assumes `db_session`, `sample_user`, `sample_project` fixtures exist in `conftest.py`. If they don't, see Step 2.)

- [ ] **Step 2: Verify or add fixtures**

Check `backend/tests/conftest.py`:

```bash
grep -E "sample_user|sample_project|db_session" backend/tests/conftest.py
```

If `sample_user` / `sample_project` fixtures aren't there, add them:

```python
# Append to backend/tests/conftest.py
import pytest_asyncio
from app.models.user import User
from app.models.project import Project


@pytest_asyncio.fixture
async def sample_user(db_session):
    u = User(email="test+knowledge@example.com", hashed_password="x")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def sample_project(db_session, sample_user):
    p = Project(name="TestProj", slug="testproj", user_id=sample_user.id)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p
```

- [ ] **Step 3: Run — should fail (extract_from_chat_turn not implemented)**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py::test_extract_persists_nodes_and_within_turn_edges -v
```
Expected: `ImportError` or `AttributeError`.

- [ ] **Step 4: Implement persistence orchestrator**

Append to `backend/app/services/knowledge_extractor.py`:

```python
import uuid
from typing import List, Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.models.chat import ChatMessage
from app.services.ai_client import get_cloud_client


async def _embed(text_to_embed: str) -> List[float]:
    """Wrap ai.embed for easier mocking in tests."""
    ai = get_cloud_client()
    return await ai.embed(text_to_embed)


async def _find_nearest(
    db: AsyncSession, user_id: uuid.UUID, embedding: List[float], node_type: str, k: int = 3,
) -> List[Tuple[KnowledgeNode, float]]:
    """Return up to k existing nodes for this user ranked by cosine similarity. Same node_type preferred."""
    if not embedding:
        return []
    # Cosine distance via pgvector <-> ; similarity = 1 - distance.
    sql = text("""
        SELECT id, 1 - (embedding <=> CAST(:emb AS vector)) AS sim
        FROM knowledge_nodes
        WHERE user_id = :uid AND embedding IS NOT NULL AND archived = false
        ORDER BY embedding <=> CAST(:emb AS vector)
        LIMIT :k
    """)
    rows = (await db.execute(sql, {"emb": str(embedding), "uid": str(user_id), "k": k})).all()
    if not rows:
        return []
    ids = [r.id for r in rows]
    nodes = {n.id: n for n in (
        await db.execute(select(KnowledgeNode).where(KnowledgeNode.id.in_(ids)))
    ).scalars().all()}
    out: List[Tuple[KnowledgeNode, float]] = []
    for r in rows:
        node = nodes.get(r.id)
        if node is not None:
            out.append((node, float(r.sim)))
    # Re-rank: prefer same-type matches with a small bonus
    out.sort(key=lambda x: (x[1] + (0.02 if x[0].node_type == node_type else 0.0)), reverse=True)
    return out


def _make_source_ref(ai_message: ChatMessage) -> dict:
    return {
        "kind": "chat_message",
        "id": str(ai_message.id),
        "excerpt": (ai_message.content or "")[:200],
    }


async def extract_from_chat_turn(
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    user_message: ChatMessage,
    ai_message: ChatMessage,
    conversation_kind: str,
    db: AsyncSession,
) -> None:
    """End-to-end per-turn extraction. Best-effort; logs and returns on any failure."""
    ai = get_cloud_client()

    if not await _classify_extractable(ai, user_message.content or "", ai_message.content or ""):
        return

    result = await _extract_structured(
        ai, user_message.content or "", ai_message.content or "",
        conversation_kind, recent_turns=[],
    )
    if not result.nodes:
        return

    persisted: List[KnowledgeNode] = []  # index-aligned with result.nodes (None for merged)
    for extracted in result.nodes:
        try:
            embed_text = f"{extracted.title}\n\n{extracted.content}"
            embedding = await _embed(embed_text)
        except Exception:
            logger.exception("embed failed; skipping node")
            persisted.append(None)  # type: ignore[arg-type]
            continue

        neighbors = await _find_nearest(db, user_id, embedding, extracted.node_type)
        best = neighbors[0] if neighbors else None
        action = _decide_dedup_action(
            best_score=best[1] if best else None,
            same_type=(best is not None and best[0].node_type == extracted.node_type),
        )

        if action.kind == "merge" and best is not None:
            existing = best[0]
            existing.source_refs = (existing.source_refs or []) + [_make_source_ref(ai_message)]
            meta = dict(existing.metadata_ or {})
            meta["reinforcement_count"] = int(meta.get("reinforcement_count", 1)) + 1
            existing.metadata_ = meta
            persisted.append(existing)
            continue

        node = KnowledgeNode(
            user_id=user_id, project_id=project_id,
            node_type=extracted.node_type, title=extracted.title,
            content=extracted.content, embedding=embedding,
            source_refs=[_make_source_ref(ai_message)],
            metadata_={
                "confidence": extracted.confidence,
                "extraction_model": "gemini_flash",
                "conversation_kind": conversation_kind,
            },
            created_by="auto_extractor",
        )
        db.add(node)
        await db.flush()  # populate node.id

        if action.kind == "create_with_edge" and best is not None and action.edge_type:
            db.add(KnowledgeEdge(
                user_id=user_id, source_node_id=node.id,
                target_node_id=best[0].id, edge_type=action.edge_type, weight=0.5,
                source_refs=[_make_source_ref(ai_message)],
                created_by="auto_extractor",
            ))
        persisted.append(node)

    # Within-turn edges from extractor JSON
    for edge in result.edges_within_turn:
        src = persisted[edge["from_idx"]]
        tgt = persisted[edge["to_idx"]]
        if src is None or tgt is None or src.id == tgt.id:
            continue
        db.add(KnowledgeEdge(
            user_id=user_id, source_node_id=src.id, target_node_id=tgt.id,
            edge_type=edge["edge_type"], weight=1.0,
            source_refs=[_make_source_ref(ai_message)], created_by="auto_extractor",
        ))

    try:
        await db.commit()
    except Exception:
        logger.exception("knowledge extractor commit failed; rolling back")
        await db.rollback()
```

- [ ] **Step 5: Run integration test**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py::test_extract_persists_nodes_and_within_turn_edges -v
```
Expected: PASS.

- [ ] **Step 6: Run all extractor tests**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py -v
```
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/knowledge_extractor.py backend/tests/test_knowledge_extractor.py backend/tests/conftest.py
git commit -m "feat(knowledge): persistence + dedup + within-turn edges"
```

---

### Task 8: Hook extractor into chat_service

**Files:**
- Modify: `backend/app/services/chat_service.py`

- [ ] **Step 1: Locate the persistence point**

```bash
grep -n "ai_message\|assistant.*ChatMessage\|db.commit" backend/app/services/chat_service.py | head -20
```

Find the spot just after the AI message is committed and before the function returns.

- [ ] **Step 2: Add fire-and-forget hook**

Add at the top of `chat_service.py`:

```python
import asyncio
from app.database import async_session_maker  # if exists; otherwise see Step 3
from app.services import knowledge_extractor
```

Then insert just before the function returns (after the AI message has been committed). Pattern:

```python
# Fire-and-forget knowledge extraction (per-turn). Uses its own DB session.
async def _bg_extract():
    async with async_session_maker() as bg_db:
        try:
            await knowledge_extractor.extract_from_chat_turn(
                user_id=user_id_uuid,
                project_id=project.id,
                user_message=user_msg,  # the persisted ChatMessage objects
                ai_message=ai_msg,
                conversation_kind="cofounder",
                db=bg_db,
            )
        except Exception:
            logger.exception("background knowledge extraction failed (non-fatal)")

asyncio.create_task(_bg_extract())
```

Where `user_id_uuid` is the JWT user (or the project owner's user_id when API key is used).

- [ ] **Step 3: Verify the session factory exists**

```bash
grep -n "async_session_maker\|sessionmaker" backend/app/database.py
```

If it does not exist, add to `backend/app/database.py`:

```python
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
```

(adjust to match the existing engine variable name).

- [ ] **Step 4: Run a smoke test against a live message**

Bring the stack up if it isn't already, then send a real roundtable message via the existing `/api/v1/projects/{id}/chat/send` endpoint and inspect the DB:

```bash
docker compose exec db psql -U postgres -d pr_secretary -c \
  "SELECT node_type, title, created_at FROM knowledge_nodes ORDER BY created_at DESC LIMIT 5;"
```

Expected: rows appear within ~5 seconds of the AI response.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat_service.py backend/app/database.py
git commit -m "feat(knowledge): fire-and-forget extraction hook in chat_service"
```

---

### Task 9: Hook extractor into research_service

**Files:**
- Modify: `backend/app/services/research_service.py`

- [ ] **Step 1: Locate equivalent persistence point**

```bash
grep -n "ChatMessage\|persist\|commit\|return" backend/app/services/research_service.py | head -30
```

- [ ] **Step 2: Add the same hook with `conversation_kind="research"`**

Mirror Task 8 — wrap the extraction call in `_bg_extract` and dispatch with `asyncio.create_task` after the AI message is persisted. Use the SAME helper module `knowledge_extractor.extract_from_chat_turn`.

- [ ] **Step 3: Smoke-test with a research roundtable message**

Trigger a research roundtable interaction via the existing endpoint, then:

```bash
docker compose exec db psql -U postgres -d pr_secretary -c \
  "SELECT node_type, title, metadata->>'conversation_kind' AS kind FROM knowledge_nodes ORDER BY created_at DESC LIMIT 5;"
```

Expected: at least one row with `kind = 'research'`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/research_service.py
git commit -m "feat(knowledge): extraction hook in research_service"
```

---

### Task 10: Manual extractor-bypass entrypoint (`promote_manual`)

**Files:**
- Modify: `backend/app/services/knowledge_extractor.py`
- Modify: `backend/tests/test_knowledge_extractor.py`

- [ ] **Step 1: Add failing test**

```python
@pytest.mark.asyncio
async def test_promote_manual_creates_node_with_user_supplied_fields(db_session, sample_user, sample_project):
    from app.services.knowledge_extractor import promote_manual
    from app.schemas.knowledge import SourceRef

    with patch("app.services.knowledge_extractor._embed", new=AsyncMock(return_value=[0.0]*768)):
        node = await promote_manual(
            user_id=sample_user.id, project_id=sample_project.id,
            source=SourceRef(kind="manual", note="from chat msg X"),
            suggested_type="decision",
            title="Manual decision",
            content="We decided to do thing.",
            db=db_session,
        )
    assert node.node_type == "decision"
    assert node.title == "Manual decision"
    assert node.created_by == "manual_promote"
```

- [ ] **Step 2: Run — fail**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py::test_promote_manual_creates_node_with_user_supplied_fields -v
```

- [ ] **Step 3: Implement**

Append to `knowledge_extractor.py`:

```python
from app.schemas.knowledge import SourceRef


async def promote_manual(
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    source: SourceRef,
    suggested_type: str | None,
    title: str | None,
    content: str | None,
    db: AsyncSession,
) -> KnowledgeNode:
    """Manual promotion. If title/content missing, the caller must supply them — no inference here in v1."""
    if not title or not content:
        raise ValueError("title and content required for manual promotion")
    nt = suggested_type or "insight"
    if nt not in NODE_TYPES:
        raise ValueError(f"node_type must be one of {sorted(NODE_TYPES)}")

    embedding: List[float]
    try:
        embedding = await _embed(f"{title}\n\n{content}")
    except Exception:
        logger.exception("embed failed during manual promote; storing without")
        embedding = []  # store None below

    node = KnowledgeNode(
        user_id=user_id, project_id=project_id, node_type=nt,
        title=title.strip()[:160], content=content.strip(),
        embedding=embedding or None,
        source_refs=[source.model_dump(exclude_none=True)],
        metadata_={"extraction_model": "manual"},
        created_by="manual_promote",
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node
```

- [ ] **Step 4: Run**

```bash
docker compose exec backend pytest tests/test_knowledge_extractor.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge_extractor.py backend/tests/test_knowledge_extractor.py
git commit -m "feat(knowledge): promote_manual entrypoint"
```

---

### Task 11: Phase 1a smoke validation

- [ ] **Step 1: Run 3 roundtable sessions manually**

In the live UI: have 3 short conversations (~5 turns each) — one cofounder, one research, one mixed.

- [ ] **Step 2: Inspect node distribution**

```bash
docker compose exec db psql -U postgres -d pr_secretary -c \
  "SELECT node_type, count(*) FROM knowledge_nodes GROUP BY node_type ORDER BY count(*) DESC;"
```

Sanity targets: ≥3 distinct types, no single type >70% of total.

- [ ] **Step 3: Inspect dedup behavior**

```bash
docker compose exec db psql -U postgres -d pr_secretary -c \
  "SELECT title, metadata->>'reinforcement_count' AS rein FROM knowledge_nodes WHERE (metadata->>'reinforcement_count')::int > 1;"
```

If you see same titles repeated as separate rows that should have merged, lower `DEDUP_HIGH` to `0.88`. If unrelated topics merged, raise to `0.95`. Update `DEDUP_HIGH` in `knowledge_extractor.py`.

- [ ] **Step 4: Inspect within-turn edges**

```bash
docker compose exec db psql -U postgres -d pr_secretary -c \
  "SELECT edge_type, count(*) FROM knowledge_edges GROUP BY edge_type;"
```

- [ ] **Step 5: Commit any threshold tuning**

```bash
git add backend/app/services/knowledge_extractor.py
git commit -m "chore(knowledge): tune DEDUP thresholds from real data" --allow-empty
```

---

## Phase 1b — Consumer wiring (Tasks 12–17)

### Task 12: Extract `_hybrid_search` helper from `memory_service`

**Files:**
- Create: `backend/app/services/_hybrid_search.py`
- Modify: `backend/app/services/memory_service.py`

- [ ] **Step 1: Read existing impl**

```bash
sed -n '139,260p' backend/app/services/memory_service.py
```

- [ ] **Step 2: Create the generic helper**

```python
# backend/app/services/_hybrid_search.py
"""Generic hybrid search: pgvector cosine + BM25 + RRF fusion + FlashRank reranking.

Table-agnostic — used by both memory_service and knowledge_service.
"""
import logging
import uuid
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(rankings: Sequence[List[uuid.UUID]], k: int = 60) -> List[uuid.UUID]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return [i for i, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


async def vector_search(
    db: AsyncSession, table: str, embedding: List[float], limit: int,
    where_sql: str, where_params: dict,
) -> List[uuid.UUID]:
    sql = text(f"""
        SELECT id FROM {table}
        WHERE embedding IS NOT NULL {('AND ' + where_sql) if where_sql else ''}
        ORDER BY embedding <=> CAST(:emb AS vector)
        LIMIT :lim
    """)
    rows = (await db.execute(sql, {"emb": str(embedding), "lim": limit, **where_params})).all()
    return [r.id for r in rows]


async def bm25_search(
    db: AsyncSession, table: str, query: str, limit: int,
    where_sql: str, where_params: dict,
) -> List[uuid.UUID]:
    sql = text(f"""
        SELECT id FROM {table}
        WHERE search_vector @@ plainto_tsquery('english', :q)
            {('AND ' + where_sql) if where_sql else ''}
        ORDER BY ts_rank(search_vector, plainto_tsquery('english', :q)) DESC
        LIMIT :lim
    """)
    rows = (await db.execute(sql, {"q": query, "lim": limit, **where_params})).all()
    return [r.id for r in rows]


async def rerank(query: str, candidates: List[str], top_k: int) -> List[int]:
    """Returns indices into `candidates` ordered by FlashRank score, top_k."""
    try:
        from flashrank import Ranker, RerankRequest
        ranker = Ranker()
        passages = [{"id": str(i), "text": c} for i, c in enumerate(candidates)]
        ranked = ranker.rerank(RerankRequest(query=query, passages=passages))
        return [int(r["id"]) for r in ranked[:top_k]]
    except Exception:
        logger.debug("rerank unavailable; returning original order")
        return list(range(min(top_k, len(candidates))))
```

- [ ] **Step 3: Refactor `memory_service.search_memory` to call helpers**

Inside `memory_service.py`, replace the body of `search_memory` (around lines 256-302) so that the inline RRF + reranking code calls into `_hybrid_search` helpers. Existing function signatures stay identical; behavior must not change.

- [ ] **Step 4: Run existing memory tests**

```bash
docker compose exec backend pytest tests/test_memory_service.py -v
```

Expected: same green/red as before the refactor (no regressions).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/_hybrid_search.py backend/app/services/memory_service.py
git commit -m "refactor(memory): extract generic _hybrid_search helper"
```

---

### Task 13: `knowledge_service.search_knowledge` + tests

**Files:**
- Create: `backend/app/services/knowledge_service.py`
- Create: `backend/tests/test_knowledge_service.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_knowledge_service.py
import pytest
from unittest.mock import AsyncMock, patch

from app.services.knowledge_service import search_knowledge
from app.models.knowledge import KnowledgeNode


@pytest.mark.asyncio
async def test_search_returns_user_scoped_results(db_session, sample_user):
    db_session.add_all([
        KnowledgeNode(user_id=sample_user.id, node_type="decision",
                      title="pgvector", content="use pgvector for search",
                      created_by="manual_promote"),
        KnowledgeNode(user_id=sample_user.id, node_type="claim",
                      title="bm25 helps", content="hybrid retrieval improves recall",
                      created_by="manual_promote"),
    ])
    await db_session.commit()

    with patch("app.services.knowledge_service._embed_query", new=AsyncMock(return_value=[0.0]*768)):
        hits = await search_knowledge(
            user_id=sample_user.id, query="pgvector", limit=5, db=db_session,
        )
    assert any(h.node.title == "pgvector" for h in hits)


@pytest.mark.asyncio
async def test_search_filters_archived(db_session, sample_user):
    db_session.add(KnowledgeNode(
        user_id=sample_user.id, node_type="claim", title="old", content="archived content",
        archived=True, created_by="manual_promote",
    ))
    await db_session.commit()
    with patch("app.services.knowledge_service._embed_query", new=AsyncMock(return_value=[0.0]*768)):
        hits = await search_knowledge(
            user_id=sample_user.id, query="old", limit=5, db=db_session,
        )
    assert all(not h.node.archived for h in hits)
```

- [ ] **Step 2: Run — fail**

```bash
docker compose exec backend pytest tests/test_knowledge_service.py -v
```

- [ ] **Step 3: Implement**

```python
# backend/app/services/knowledge_service.py
"""Knowledge query API. Reuses _hybrid_search.

See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md
"""
import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeNode, KnowledgeEdge
from app.services._hybrid_search import (
    bm25_search, rerank, reciprocal_rank_fusion, vector_search,
)
from app.services.ai_client import get_cloud_client

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeHit:
    node: KnowledgeNode
    score: float


async def _embed_query(query: str) -> List[float]:
    return await get_cloud_client().embed(query)


def _build_where(
    user_id: uuid.UUID, project_id: Optional[uuid.UUID],
    node_types: Optional[List[str]], include_archived: bool,
) -> tuple[str, dict]:
    parts = ["user_id = :uid"]
    params: dict = {"uid": str(user_id)}
    if project_id is not None:
        parts.append("project_id = :pid")
        params["pid"] = str(project_id)
    if node_types:
        parts.append("node_type = ANY(:ntypes)")
        params["ntypes"] = node_types
    if not include_archived:
        parts.append("archived = false")
    return " AND ".join(parts), params


async def search_knowledge(
    user_id: uuid.UUID,
    query: str,
    db: AsyncSession,
    project_id: Optional[uuid.UUID] = None,
    node_types: Optional[List[str]] = None,
    limit: int = 10,
    include_archived: bool = False,
) -> List[KnowledgeHit]:
    where_sql, params = _build_where(user_id, project_id, node_types, include_archived)
    fetch = limit * 2

    embedding = await _embed_query(query)
    vec_ids = await vector_search(db, "knowledge_nodes", embedding, fetch, where_sql, params)
    bm_ids = await bm25_search(db, "knowledge_nodes", query, fetch, where_sql, params)

    if vec_ids and bm_ids:
        fused = reciprocal_rank_fusion([vec_ids, bm_ids])
    else:
        fused = vec_ids or bm_ids
    if not fused:
        return []

    nodes_by_id = {
        n.id: n for n in (await db.execute(
            select(KnowledgeNode).where(KnowledgeNode.id.in_(fused[:fetch]))
        )).scalars().all()
    }
    candidates: List[KnowledgeNode] = [nodes_by_id[i] for i in fused if i in nodes_by_id]

    if len(candidates) > limit:
        ordered_idx = await rerank(
            query, [f"{c.title}\n{c.content}" for c in candidates[:limit * 3]], top_k=limit,
        )
        candidates = [candidates[i] for i in ordered_idx]

    return [KnowledgeHit(node=n, score=1.0 - i * 0.01) for i, n in enumerate(candidates[:limit])]


async def get_node_with_neighbors(
    node_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession, depth: int = 1,
) -> tuple[List[KnowledgeNode], List[KnowledgeEdge]]:
    """Return (nodes, edges) — center node + neighbors out to `depth`."""
    visited: set[uuid.UUID] = {node_id}
    frontier: set[uuid.UUID] = {node_id}
    all_edges: List[KnowledgeEdge] = []
    for _ in range(depth):
        if not frontier:
            break
        edges = (await db.execute(
            select(KnowledgeEdge).where(
                KnowledgeEdge.user_id == user_id,
                (KnowledgeEdge.source_node_id.in_(frontier))
                | (KnowledgeEdge.target_node_id.in_(frontier)),
            )
        )).scalars().all()
        all_edges.extend(edges)
        next_frontier: set[uuid.UUID] = set()
        for e in edges:
            for nid in (e.source_node_id, e.target_node_id):
                if nid not in visited:
                    next_frontier.add(nid)
                    visited.add(nid)
        frontier = next_frontier

    nodes = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id.in_(visited), KnowledgeNode.user_id == user_id,
        )
    )).scalars().all()
    return list(nodes), all_edges


async def list_recent_nodes(
    user_id: uuid.UUID, db: AsyncSession,
    project_id: Optional[uuid.UUID] = None, limit: int = 50,
) -> List[KnowledgeNode]:
    stmt = (
        select(KnowledgeNode)
        .where(KnowledgeNode.user_id == user_id, KnowledgeNode.archived.is_(False))
        .order_by(KnowledgeNode.created_at.desc())
        .limit(limit)
    )
    if project_id is not None:
        stmt = stmt.where(KnowledgeNode.project_id == project_id)
    return list((await db.execute(stmt)).scalars().all())
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec backend pytest tests/test_knowledge_service.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/knowledge_service.py backend/tests/test_knowledge_service.py
git commit -m "feat(knowledge): query API — search/get_neighbors/list_recent"
```

---

### Task 14: Wire knowledge into `chat_service._build_context`

**Files:**
- Modify: `backend/app/services/chat_service.py`

- [ ] **Step 1: Locate `_build_context`**

```bash
grep -n "_build_context\|## Relevant Memory" backend/app/services/chat_service.py
```

- [ ] **Step 2: Add knowledge block**

After the existing memory block in `_build_context`, add:

```python
if include_memory:
    try:
        from app.services.knowledge_service import search_knowledge
        hits = await search_knowledge(
            user_id=user_id_uuid, query=user_message, limit=5, db=db,
        )
        if hits:
            lines = [f"- [{h.node.node_type}] {h.node.title} — {h.node.content[:200]}"
                     for h in hits]
            sections.append("## Relevant Knowledge\n" + "\n".join(lines))
    except Exception:
        logger.exception("knowledge lookup failed (non-fatal)")
```

`user_id_uuid` must be the resolved owner. If only `project_id` is in scope here, look up `project.user_id`.

- [ ] **Step 3: Smoke test**

Send a chat message in a project that has knowledge nodes; verify the response references prior decisions. Inspect logs for the `## Relevant Knowledge` block being assembled (`logger.debug` if needed).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat_service.py
git commit -m "feat(knowledge): inject knowledge block into chat context"
```

---

### Task 15: Wire knowledge into `paper_service._build_paper_context`

**Files:**
- Modify: `backend/app/services/paper_service.py`

- [ ] **Step 1: Locate `_build_paper_context`**

```bash
grep -n "_build_paper_context\|context_block" backend/app/services/paper_service.py | head -20
```

- [ ] **Step 2: Add a knowledge section before the function returns**

```python
try:
    from app.services.knowledge_service import search_knowledge
    project = await db.get(Project, project_id)
    user_id = project.user_id if project else None
    if user_id:
        hits = await search_knowledge(
            user_id=user_id,
            query=f"{paper_title or ''} {paper_topic or ''}",
            db=db, project_id=project_id, limit=15,
            node_types=["claim", "insight", "hypothesis", "decision"],
        )
        if hits:
            lines = [f"- [{h.node.node_type}] {h.node.title} — {h.node.content}" for h in hits]
            context_block += "\n\n## Project knowledge\n" + "\n".join(lines)
except Exception:
    logger.exception("knowledge enrichment of paper context failed (non-fatal)")
```

(Adapt variable names — `paper_title`/`paper_topic`/`context_block` to match the existing function signature.)

- [ ] **Step 3: Generate a test paper**

```bash
curl -s -H "X-API-Key: $API_KEY" -X POST http://localhost:8989/api/v1/projects/<id>/paper/generate-v2 -d '{"title":"Test","paper_type":"workshop"}' | jq .status
```

Inspect the saved context block: should include `## Project knowledge` if nodes exist.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/paper_service.py
git commit -m "feat(knowledge): paper context now pulls knowledge nodes"
```

---

### Task 16: Wire knowledge into `draft_service`

**Files:**
- Modify: `backend/app/services/draft_service.py`

- [ ] **Step 1: Locate where draft generation context is assembled**

```bash
grep -n "system\|context\|generate" backend/app/services/draft_service.py | head -20
```

- [ ] **Step 2: Inject 10 hits filtered to the draft's project**

Insert into the prompt-building path:

```python
try:
    from app.services.knowledge_service import search_knowledge
    if project and project.user_id:
        hits = await search_knowledge(
            user_id=project.user_id, query=draft.topic or draft.title or "",
            db=db, project_id=project.id, limit=10,
        )
        if hits:
            knowledge_block = "## Project knowledge\n" + "\n".join(
                f"- [{h.node.node_type}] {h.node.title} — {h.node.content[:300]}" for h in hits
            )
            user_prompt = f"{knowledge_block}\n\n{user_prompt}"
except Exception:
    logger.exception("knowledge enrichment of draft failed (non-fatal)")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/draft_service.py
git commit -m "feat(knowledge): draft generation pulls project knowledge"
```

---

### Task 17: Wire knowledge into `worklog_service`

**Files:**
- Modify: `backend/app/services/worklog_service.py`

- [ ] **Step 1: Locate worklog narrative generation**

```bash
grep -n "generate\|narrative\|period" backend/app/services/worklog_service.py | head -20
```

- [ ] **Step 2: Pull date-range nodes grouped by type**

```python
from sqlalchemy import select
from app.models.knowledge import KnowledgeNode

async def _knowledge_in_range(db, user_id, start, end, project_id=None):
    stmt = (
        select(KnowledgeNode)
        .where(
            KnowledgeNode.user_id == user_id,
            KnowledgeNode.archived.is_(False),
            KnowledgeNode.created_at >= start,
            KnowledgeNode.created_at <= end,
        )
        .order_by(KnowledgeNode.created_at.asc())
    )
    if project_id:
        stmt = stmt.where(KnowledgeNode.project_id == project_id)
    return list((await db.execute(stmt)).scalars().all())
```

In the worklog narrative builder, group by `node_type` into structured sections (Decisions made, Open questions, Blockers, etc.) and inject before the AI summary call.

- [ ] **Step 3: Generate a worklog and inspect**

```bash
curl -s -H "X-API-Key: $API_KEY" "http://localhost:8989/api/v1/worklog?period=weekly" | jq .markdown
```

Expected: includes a "Decisions" / "Questions" / "Blockers" section if recent nodes exist.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/worklog_service.py
git commit -m "feat(knowledge): worklog includes period decisions/questions/blockers"
```

---

## Phase 1c — Graph UI + manual promote on chat (Tasks 18–28)

### Task 18: Backend routes — list + CRUD nodes

**Files:**
- Create: `backend/app/routers/knowledge.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the router**

```python
# backend/app/routers/knowledge.py
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, verify_api_key
from app.models.knowledge import KnowledgeEdge, KnowledgeNode, NODE_TYPES
from app.schemas.knowledge import (
    GraphResponse, KnowledgeEdgeOut, KnowledgeNodeOut,
    NodeCreateRequest, NodeUpdateRequest, PromoteRequest,
)
from app.services import knowledge_extractor, knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _resolve_user_id(auth_user_id: Optional[str]) -> uuid.UUID:
    if not auth_user_id:
        raise HTTPException(status_code=400, detail="user-scoped endpoint requires JWT auth")
    return uuid.UUID(auth_user_id)


@router.get("/nodes", response_model=List[KnowledgeNodeOut])
async def list_nodes(
    project_id: Optional[uuid.UUID] = Query(default=None),
    node_type: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    if project_id is not None:
        stmt = stmt.where(KnowledgeNode.project_id == project_id)
    if node_type is not None:
        if node_type not in NODE_TYPES:
            raise HTTPException(400, f"node_type must be one of {sorted(NODE_TYPES)}")
        stmt = stmt.where(KnowledgeNode.node_type == node_type)
    if not include_archived:
        stmt = stmt.where(KnowledgeNode.archived.is_(False))
    stmt = stmt.order_by(KnowledgeNode.created_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@router.post("/nodes", response_model=KnowledgeNodeOut, status_code=status.HTTP_201_CREATED)
async def create_node(
    body: NodeCreateRequest,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    from app.schemas.knowledge import SourceRef
    src = body.source_refs[0] if body.source_refs else SourceRef(kind="manual")
    node = await knowledge_extractor.promote_manual(
        user_id=user_id, project_id=body.project_id, source=src,
        suggested_type=body.node_type, title=body.title, content=body.content, db=db,
    )
    return node


@router.patch("/nodes/{node_id}", response_model=KnowledgeNodeOut)
async def update_node(
    node_id: uuid.UUID,
    body: NodeUpdateRequest,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    node = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not node:
        raise HTTPException(404, "node not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(node, field, val)
    await db.commit()
    await db.refresh(node)
    return node


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: uuid.UUID,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    node = (await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == node_id, KnowledgeNode.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not node:
        raise HTTPException(404, "node not found")
    await db.delete(node)
    await db.commit()


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    root: uuid.UUID = Query(...),
    depth: int = Query(default=1, ge=1, le=3),
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    nodes, edges = await knowledge_service.get_node_with_neighbors(
        node_id=root, user_id=user_id, db=db, depth=depth,
    )
    return GraphResponse(
        nodes=[KnowledgeNodeOut.model_validate(n) for n in nodes],
        edges=[KnowledgeEdgeOut.model_validate(e) for e in edges],
    )


@router.post("/promote", response_model=KnowledgeNodeOut, status_code=status.HTTP_201_CREATED)
async def promote(
    body: PromoteRequest,
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    if not body.title or not body.content:
        raise HTTPException(400, "title and content required")
    node = await knowledge_extractor.promote_manual(
        user_id=user_id, project_id=body.project_id, source=body.source,
        suggested_type=body.suggested_type, title=body.title, content=body.content, db=db,
    )
    return node
```

- [ ] **Step 2: Register router**

In `backend/app/main.py` after line 222 (next to other `app.include_router` calls):

```python
from app.routers import knowledge as knowledge_router
app.include_router(knowledge_router.router, prefix=API_PREFIX)
```

- [ ] **Step 3: Restart backend**

```bash
docker compose restart backend
```

- [ ] **Step 4: Smoke-test endpoints**

```bash
TOKEN="<your jwt>"
curl -s -H "Authorization: Bearer $TOKEN" -H "X-API-Key: $API_KEY" \
  "http://localhost:8989/api/v1/knowledge/nodes?limit=5" | jq .
```

Expected: array of nodes (or `[]`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/knowledge.py backend/app/main.py
git commit -m "feat(knowledge): REST routes — list/CRUD/graph/promote"
```

---

### Task 19: Backend route tests

**Files:**
- Create: `backend/tests/test_knowledge_routes.py`

- [ ] **Step 1: Write integration tests**

```python
# backend/tests/test_knowledge_routes.py
import pytest


@pytest.mark.asyncio
async def test_list_nodes_empty(async_client, auth_headers):
    r = await async_client.get("/api/v1/knowledge/nodes", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_create_then_list_then_archive(async_client, auth_headers):
    body = {
        "node_type": "decision",
        "title": "test decision",
        "content": "we decided to test",
    }
    r = await async_client.post("/api/v1/knowledge/nodes", json=body, headers=auth_headers)
    assert r.status_code == 201
    nid = r.json()["id"]

    r = await async_client.get("/api/v1/knowledge/nodes", headers=auth_headers)
    assert any(n["id"] == nid for n in r.json())

    r = await async_client.patch(
        f"/api/v1/knowledge/nodes/{nid}", json={"archived": True}, headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["archived"] is True


@pytest.mark.asyncio
async def test_create_invalid_type_400(async_client, auth_headers):
    r = await async_client.post(
        "/api/v1/knowledge/nodes",
        json={"node_type": "wishful", "title": "t", "content": "c"},
        headers=auth_headers,
    )
    assert r.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_promote_creates_node(async_client, auth_headers):
    r = await async_client.post(
        "/api/v1/knowledge/promote",
        json={
            "source": {"kind": "manual", "note": "test"},
            "suggested_type": "insight",
            "title": "promoted",
            "content": "from manual flow",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["title"] == "promoted"
```

`auth_headers` and `async_client` should already exist in `conftest.py`. Verify:

```bash
grep -E "async_client|auth_headers" backend/tests/conftest.py
```

- [ ] **Step 2: Run**

```bash
docker compose exec backend pytest tests/test_knowledge_routes.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_knowledge_routes.py
git commit -m "test(knowledge): route integration tests"
```

---

### Task 20: Frontend — install React Flow + dagre

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install**

```bash
docker compose exec frontend npm install @xyflow/react dagre
docker compose exec frontend npm install -D @types/dagre
```

- [ ] **Step 2: Verify**

```bash
docker compose exec frontend node -e "console.log(require('@xyflow/react/package.json').version)"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add @xyflow/react + dagre for knowledge graph UI"
```

---

### Task 21: Frontend types + SWR hooks

**Files:**
- Create: `frontend/lib/knowledge.ts`

- [ ] **Step 1: Implement**

```typescript
// frontend/lib/knowledge.ts
import useSWR from "swr";
import { fetcher } from "@/lib/api";  // existing utility — verify path

export type NodeType =
  | "claim" | "decision" | "question" | "hypothesis"
  | "rejection" | "blocker" | "insight";

export type EdgeType =
  | "supports" | "contradicts" | "refines" | "follows_up"
  | "depends_on" | "derives_from" | "rejects" | "related_to";

export interface SourceRef {
  kind: string;
  id?: string;
  excerpt?: string;
  note?: string;
}

export interface KnowledgeNode {
  id: string;
  user_id: string;
  project_id: string | null;
  node_type: NodeType;
  title: string;
  content: string;
  source_refs: SourceRef[];
  metadata: Record<string, unknown>;
  archived: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: EdgeType;
  weight: number;
  created_at: string;
}

export const NODE_COLORS: Record<NodeType, string> = {
  claim:      "#3b82f6",
  decision:   "#22c55e",
  question:   "#f59e0b",
  hypothesis: "#a855f7",
  rejection:  "#ef4444",
  blocker:    "#f97316",
  insight:    "#14b8a6",
};

export const EDGE_STYLES: Record<EdgeType, { stroke: string; dashed?: boolean }> = {
  supports:     { stroke: "#22c55e" },
  contradicts:  { stroke: "#ef4444", dashed: true },
  refines:      { stroke: "#3b82f6" },
  follows_up:   { stroke: "#a855f7" },
  depends_on:   { stroke: "#f97316" },
  derives_from: { stroke: "#94a3b8", dashed: true },
  rejects:      { stroke: "#ef4444" },
  related_to:   { stroke: "#94a3b8", dashed: true },
};

export function useNodes(params: {
  projectId?: string; nodeType?: NodeType; includeArchived?: boolean; limit?: number;
}) {
  const qs = new URLSearchParams();
  if (params.projectId)       qs.set("project_id", params.projectId);
  if (params.nodeType)        qs.set("node_type", params.nodeType);
  if (params.includeArchived) qs.set("include_archived", "true");
  if (params.limit)           qs.set("limit", String(params.limit));
  return useSWR<KnowledgeNode[]>(`/api/v1/knowledge/nodes?${qs.toString()}`, fetcher);
}

export function useGraph(rootId: string | null, depth = 1) {
  return useSWR<{ nodes: KnowledgeNode[]; edges: KnowledgeEdge[] }>(
    rootId ? `/api/v1/knowledge/graph?root=${rootId}&depth=${depth}` : null,
    fetcher,
  );
}

export async function patchNode(id: string, body: Partial<KnowledgeNode>) {
  const res = await fetch(`/api/v1/knowledge/nodes/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<KnowledgeNode>;
}

export async function deleteNode(id: string) {
  const res = await fetch(`/api/v1/knowledge/nodes/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok && res.status !== 204) throw new Error(await res.text());
}

export async function promoteNode(body: {
  project_id?: string; source: SourceRef; suggested_type?: NodeType;
  title: string; content: string;
}) {
  const res = await fetch(`/api/v1/knowledge/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<KnowledgeNode>;
}
```

- [ ] **Step 2: Verify fetcher path**

```bash
grep -rn "export.*fetcher" frontend/lib/ | head -3
```

If the path is different, adjust the `import { fetcher }` line.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/knowledge.ts
git commit -m "feat(knowledge ui): types + SWR hooks for knowledge API"
```

---

### Task 22: `/knowledge` page scaffolding

**Files:**
- Create: `frontend/app/knowledge/page.tsx`

- [ ] **Step 1: Implement minimal page**

```tsx
// frontend/app/knowledge/page.tsx
"use client";
import { useState } from "react";
import { useNodes, type NodeType, type KnowledgeNode } from "@/lib/knowledge";
import { KnowledgeFilters } from "@/components/knowledge/KnowledgeFilters";
import { KnowledgeGraph } from "@/components/knowledge/KnowledgeGraph";
import { NodeDetailPanel } from "@/components/knowledge/NodeDetailPanel";

export default function KnowledgePage() {
  const [projectId, setProjectId] = useState<string | undefined>();
  const [nodeType, setNodeType] = useState<NodeType | undefined>();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selected, setSelected] = useState<KnowledgeNode | null>(null);

  const { data: nodes = [], mutate } = useNodes({
    projectId, nodeType, includeArchived, limit: 200,
  });

  return (
    <div className="flex h-screen">
      <KnowledgeFilters
        projectId={projectId} onProjectChange={setProjectId}
        nodeType={nodeType} onTypeChange={setNodeType}
        includeArchived={includeArchived} onIncludeArchivedChange={setIncludeArchived}
      />
      <div className="flex-1 flex flex-col">
        <header className="p-4 border-b">
          <h1 className="text-2xl font-semibold">Knowledge</h1>
          <p className="text-sm text-muted-foreground">
            {nodes.length} node{nodes.length === 1 ? "" : "s"}
          </p>
        </header>
        <div className="flex-1 relative">
          <KnowledgeGraph nodes={nodes} onSelect={setSelected} />
        </div>
        {selected && (
          <NodeDetailPanel
            node={selected}
            onClose={() => setSelected(null)}
            onChanged={() => { mutate(); }}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit (component stubs come next; expect type errors until Tasks 23-25)**

```bash
git add frontend/app/knowledge/page.tsx
git commit -m "feat(knowledge ui): /knowledge page scaffolding"
```

---

### Task 23: KnowledgeFilters sidebar

**Files:**
- Create: `frontend/components/knowledge/KnowledgeFilters.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/components/knowledge/KnowledgeFilters.tsx
"use client";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { NodeType } from "@/lib/knowledge";

const NODE_TYPES: NodeType[] = [
  "claim", "decision", "question", "hypothesis", "rejection", "blocker", "insight",
];

interface Props {
  projectId: string | undefined;
  onProjectChange: (id: string | undefined) => void;
  nodeType: NodeType | undefined;
  onTypeChange: (t: NodeType | undefined) => void;
  includeArchived: boolean;
  onIncludeArchivedChange: (v: boolean) => void;
}

interface ProjectMin { id: string; name: string; }

export function KnowledgeFilters(p: Props) {
  const { data: projects = [] } = useSWR<ProjectMin[]>("/api/v1/projects", fetcher);

  return (
    <aside className="w-64 border-r p-4 space-y-6 bg-card">
      <div>
        <label className="text-sm font-medium">Project</label>
        <select
          className="mt-1 w-full p-2 rounded border bg-background"
          value={p.projectId ?? ""}
          onChange={(e) => p.onProjectChange(e.target.value || undefined)}
        >
          <option value="">All projects</option>
          {projects.map((pr) => (
            <option key={pr.id} value={pr.id}>{pr.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-sm font-medium">Type</label>
        <div className="mt-1 space-y-1">
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" checked={!p.nodeType}
                   onChange={() => p.onTypeChange(undefined)} />
            All
          </label>
          {NODE_TYPES.map((t) => (
            <label key={t} className="flex items-center gap-2 text-sm">
              <input type="radio" checked={p.nodeType === t}
                     onChange={() => p.onTypeChange(t)} />
              {t}
            </label>
          ))}
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={p.includeArchived}
               onChange={(e) => p.onIncludeArchivedChange(e.target.checked)} />
        Show archived
      </label>
    </aside>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/knowledge/KnowledgeFilters.tsx
git commit -m "feat(knowledge ui): filter sidebar"
```

---

### Task 24: KnowledgeGraph canvas (React Flow + dagre)

**Files:**
- Create: `frontend/components/knowledge/KnowledgeGraph.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/components/knowledge/KnowledgeGraph.tsx
"use client";
import { useEffect, useMemo } from "react";
import { ReactFlow, Background, Controls, type Edge, type Node, useNodesState, useEdgesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { NODE_COLORS, EDGE_STYLES, type KnowledgeNode } from "@/lib/knowledge";
import useSWR from "swr";
import { fetcher } from "@/lib/api";

interface Props {
  nodes: KnowledgeNode[];
  onSelect: (n: KnowledgeNode) => void;
}

const NODE_W = 220;
const NODE_H = 70;

function layout(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 60 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}

export function KnowledgeGraph({ nodes, onSelect }: Props) {
  // For v1 we render the full filtered set as a flat graph. Edges come from /graph
  // for the currently-selected node would expand the view; here we fetch all edges
  // for visible nodes via a helper (or, simpler: we omit edges until selection).
  const { data: allEdges } = useSWR<{ edges: { id: string; source_node_id: string; target_node_id: string; edge_type: string }[] }>(
    nodes.length ? `/api/v1/knowledge/edges?ids=${nodes.map(n => n.id).join(",")}` : null,
    fetcher,
  );

  const initialNodes: Node[] = useMemo(
    () => nodes.map((n) => ({
      id: n.id,
      data: { label: <NodeLabel node={n} /> },
      position: { x: 0, y: 0 },
      style: {
        background: "white",
        border: `2px solid ${NODE_COLORS[n.node_type]}`,
        borderRadius: 8, padding: 8, width: NODE_W,
      },
    })),
    [nodes],
  );

  const initialEdges: Edge[] = useMemo(
    () => (allEdges?.edges ?? []).map((e) => ({
      id: e.id,
      source: e.source_node_id,
      target: e.target_node_id,
      label: e.edge_type,
      style: {
        stroke: EDGE_STYLES[e.edge_type as keyof typeof EDGE_STYLES]?.stroke ?? "#888",
        strokeDasharray: EDGE_STYLES[e.edge_type as keyof typeof EDGE_STYLES]?.dashed ? "4 4" : undefined,
      },
    })),
    [allEdges],
  );

  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => { setRfNodes(layout(initialNodes, initialEdges)); }, [initialNodes, initialEdges, setRfNodes]);
  useEffect(() => { setRfEdges(initialEdges); }, [initialEdges, setRfEdges]);

  return (
    <ReactFlow
      nodes={rfNodes} edges={rfEdges}
      onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
      onNodeClick={(_, n) => {
        const found = nodes.find((x) => x.id === n.id);
        if (found) onSelect(found);
      }}
      fitView
    >
      <Background />
      <Controls />
    </ReactFlow>
  );
}

function NodeLabel({ node }: { node: KnowledgeNode }) {
  return (
    <div className="text-xs text-left">
      <div className="font-medium truncate">{node.title}</div>
      <div className="opacity-70 truncate">{node.node_type}</div>
    </div>
  );
}
```

- [ ] **Step 2: Add the missing `/edges` helper endpoint**

This component uses `/api/v1/knowledge/edges?ids=...`. Add to `backend/app/routers/knowledge.py`:

```python
@router.get("/edges", response_model=List[KnowledgeEdgeOut])
async def list_edges_for_nodes(
    ids: str = Query(..., description="comma-separated node ids"),
    auth_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_user_id(auth_user_id)
    try:
        node_ids = [uuid.UUID(s) for s in ids.split(",") if s]
    except ValueError:
        raise HTTPException(400, "ids must be comma-separated UUIDs")
    if not node_ids:
        return []
    edges = (await db.execute(
        select(KnowledgeEdge).where(
            KnowledgeEdge.user_id == user_id,
            KnowledgeEdge.source_node_id.in_(node_ids),
            KnowledgeEdge.target_node_id.in_(node_ids),
        )
    )).scalars().all()
    return list(edges)
```

Restart backend.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/knowledge/KnowledgeGraph.tsx backend/app/routers/knowledge.py
git commit -m "feat(knowledge ui): React Flow canvas with dagre layout"
```

---

### Task 25: NodeDetailPanel

**Files:**
- Create: `frontend/components/knowledge/NodeDetailPanel.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/components/knowledge/NodeDetailPanel.tsx
"use client";
import { useState } from "react";
import { type KnowledgeNode, NODE_COLORS, deleteNode, patchNode } from "@/lib/knowledge";

interface Props {
  node: KnowledgeNode;
  onClose: () => void;
  onChanged: () => void;
}

export function NodeDetailPanel({ node, onClose, onChanged }: Props) {
  const [busy, setBusy] = useState(false);

  return (
    <aside className="border-t p-4 max-h-72 overflow-auto bg-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span
            className="inline-block px-2 py-0.5 rounded text-xs text-white"
            style={{ background: NODE_COLORS[node.node_type] }}
          >
            {node.node_type}
          </span>
          <h2 className="text-lg font-semibold mt-1">{node.title}</h2>
        </div>
        <button onClick={onClose} className="text-sm opacity-60 hover:opacity-100">close</button>
      </div>
      <p className="mt-2 text-sm">{node.content}</p>

      <div className="mt-3 text-xs opacity-70">
        Created {new Date(node.created_at).toLocaleString()} · {node.created_by}
      </div>

      {node.source_refs.length > 0 && (
        <div className="mt-2 text-xs">
          <div className="font-medium opacity-80">Sources</div>
          <ul className="list-disc pl-4">
            {node.source_refs.map((s, i) => (
              <li key={i}>{s.kind}{s.id ? ` · ${s.id.slice(0, 8)}` : ""}{s.note ? ` — ${s.note}` : ""}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex gap-2">
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            await patchNode(node.id, { archived: !node.archived });
            setBusy(false);
            onChanged();
          }}
          className="text-sm px-2 py-1 rounded border"
        >
          {node.archived ? "Unarchive" : "Archive"}
        </button>
        <button
          disabled={busy}
          onClick={async () => {
            if (!confirm("Delete this node?")) return;
            setBusy(true);
            await deleteNode(node.id);
            setBusy(false);
            onChanged();
            onClose();
          }}
          className="text-sm px-2 py-1 rounded border text-red-600"
        >
          Delete
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Verify the page renders end-to-end**

```bash
docker compose exec frontend npm run build
```
Expected: clean build (no TS errors).

Visit http://localhost:3989/knowledge in the browser. Filters + canvas + detail panel all functional.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/knowledge/NodeDetailPanel.tsx
git commit -m "feat(knowledge ui): node detail panel with archive/delete"
```

---

### Task 26: PromoteButton + PromoteModal

**Files:**
- Create: `frontend/components/knowledge/PromoteButton.tsx`
- Create: `frontend/components/knowledge/PromoteModal.tsx`

- [ ] **Step 1: PromoteModal**

```tsx
// frontend/components/knowledge/PromoteModal.tsx
"use client";
import { useState } from "react";
import { promoteNode, type NodeType, type SourceRef } from "@/lib/knowledge";

const TYPES: NodeType[] = [
  "claim", "decision", "question", "hypothesis", "rejection", "blocker", "insight",
];

interface Props {
  open: boolean;
  source: SourceRef;
  projectId?: string;
  defaultExcerpt?: string;
  onClose: () => void;
  onSaved: () => void;
}

export function PromoteModal({ open, source, projectId, defaultExcerpt, onClose, onSaved }: Props) {
  const [type, setType] = useState<NodeType>("insight");
  const [title, setTitle] = useState(defaultExcerpt?.slice(0, 80) ?? "");
  const [content, setContent] = useState(defaultExcerpt ?? "");
  const [busy, setBusy] = useState(false);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-card rounded-lg p-6 w-[480px] space-y-4" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">Save as knowledge</h2>
        <label className="block text-sm">
          Type
          <select value={type} onChange={(e) => setType(e.target.value as NodeType)}
                  className="mt-1 w-full p-2 rounded border bg-background">
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="block text-sm">
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160}
                 className="mt-1 w-full p-2 rounded border bg-background" />
        </label>
        <label className="block text-sm">
          Content
          <textarea value={content} onChange={(e) => setContent(e.target.value)}
                    className="mt-1 w-full p-2 rounded border bg-background h-24" />
        </label>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1 rounded border text-sm">Cancel</button>
          <button
            disabled={busy || !title || !content}
            onClick={async () => {
              setBusy(true);
              await promoteNode({ project_id: projectId, source, suggested_type: type, title, content });
              setBusy(false);
              onSaved(); onClose();
            }}
            className="px-3 py-1 rounded bg-primary text-primary-foreground text-sm"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: PromoteButton**

```tsx
// frontend/components/knowledge/PromoteButton.tsx
"use client";
import { useState } from "react";
import { Bookmark } from "lucide-react";
import { PromoteModal } from "./PromoteModal";
import type { SourceRef } from "@/lib/knowledge";

interface Props {
  source: SourceRef;
  projectId?: string;
  defaultExcerpt?: string;
  className?: string;
}

export function PromoteButton({ source, projectId, defaultExcerpt, className }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        title="Save as knowledge"
        onClick={() => setOpen(true)}
        className={className ?? "opacity-50 hover:opacity-100"}
      >
        <Bookmark className="w-4 h-4" />
      </button>
      <PromoteModal
        open={open} source={source} projectId={projectId} defaultExcerpt={defaultExcerpt}
        onClose={() => setOpen(false)} onSaved={() => { /* could toast */ }}
      />
    </>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/knowledge/PromoteButton.tsx frontend/components/knowledge/PromoteModal.tsx
git commit -m "feat(knowledge ui): manual promote button + modal"
```

---

### Task 27: Wire PromoteButton into ChatMessage

**Files:**
- Modify: `frontend/components/chat/ChatMessage.tsx`

- [ ] **Step 1: Find where AI messages render**

```bash
grep -n "role.*assistant\|role === " frontend/components/chat/ChatMessage.tsx
```

- [ ] **Step 2: Add the button on assistant messages**

In the assistant-message render path, add (e.g., in a hover toolbar):

```tsx
import { PromoteButton } from "@/components/knowledge/PromoteButton";

// inside the assistant render block:
{message.role === "assistant" && (
  <PromoteButton
    source={{ kind: "chat_message", id: message.id, excerpt: message.content.slice(0, 200) }}
    projectId={projectId}
    defaultExcerpt={message.content.slice(0, 400)}
    className="ml-2 opacity-40 hover:opacity-100"
  />
)}
```

`projectId` should already be in scope via props or context — adapt to the component's existing pattern.

- [ ] **Step 3: Visual check**

Open a roundtable conversation in the browser. Hover an assistant message — bookmark icon appears. Click → modal opens with content prefilled. Save → toast/silent success → reload `/knowledge`, new node visible.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/chat/ChatMessage.tsx
git commit -m "feat(knowledge ui): promote button on roundtable AI messages"
```

---

### Task 28: Add `/knowledge` to navigation

**Files:**
- Modify: whichever file holds the global nav

- [ ] **Step 1: Find nav**

```bash
grep -rn "href=\"/projects\"\|href={\"/projects" frontend/components/ frontend/app/ | head -5
```

- [ ] **Step 2: Add link**

In the same nav, add (matching the existing item style):

```tsx
<Link href="/knowledge" className="...">Knowledge</Link>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/Header.tsx  # or wherever
git commit -m "feat(knowledge ui): nav link to /knowledge"
```

---

## Phase 1d — Manual promote on drafts & files (Tasks 29–30)

### Task 29: Selection-based promote on DraftEditor

**Files:**
- Modify: `frontend/components/DraftEditor.tsx`

- [ ] **Step 1: Locate the editor**

```bash
grep -n "onSelect\|selectionchange\|getSelection" frontend/components/DraftEditor.tsx
```

- [ ] **Step 2: Add a selection-driven floating button**

```tsx
import { useEffect, useState } from "react";
import { PromoteModal } from "@/components/knowledge/PromoteModal";

function useSelectionExcerpt(): { text: string; rect: DOMRect | null } {
  const [s, set] = useState<{ text: string; rect: DOMRect | null }>({ text: "", rect: null });
  useEffect(() => {
    const handler = () => {
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return set({ text: "", rect: null });
      const text = sel.toString().trim();
      if (!text) return set({ text: "", rect: null });
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      set({ text, rect });
    };
    document.addEventListener("selectionchange", handler);
    return () => document.removeEventListener("selectionchange", handler);
  }, []);
  return s;
}

// inside the editor component:
const { text, rect } = useSelectionExcerpt();
const [modalOpen, setModalOpen] = useState(false);
// ...
{rect && text.length > 5 && (
  <button
    style={{ position: "fixed", top: rect.top - 40, left: rect.left }}
    className="z-50 px-2 py-1 rounded bg-primary text-primary-foreground text-xs"
    onClick={() => setModalOpen(true)}
  >
    🔖 Save as knowledge
  </button>
)}
<PromoteModal
  open={modalOpen}
  source={{ kind: "draft", id: draft.id, excerpt: text.slice(0, 200) }}
  projectId={draft.project_id}
  defaultExcerpt={text}
  onClose={() => setModalOpen(false)}
  onSaved={() => { /* toast */ }}
/>
```

- [ ] **Step 3: Visual check**

Open a draft, select a sentence → floating button appears → click → modal prefilled.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/DraftEditor.tsx
git commit -m "feat(knowledge ui): selection-based promote on drafts"
```

---

### Task 30: Selection-based promote on file ingest pages

**Files:**
- Modify: whichever component renders file ingest content (find via grep)

- [ ] **Step 1: Find file content renderer**

```bash
grep -rn "file_ingest\|FileIngest\|ingest" frontend/app/ frontend/components/ | grep -E "\.tsx" | head -10
```

- [ ] **Step 2: Reuse the `useSelectionExcerpt` + `PromoteModal` pattern from Task 29**

Add the same floating button. `source.kind` becomes `"file_ingest"`, `source.id` is the memory entry id (since files become memory entries).

- [ ] **Step 3: Commit**

```bash
git add <the-modified-file-from-step-1>
git commit -m "feat(knowledge ui): selection-based promote on file pages"
```

If file ingest pages don't exist as a navigable surface yet, skip this task and note it in the PR description as deferred to whenever those pages get built.

---

## Final Verification

- [ ] **End-to-end smoke test**

1. Open `/projects/<id>/chat`, hold a 5-turn cofounder conversation
2. Wait 5s, refresh `/knowledge` — auto-extracted nodes appear
3. Hover an assistant message → bookmark → save with custom title → appears
4. Open a draft, select text → floating button → save → appears
5. Click a node in `/knowledge` → detail panel shows sources
6. Archive a node → disappears (until "Show archived" toggled)
7. Generate a paper for the project → confirm `## Project knowledge` appears in saved context
8. Generate a worklog → confirm Decisions/Questions/Blockers section

- [ ] **Run all tests**

```bash
docker compose exec backend pytest tests/ -v
docker compose exec frontend npm run lint && docker compose exec frontend npm run build
```

- [ ] **Final commit on the branch / open PR**

```bash
git log --oneline origin/main..HEAD
gh pr create --title "feat: knowledge layer (Phase 1)" --body "Implements docs/superpowers/specs/2026-05-04-knowledge-layer-design.md"
```
