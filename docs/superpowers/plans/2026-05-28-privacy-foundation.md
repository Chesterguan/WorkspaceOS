# Privacy Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the four foundation workstreams (W1 leak fixes, W2 `record_egress` instrumentation, W3 `privacy:*` tag namespace, W4 tag-resolving prompt assembler) that everything else in the privacy prototype depends on.

**Architecture:** Additive. No surface UI in this plan. We fix two leaks in existing services, add one new table (`egress_logs`), one new column (`Project.privacy_default`), one new context-manager service (`EgressRecorder`), one new pure function module (`privacy_assembler`), and a thin GET endpoint for the bench. Every behaviour change is gated behind code that already runs on the cloud-egress path — failing closed preserves current behaviour.

**Tech Stack:** Python 3.9+ typing (`Optional[]`, `List[]`, `Dict[]`), FastAPI, SQLAlchemy 2.0 (`Mapped`, `mapped_column`), Alembic, asyncpg, pytest + pytest-asyncio. Local dev: Docker Compose (`docker compose up --build -d backend`). Backend image is **not** source-mounted — rebuild after edits or `docker cp` for fast iteration (see memory: `backend-not-source-mounted`).

**Spec:** [`docs/superpowers/specs/2026-05-28-privacy-prototype-design.md`](../specs/2026-05-28-privacy-prototype-design.md)
**Investigation rationale:** [`docs/privacy/`](../../privacy/)

---

## File Structure

### Created

| File | Purpose |
|---|---|
| `backend/alembic/versions/0022_privacy_foundation.py` | Migration: `egress_logs` table + `projects.privacy_default` column |
| `backend/app/models/egress_log.py` | SQLAlchemy model for `egress_logs` |
| `backend/app/services/egress_recorder.py` | Context manager that records per-call egress |
| `backend/app/services/privacy_tags.py` | Reserved tag constants + tag resolution helpers |
| `backend/app/services/privacy_assembler.py` | `assemble_context()` — turns memory entries into stubs |
| `backend/app/routers/egress.py` | `GET /api/v1/egress/recent` |
| `backend/app/schemas/egress.py` | Pydantic schemas for the egress router |
| `backend/scripts/reembed_knowledge_nodes.py` | One-off script to re-embed knowledge nodes after L-1 fix |
| `backend/tests/test_privacy_tags.py` | Unit tests for tag resolution |
| `backend/tests/test_privacy_assembler.py` | Unit tests for the assembler |
| `backend/tests/test_egress_recorder.py` | Unit tests for the recorder |
| `backend/tests/test_egress_router.py` | Integration test for `/egress/recent` |
| `backend/tests/test_leak_fixes.py` | Regression tests for L-1 and L-2 |

### Modified

| File | Change |
|---|---|
| `backend/app/services/knowledge_service.py:30` | L-1 fix — `get_cloud_client()` → `get_local_client()` |
| `backend/app/services/agents.py:21,199-200` | L-2 fix — remove direct `OpenAIClient()` |
| `backend/app/services/agentic_generation.py:29,59-92` | L-2 fix — remove direct `OpenAIClient()` |
| `backend/app/services/paper_reviewers.py:23,200-203` | L-2 fix — gate behind `paper_reviewer_providers` setting |
| `backend/app/services/paper_service.py:35` | L-2 fix — gate behind the same setting |
| `backend/app/config.py` | Add `paper_reviewer_providers: List[str]` setting |
| `backend/app/models/project.py` | Add `privacy_default` column |
| `backend/app/services/ai_client.py:30-43` | Hook `EgressRecorder` into the `complete()` wrapper |
| `backend/app/main.py` | Wire `routers/egress.py` |

---

## Phase 1 — W1: Fix L-1 and L-2 leaks

### Task 1.1: Regression test for L-1 (knowledge query embed must be local)

**Files:**
- Test: `backend/tests/test_leak_fixes.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_leak_fixes.py`:

```python
"""Regression tests for the privacy leaks documented in
docs/privacy/known-leaks.md. Each test pins the contract: after the
fix, these calls must hit the local AI client, not the cloud one."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services import knowledge_service


@pytest.mark.asyncio
async def test_query_embedding_uses_local_client():
    """L-1: knowledge query embedding must go local, not cloud."""
    fake_local = AsyncMock()
    fake_local.embed.return_value = [0.0] * 768
    fake_cloud = AsyncMock()
    fake_cloud.embed.return_value = [9.9] * 768  # must NOT be called

    with patch.object(knowledge_service, "get_local_client", return_value=fake_local), \
         patch.object(knowledge_service, "get_cloud_client", return_value=fake_cloud):
        result = await knowledge_service.query_embedding("private research query")

    fake_local.embed.assert_awaited_once_with("private research query")
    fake_cloud.embed.assert_not_awaited()
    assert result == [0.0] * 768
```

- [ ] **Step 2: Run test to verify it fails**

```
docker compose exec backend pytest tests/test_leak_fixes.py::test_query_embedding_uses_local_client -v
```

Expected: FAIL with `AssertionError: Expected 'embed' to have been awaited once. Awaited 0 times.` (because today `query_embedding` calls `get_cloud_client()`).

- [ ] **Step 3: Commit the failing test**

```bash
git add backend/tests/test_leak_fixes.py
git commit -m "test(privacy): pin L-1 — knowledge query embed must use local client"
```

### Task 1.2: Fix L-1

**Files:**
- Modify: `backend/app/services/knowledge_service.py:30`

- [ ] **Step 1: Apply the one-line fix**

In `backend/app/services/knowledge_service.py`, change:

```python
async def query_embedding(query: str) -> List[float]:
    return await get_cloud_client().embed(query)
```

to:

```python
async def query_embedding(query: str) -> List[float]:
    # Embeddings are foundation ops — must stay local. See
    # docs/privacy/known-leaks.md#l-1.
    return await get_local_client().embed(query)
```

Also update the import line at the top of the file so `get_local_client` is available:

```python
from app.services.ai_client import get_local_client  # added
from app.services.ai_client import get_cloud_client  # leave for other callers in this file
```

- [ ] **Step 2: Run the regression test to verify it passes**

```
docker compose exec backend pytest tests/test_leak_fixes.py::test_query_embedding_uses_local_client -v
```

Expected: PASS.

- [ ] **Step 3: Run all knowledge service tests to confirm no regression**

```
docker compose exec backend pytest tests/test_knowledge_service.py tests/test_knowledge_extractor.py tests/test_knowledge_routes.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/knowledge_service.py
git commit -m "fix(privacy): L-1 — knowledge query embedding uses local client

Embeddings are a foundation operation; every other embedding call in
the codebase uses get_local_client(). This one line was the odd one
out and sent every knowledge-graph search query to the configured
cloud provider.

See docs/privacy/known-leaks.md#l-1."
```

### Task 1.3: Re-embed existing knowledge nodes (script)

Pre-existing knowledge-node embeddings were generated against the cloud model. Mixing local and cloud embeddings in the same column corrupts cosine similarity. This script rebuilds them.

**Files:**
- Create: `backend/scripts/reembed_knowledge_nodes.py`

- [ ] **Step 1: Write the script**

```python
"""One-off: re-embed every KnowledgeNode using the local AI client.

Run after L-1 fix landed. Required because mixing local + cloud
embeddings in the same pgvector column makes cosine similarity
meaningless.

Usage (inside the backend container):
    python scripts/reembed_knowledge_nodes.py [--batch-size N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.knowledge import KnowledgeNode
from app.services.ai_client import get_local_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reembed")


async def _process_batch(db: AsyncSession, nodes: List[KnowledgeNode], dry_run: bool) -> int:
    ai = get_local_client()
    updated = 0
    for node in nodes:
        embed_text = f"{node.title}\n\n{node.content or ''}"[:8000]
        try:
            vec = await ai.embed(embed_text)
        except Exception:
            log.exception("embed failed for node %s; skipping", node.id)
            continue
        if not dry_run:
            node.embedding = vec
        updated += 1
    if not dry_run:
        await db.commit()
    return updated


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = 0
    async with async_session_maker() as db:
        result = await db.execute(select(KnowledgeNode).where(KnowledgeNode.archived == False))
        all_nodes = list(result.scalars().all())
        log.info("found %d nodes to re-embed", len(all_nodes))

        for i in range(0, len(all_nodes), args.batch_size):
            batch = all_nodes[i:i + args.batch_size]
            updated = await _process_batch(db, batch, args.dry_run)
            total += updated
            log.info("batch %d-%d: %d updated", i, i + len(batch), updated)

    log.info("done. updated %d nodes (dry_run=%s)", total, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Verify the script imports and dry-run works**

```
docker compose exec backend python scripts/reembed_knowledge_nodes.py --dry-run --batch-size 10
```

Expected: script runs without exception, logs `found N nodes to re-embed`, `done. updated N nodes (dry_run=True)`.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/reembed_knowledge_nodes.py
git commit -m "chore(privacy): re-embed script for knowledge nodes after L-1 fix

One-off maintenance script. Mixing cloud + local embeddings in the
same pgvector column corrupts cosine similarity, so any existing
nodes need a one-time refresh."
```

### Task 1.4: Regression test for L-2 (no direct OpenAIClient outside ai_client.py)

**Files:**
- Modify: `backend/tests/test_leak_fixes.py`

- [ ] **Step 1: Append the structural test**

```python
import importlib
import inspect
from pathlib import Path


def test_no_direct_openai_client_instantiation_outside_ai_client():
    """L-2: only ai_client.py may instantiate OpenAIClient directly.

    Any other call site bypasses the CLOUD_AI_PROVIDER router and
    sends data to OpenAI even when the user picked a different
    provider. The allowed exceptions are gated paper-reviewer paths
    that route through get_paper_reviewer_client() helpers.
    """
    services_dir = Path(__file__).parent.parent / "app" / "services"
    capabilities_dir = Path(__file__).parent.parent / "app" / "capabilities"

    offenders: list[str] = []
    for root in (services_dir, capabilities_dir):
        for path in root.rglob("*.py"):
            if path.name == "ai_client.py":
                continue  # the definition file is allowed
            text = path.read_text()
            # Direct instantiation: OpenAIClient(  (call syntax)
            if "OpenAIClient(" in text:
                # Allow it only inside a function named *_paper_reviewer_client
                # — that's the explicit, gated path. Otherwise it's a leak.
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if "OpenAIClient(" in line and "_paper_reviewer_client" not in text[max(0, text.find(line) - 200):text.find(line)]:
                        offenders.append(f"{path.relative_to(services_dir.parent.parent)}:{line_no}: {line.strip()}")

    assert not offenders, (
        "Direct OpenAIClient() instantiation found outside the gated paper-reviewer "
        "helper. These bypass CLOUD_AI_PROVIDER and leak to OpenAI. Move to "
        "get_cloud_client() or the gated _paper_reviewer_client():\n  "
        + "\n  ".join(offenders)
    )
```

- [ ] **Step 2: Run and confirm it fails (lists the current 4 offenders)**

```
docker compose exec backend pytest tests/test_leak_fixes.py::test_no_direct_openai_client_instantiation_outside_ai_client -v
```

Expected: FAIL, output names `agents.py`, `agentic_generation.py`, `paper_reviewers.py`, `paper_service.py`.

- [ ] **Step 3: Commit the test**

```bash
git add backend/tests/test_leak_fixes.py
git commit -m "test(privacy): pin L-2 — no direct OpenAIClient outside ai_client.py"
```

### Task 1.5: Add `paper_reviewer_providers` setting

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add the setting**

Find the `Settings` class in `backend/app/config.py` and add (near the other AI provider settings):

```python
    # Explicit list of providers the paper-reviewer roundtable is allowed
    # to call directly. Bypasses CLOUD_AI_PROVIDER so the roundtable can
    # use multi-provider critique diversity (the deliberate design intent).
    # Empty list = roundtable uses only get_cloud_client().
    # See docs/privacy/known-leaks.md#l-2.
    paper_reviewer_providers: List[str] = []
```

If `List` is not already imported at the top of `config.py`, add `from typing import List`.

- [ ] **Step 2: Verify config loads**

```
docker compose exec backend python -c "from app.config import settings; print(settings.paper_reviewer_providers)"
```

Expected: `[]`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(privacy): add paper_reviewer_providers setting

Empty by default. When non-empty, paper_reviewers and paper_service
may call providers in the list directly. Replaces the implicit
'if OPENAI_API_KEY set' check that bypassed CLOUD_AI_PROVIDER."
```

### Task 1.6: Add gated `_paper_reviewer_client()` helper

**Files:**
- Modify: `backend/app/services/ai_client.py`

- [ ] **Step 1: Append the helper to ai_client.py**

At the bottom of `backend/app/services/ai_client.py`, after `get_ai_client()`:

```python
def get_paper_reviewer_client(provider: str) -> AIClient:
    """Explicit, gated cloud client for the paper-reviewer roundtable.

    The paper-reviewer surface is the one place where multi-provider
    diversity is structural (see docs/privacy/capability-matrix.md
    rows 24-26). This helper grants access to a specific provider only
    if it's in settings.paper_reviewer_providers — otherwise returns
    the configured cloud client, transparently degrading.
    """
    allowed = settings.paper_reviewer_providers
    if provider not in allowed:
        return get_cloud_client()
    return _build_client(provider)
```

- [ ] **Step 2: Quick smoke check**

```
docker compose exec backend python -c "
from app.services.ai_client import get_paper_reviewer_client
print(type(get_paper_reviewer_client('openai')).__name__)
"
```

Expected: `OpenAIClient` if `openai` is in `paper_reviewer_providers` (default empty → falls back to cloud), otherwise whatever the configured cloud provider is.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/ai_client.py
git commit -m "feat(privacy): add gated get_paper_reviewer_client(provider) helper

Single entry point for the deliberately-multi-provider paper-reviewer
roundtable. Honors settings.paper_reviewer_providers — any provider
not in the list silently falls back to the configured cloud client."
```

### Task 1.7: Fix L-2 in `agents.py` and `agentic_generation.py`

These files use `OpenAIClient()` for non-paper reasons. Per L-2 analysis, those are accidental — should route through `get_cloud_client()`.

**Files:**
- Modify: `backend/app/services/agents.py:21,199-200`
- Modify: `backend/app/services/agentic_generation.py:29,59`

- [ ] **Step 1: Edit `agents.py`**

Change the import line near the top (currently `from app.services.ai_client import OpenAIClient, get_cloud_client, get_local_client`) to:

```python
from app.services.ai_client import get_cloud_client, get_local_client
```

Find `cloud = get_cloud_client()` around line 199. Confirm the block does not also instantiate `OpenAIClient()` elsewhere; remove any such line.

- [ ] **Step 2: Edit `agentic_generation.py`**

Change the import:

```python
from app.services.ai_client import get_cloud_client, get_local_client
```

Find the line `_reviewer_client = OpenAIClient()` (around line 59) and replace with:

```python
_reviewer_client = get_cloud_client()
```

- [ ] **Step 3: Run the L-2 regression test**

```
docker compose exec backend pytest tests/test_leak_fixes.py::test_no_direct_openai_client_instantiation_outside_ai_client -v
```

Expected: now lists only `paper_reviewers.py` and `paper_service.py` (the two legitimate paper-reviewer paths).

- [ ] **Step 4: Run agentic and chat tests**

```
docker compose exec backend pytest tests/test_paper_pipeline_v2.py tests/test_endpoints.py -v -k "agentic or chat or advisor"
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents.py backend/app/services/agentic_generation.py
git commit -m "fix(privacy): L-2 (1/2) — route agents.py and agentic_generation.py through cloud client

Both files instantiated OpenAIClient() directly, bypassing
CLOUD_AI_PROVIDER. The diversity rationale that legitimises the
direct call in paper_reviewers does not apply here — these calls
should follow the configured provider.

See docs/privacy/known-leaks.md#l-2."
```

### Task 1.8: Fix L-2 in `paper_reviewers.py` and `paper_service.py`

These have a legitimate multi-provider intent — route them through the new gated helper.

**Files:**
- Modify: `backend/app/services/paper_reviewers.py:23,200-203`
- Modify: `backend/app/services/paper_service.py:35`

- [ ] **Step 1: Edit `paper_reviewers.py`**

Change the import:

```python
from app.services.ai_client import get_cloud_client, get_paper_reviewer_client
```

Find the block around line 200:

```python
cloud = get_cloud_client()
if settings.openai_api_key:
    openai_client: Any = OpenAIClient()
else:
    openai_client = cloud
```

Replace with:

```python
cloud = get_cloud_client()
openai_client: Any = get_paper_reviewer_client("openai")
```

- [ ] **Step 2: Edit `paper_service.py`**

Same import change. Find any `OpenAIClient()` instantiation and replace with `get_paper_reviewer_client("openai")` if it's the reviewer path, or `get_cloud_client()` if it's the writer/reviser.

- [ ] **Step 3: Run the L-2 regression test**

```
docker compose exec backend pytest tests/test_leak_fixes.py::test_no_direct_openai_client_instantiation_outside_ai_client -v
```

Expected: PASS.

- [ ] **Step 4: Run paper pipeline tests**

```
docker compose exec backend pytest tests/test_paper_pipeline_v2.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_reviewers.py backend/app/services/paper_service.py
git commit -m "fix(privacy): L-2 (2/2) — gate paper-reviewer OpenAI behind setting

paper_reviewers and paper_service now use get_paper_reviewer_client(),
which only returns the requested provider when settings.paper_reviewer_providers
allows it. Default behaviour is unchanged for users with OPENAI_API_KEY
configured AND 'openai' in the provider list; everyone else gets
silent fallback to get_cloud_client().

See docs/privacy/known-leaks.md#l-2."
```

---

## Phase 2 — W2: `record_egress` instrumentation

### Task 2.1: Alembic migration for `egress_logs`

**Files:**
- Create: `backend/alembic/versions/0022_privacy_foundation.py`

- [ ] **Step 1: Write the migration**

```python
"""privacy foundation: egress_logs + projects.privacy_default

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. egress_logs — one row per cloud egress call
    op.create_table(
        "egress_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("surface", sa.String(64), nullable=False, index=True),
        sa.Column("service", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("fields", JSONB, nullable=False),
        sa.Column("redaction", JSONB, nullable=True),
        sa.Column("tokens_estimated", sa.Integer, nullable=True),
        sa.Column("total_bytes", sa.Integer, nullable=False),
    )
    op.create_index("ix_egress_logs_user_ts", "egress_logs", ["user_id", "ts"])

    # 2. projects.privacy_default — 'open' | 'strict'
    op.add_column(
        "projects",
        sa.Column("privacy_default", sa.String(16), nullable=False, server_default="open"),
    )


def downgrade() -> None:
    op.drop_column("projects", "privacy_default")
    op.drop_index("ix_egress_logs_user_ts", table_name="egress_logs")
    op.drop_table("egress_logs")
```

- [ ] **Step 2: Run the migration**

```
docker compose exec backend alembic upgrade head
```

Expected: `Running upgrade 0021 -> 0022, privacy foundation`.

- [ ] **Step 3: Verify the schema**

```
docker compose exec db psql -U postgres -d pr_secretary -c "\d egress_logs" -c "\d projects"
```

Expected: `egress_logs` exists with all columns; `projects.privacy_default` exists with default `open`.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0022_privacy_foundation.py
git commit -m "feat(privacy): migration — egress_logs + projects.privacy_default"
```

### Task 2.2: `EgressLog` model

**Files:**
- Create: `backend/app/models/egress_log.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the model**

```python
"""SQLAlchemy model for egress_logs. One row per cloud-egress AI call.

See docs/privacy/measurement-and-redaction.md#part-1--measurement for
the shape of the `fields` and `redaction` JSONB columns.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EgressLog(Base):
    __tablename__ = "egress_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    surface: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    redaction: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tokens_estimated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
```

- [ ] **Step 2: Register in models/__init__.py**

Open `backend/app/models/__init__.py`. After the existing model imports, add:

```python
from app.models.egress_log import EgressLog  # noqa: F401
```

Add `"EgressLog"` to the `__all__` list.

- [ ] **Step 3: Verify import**

```
docker compose exec backend python -c "from app.models import EgressLog; print(EgressLog.__tablename__)"
```

Expected: `egress_logs`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/egress_log.py backend/app/models/__init__.py
git commit -m "feat(privacy): EgressLog model"
```

### Task 2.3: `EgressRecorder` context manager

**Files:**
- Create: `backend/app/services/egress_recorder.py`
- Test: `backend/tests/test_egress_recorder.py`

- [ ] **Step 1: Write the failing test**

```python
"""EgressRecorder records per-call field byte breakdown + redaction
summary, emits a TUI event, and persists a row to egress_logs."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.services.egress_recorder import EgressRecorder, RedactionSummary


@pytest.mark.asyncio
async def test_recorder_records_field_bytes_and_total(monkeypatch):
    written: list = []

    async def fake_persist(rec_payload):
        written.append(rec_payload)

    monkeypatch.setattr("app.services.egress_recorder._persist", fake_persist)

    async with EgressRecorder(
        surface="paper",
        service="paper_service.generate_paper",
        provider="gemini",
        model="gemini-2.0-flash",
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    ) as rec:
        rec.field("paper_body", "hello world")  # 11 bytes
        rec.field("venue", "ICML 2026")          # 9 bytes
        rec.redaction_summary(RedactionSummary(
            spans_replaced=2, bytes_replaced=42, categories={"name": 2}
        ))

    assert len(written) == 1
    payload = written[0]
    assert payload["surface"] == "paper"
    assert payload["fields"]["paper_body"] == 11
    assert payload["fields"]["venue"] == 9
    assert payload["total_bytes"] == 20
    assert payload["redaction"]["spans_replaced"] == 2
```

- [ ] **Step 2: Run to verify it fails**

```
docker compose exec backend pytest tests/test_egress_recorder.py -v
```

Expected: FAIL with `ImportError: cannot import name 'EgressRecorder'`.

- [ ] **Step 3: Implement the recorder**

Create `backend/app/services/egress_recorder.py`:

```python
"""EgressRecorder — context manager that records per-call cloud-egress.

Usage:
    async with EgressRecorder(
        surface="paper", service="paper_service.generate_paper",
        provider="gemini", model=settings.gemini_chat_model,
        user_id=user_id, project_id=project_id,
    ) as rec:
        rec.field("paper_body", body_text)
        rec.field("venue", venue_text)
        rec.redaction_summary(redaction)
        result = await ai.complete(system, user)

The recorder emits a `data.egress` event to the bench TUI on exit
and persists one row to egress_logs.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.database import async_session_maker
from app.models.egress_log import EgressLog
from app.services.event_stream import emit

logger = logging.getLogger(__name__)


@dataclass
class RedactionSummary:
    spans_replaced: int = 0
    bytes_replaced: int = 0
    categories: Dict[str, int] = field(default_factory=dict)
    entries_stubbed: int = 0


class EgressRecorder:
    def __init__(
        self,
        surface: str,
        service: str,
        provider: str,
        model: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> None:
        self.surface = surface
        self.service = service
        self.provider = provider
        self.model = model
        self.user_id = user_id
        self.project_id = project_id
        self._fields: Dict[str, int] = {}
        self._redaction: Optional[RedactionSummary] = None
        self._tokens_estimated: Optional[int] = None

    def field(self, name: str, payload: str) -> None:
        """Record one named field of the egress payload."""
        self._fields[name] = self._fields.get(name, 0) + len(payload.encode("utf-8"))

    def redaction_summary(self, summary: RedactionSummary) -> None:
        self._redaction = summary

    def tokens(self, n: int) -> None:
        self._tokens_estimated = n

    async def __aenter__(self) -> "EgressRecorder":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # We persist even on exception so failed cloud calls still appear
        # in the audit log (the user can see what we attempted to send).
        total_bytes = sum(self._fields.values())
        payload = {
            "ts": datetime.now(tz=timezone.utc),
            "surface": self.surface,
            "service": self.service,
            "provider": self.provider,
            "model": self.model,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "fields": dict(self._fields),
            "redaction": self._redaction.__dict__ if self._redaction else None,
            "tokens_estimated": self._tokens_estimated,
            "total_bytes": total_bytes,
        }
        try:
            await _persist(payload)
        except Exception:
            logger.exception("egress_recorder: persist failed (non-fatal)")
        try:
            redaction_blurb = ""
            if self._redaction:
                redaction_blurb = (
                    f" — {self._redaction.entries_stubbed} stubbed, "
                    f"{self._redaction.spans_replaced} spans replaced "
                    f"({self._redaction.bytes_replaced} B)"
                )
            emit(
                "info",
                "data.egress",
                f"{self.service} → {self.provider}: {total_bytes} B sent{redaction_blurb}",
                project_id=str(self.project_id) if self.project_id else None,
                meta={
                    "surface": self.surface,
                    "service": self.service,
                    "provider": self.provider,
                    "model": self.model,
                    "fields": dict(self._fields),
                    "redaction": self._redaction.__dict__ if self._redaction else None,
                    "total_bytes": total_bytes,
                },
            )
        except Exception:
            logger.exception("egress_recorder: emit failed (non-fatal)")


async def _persist(payload: Dict[str, Any]) -> None:
    """Write one egress_logs row. Separated so tests can monkeypatch."""
    async with async_session_maker() as db:
        row = EgressLog(
            ts=payload["ts"],
            user_id=payload["user_id"],
            project_id=payload["project_id"],
            surface=payload["surface"],
            service=payload["service"],
            provider=payload["provider"],
            model=payload["model"],
            fields=payload["fields"],
            redaction=payload["redaction"],
            tokens_estimated=payload["tokens_estimated"],
            total_bytes=payload["total_bytes"],
        )
        db.add(row)
        await db.commit()
```

- [ ] **Step 4: Re-run the test**

```
docker compose exec backend pytest tests/test_egress_recorder.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/egress_recorder.py backend/tests/test_egress_recorder.py
git commit -m "feat(privacy): EgressRecorder context manager"
```

### Task 2.4: Wrap the 16 cloud egress sites

Apply the same instrumentation pattern at each cloud egress site listed in [`docs/privacy/egress-audit.md`](../../privacy/egress-audit.md). The pattern is the same per site; one task per site keeps commits small.

**The pattern (apply to each site below):**

```python
# BEFORE
ai = get_cloud_client()
result = await ai.complete(system, user)

# AFTER
ai = get_cloud_client()
async with EgressRecorder(
    surface="<surface>",                # paper / chat / worklog / etc.
    service="<module>.<fn>",            # paper_service.generate_paper
    provider=type(ai).__name__.lower().replace("client", ""),
    model=getattr(ai, "_model", None) or getattr(ai, "chat_model", None),
    user_id=user_id,                    # whatever's in scope
    project_id=project_id,              # whatever's in scope
) as rec:
    rec.field("system_prompt", system)
    rec.field("user_prompt", user)
    result = await ai.complete(system, user)
```

If `user_id` or `project_id` aren't in scope at the call site, pass `None`.

For each site, the `field()` calls should split the payload by *semantically meaningful chunk*, not just `system`/`user`. The chunk names are listed below per site so a row in `egress_logs` is meaningful when read later.

**Sites to wrap** (one commit per site; each commit message format: `feat(privacy): EG-NN — instrument <service>`):

| EG | File:Line | Surface | service= | field() chunks |
|---|---|---|---|---|
| EG-01 | `classifier_service.py:168` | `inbox` | `classifier_service.classify` | `system_prompt`, `project_catalogue`, `item_content` |
| EG-02 | `file_ingest_service.py:90` | `ingest` | `file_ingest_service.auto_tag` | `system_prompt`, `filename`, `mime_type`, `text_preview` |
| EG-03 | `knowledge_extractor.py:248`, `:304` | `knowledge` | `knowledge_extractor.extract_from_chat_turn` | `system_prompt`, `user_message`, `ai_message`, `history` |
| EG-04 | `worklog_service.py:277` | `worklog` | `worklog_service.generate_report` | `system_prompt`, `metrics`, `drafts`, `papers`, `goals` |
| EG-05 | `memory_service.py:455` | `wiki` | `memory_service.update_wiki_summary` | `system_prompt`, `context_blocks`, `previous_wiki` |
| EG-06 | `blog_service.py:194`, `ai_generation.py:173/246/311` | `drafts` | per call | `system_prompt`, `seed`, `memory_context`, `style_summary` |
| EG-07 | `agentic_generation.py:59,122` | `drafts` | `agentic_generation.run.writer` / `.reviewer` | `system_prompt`, `seed`, `memory_context` (writer); `system_prompt`, `writer_output` (reviewer) |
| EG-08 | `methods_drafter.py:163` | `paper` | `methods_drafter.draft` | `system_prompt`, `paper_section`, `context` |
| EG-08 | `diagram_service.py:204,286,447` | `diagram` | `diagram_service.<fn>` | `system_prompt`, `content_to_diagram` |
| EG-08 | `venue_service.py:203` | `publish` | `venue_service.suggest` | `system_prompt`, `project_profile` |
| EG-09 | `chat_service.py:463`, `advisors.py:152` | `roundtable` | `chat_service.send_to_advisors` / `advisors.route_to_advisors` | `system_prompt`, `history`, `user_message`, `workspace_context` (chat); `system_prompt`, `user_message` (router) |
| EG-10 | `research_service.py:420` | `research` | `research_service.send_message` | `system_prompt`, `lit_context`, `history`, `user_message` |
| EG-11 | `paper_service.py:464,876,1120` | `paper` | `paper_service.<fn>` | `system_prompt`, `paper_body`, `venue`, `additional_instructions` |
| EG-12 | `paper_reviewers.py:198,424` | `paper` | `paper_reviewers.<fn>` | `system_prompt`, `paper_content`, `venue_text` |
| EG-13 | `config_generator.py:275` | `onboarding` | `config_generator._generate_with_llm` | `system_prompt`, `wizard_answers` |
| EG-14 | (already local after L-1 fix — skip) | — | — | — |

Tasks 2.4.1 – 2.4.15 follow this template. Each is one ~5-minute task: add the imports, wrap the call, run the existing tests for that service, commit.

- [ ] **Subtasks 2.4.1 – 2.4.15**: one per site in the table above. See the pattern; each:
  - imports: `from app.services.egress_recorder import EgressRecorder`
  - wraps the existing `ai.complete()` call
  - splits the payload by the named chunks
  - runs the relevant service test (e.g., `pytest tests/test_<service>.py -v`)
  - commits with message `feat(privacy): EG-NN — instrument <service>`

### Task 2.5: `GET /api/v1/egress/recent` router

**Files:**
- Create: `backend/app/schemas/egress.py`
- Create: `backend/app/routers/egress.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_egress_router.py`

- [ ] **Step 1: Write the schema**

```python
"""Pydantic schemas for the egress audit router."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class EgressRecord(BaseModel):
    id: uuid.UUID
    ts: datetime
    project_id: Optional[uuid.UUID]
    surface: str
    service: str
    provider: str
    model: Optional[str]
    fields: Dict[str, int]
    redaction: Optional[Dict]
    total_bytes: int


class EgressRecentResponse(BaseModel):
    records: List[EgressRecord]
    total_bytes_today: int
```

- [ ] **Step 2: Write the failing router test**

```python
"""GET /api/v1/egress/recent returns last N records for the user."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.main import app
from app.models.egress_log import EgressLog
from app.database import async_session_maker


@pytest.mark.asyncio
async def test_egress_recent_returns_user_rows(auth_headers):
    # seed one row
    async with async_session_maker() as db:
        db.add(EgressLog(
            ts=datetime.now(tz=timezone.utc),
            user_id=auth_headers["user_id"],
            project_id=None,
            surface="paper",
            service="paper_service.generate_paper",
            provider="gemini",
            model="gemini-2.0-flash",
            fields={"paper_body": 1234},
            redaction=None,
            tokens_estimated=400,
            total_bytes=1234,
        ))
        await db.commit()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/v1/egress/recent", headers=auth_headers["headers"])

    assert r.status_code == 200
    body = r.json()
    assert any(rec["service"] == "paper_service.generate_paper" for rec in body["records"])
    assert body["total_bytes_today"] >= 1234
```

(Assumes a conftest `auth_headers` fixture exists — see `tests/conftest.py`. If the project name in the codebase is `auth_headers_factory` or similar, adapt.)

- [ ] **Step 3: Run to confirm it fails**

```
docker compose exec backend pytest tests/test_egress_router.py -v
```

Expected: FAIL (404 — route not wired).

- [ ] **Step 4: Implement the router**

```python
"""GET /api/v1/egress/recent — bench audit feed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_current_user_id
from app.models.egress_log import EgressLog
from app.schemas.egress import EgressRecentResponse, EgressRecord

router = APIRouter(prefix="/egress", tags=["egress"])


@router.get("/recent", response_model=EgressRecentResponse)
async def recent(
    limit: int = Query(50, ge=1, le=500),
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(EgressLog)
        .where(EgressLog.user_id == user_id)
        .order_by(EgressLog.ts.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    start_of_day = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total_today = await db.scalar(
        select(func.coalesce(func.sum(EgressLog.total_bytes), 0))
        .where(EgressLog.user_id == user_id)
        .where(EgressLog.ts >= start_of_day)
    )
    return EgressRecentResponse(
        records=[EgressRecord(
            id=r.id, ts=r.ts, project_id=r.project_id, surface=r.surface,
            service=r.service, provider=r.provider, model=r.model,
            fields=r.fields, redaction=r.redaction, total_bytes=r.total_bytes,
        ) for r in rows],
        total_bytes_today=int(total_today or 0),
    )
```

- [ ] **Step 5: Wire the router in main.py**

In `backend/app/main.py`, find where other routers are included (a block of `app.include_router(...)` calls). Add:

```python
from app.routers import egress
...
app.include_router(egress.router, prefix="/api/v1")
```

- [ ] **Step 6: Run the test**

```
docker compose exec backend pytest tests/test_egress_router.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/egress.py backend/app/routers/egress.py backend/app/main.py backend/tests/test_egress_router.py
git commit -m "feat(privacy): GET /api/v1/egress/recent — bench audit feed"
```

---

## Phase 3 — W3: `privacy:*` tag namespace

### Task 3.1: Tag constants module

**Files:**
- Create: `backend/app/services/privacy_tags.py`
- Test: `backend/tests/test_privacy_tags.py`

- [ ] **Step 1: Write the failing test**

```python
"""Reserved privacy:* tag namespace + resolution helpers."""
from __future__ import annotations

import pytest

from app.services.privacy_tags import (
    LOCAL_ONLY, REDACT_CONTENT, REDACT_VALUES, PUBLIC,
    resolve_policy, PrivacyPolicy,
)


def test_explicit_tag_wins_over_project_default():
    policy = resolve_policy(
        entry_tags=["privacy:local-only", "topic:auth"],
        project_default="open",
    )
    assert policy is PrivacyPolicy.LOCAL_ONLY


def test_project_strict_default_applies_when_no_explicit_tag():
    policy = resolve_policy(
        entry_tags=["topic:auth"],
        project_default="strict",
    )
    assert policy is PrivacyPolicy.REDACT_CONTENT


def test_project_open_default_means_public():
    policy = resolve_policy(entry_tags=[], project_default="open")
    assert policy is PrivacyPolicy.PUBLIC


def test_public_tag_overrides_strict_default():
    policy = resolve_policy(
        entry_tags=["privacy:public"],
        project_default="strict",
    )
    assert policy is PrivacyPolicy.PUBLIC
```

- [ ] **Step 2: Run to verify it fails**

```
docker compose exec backend pytest tests/test_privacy_tags.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the module**

```python
"""Reserved privacy:* tag namespace and policy resolution.

The tag namespace lives on MemoryEntry.metadata_["tags"] (a list of
strings, populated by file ingest + manual tagging). Reserved values:

    privacy:local-only      — never reaches cloud; replaced by stub
    privacy:redact-content  — title + headers preserved; body redacted
    privacy:redact-values   — schema preserved; cells become placeholders
    privacy:public          — explicit override of any project default

Project.privacy_default ∈ {'open', 'strict'} applies when no explicit
privacy:* tag is present. 'strict' treats untagged entries as
redact-content; 'open' lets them through.

See docs/privacy/measurement-and-redaction.md.
"""
from __future__ import annotations

import enum
from typing import List, Optional


LOCAL_ONLY = "privacy:local-only"
REDACT_CONTENT = "privacy:redact-content"
REDACT_VALUES = "privacy:redact-values"
PUBLIC = "privacy:public"

_RESERVED = {LOCAL_ONLY, REDACT_CONTENT, REDACT_VALUES, PUBLIC}


class PrivacyPolicy(enum.Enum):
    LOCAL_ONLY = "local_only"
    REDACT_CONTENT = "redact_content"
    REDACT_VALUES = "redact_values"
    PUBLIC = "public"


_TAG_TO_POLICY = {
    LOCAL_ONLY: PrivacyPolicy.LOCAL_ONLY,
    REDACT_CONTENT: PrivacyPolicy.REDACT_CONTENT,
    REDACT_VALUES: PrivacyPolicy.REDACT_VALUES,
    PUBLIC: PrivacyPolicy.PUBLIC,
}


def resolve_policy(
    entry_tags: Optional[List[str]],
    project_default: str = "open",
) -> PrivacyPolicy:
    """Pick the effective policy for an entry.

    Explicit privacy:* tag wins. Otherwise: strict default → REDACT_CONTENT,
    open default → PUBLIC.
    """
    tags = entry_tags or []
    for tag in tags:
        if tag in _TAG_TO_POLICY:
            return _TAG_TO_POLICY[tag]
    if project_default == "strict":
        return PrivacyPolicy.REDACT_CONTENT
    return PrivacyPolicy.PUBLIC


def is_reserved(tag: str) -> bool:
    return tag in _RESERVED
```

- [ ] **Step 4: Re-run the test**

```
docker compose exec backend pytest tests/test_privacy_tags.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/privacy_tags.py backend/tests/test_privacy_tags.py
git commit -m "feat(privacy): privacy:* tag constants + resolve_policy()"
```

### Task 3.2: Tag propagation through file ingest

`file_ingest_service.ingest_file` already merges user-supplied tags into the memory entry. We need to make chunked / derived entries from the same file inherit the parent's `privacy:*` tag.

**Files:**
- Modify: `backend/app/services/file_ingest_service.py`
- Modify: `backend/tests/` (add a small test)

- [ ] **Step 1: Audit the current chunking path**

Open `backend/app/services/file_ingest_service.py`. Find where `add_entry` is called. Confirm whether the file is stored as one entry or multiple chunks. If single, no propagation work — just inherit naturally. If multiple, each derived entry must copy the privacy tag from the merged tag list.

- [ ] **Step 2: Write a propagation test**

Append to `backend/tests/test_leak_fixes.py` (or create a new `test_tag_propagation.py`):

```python
@pytest.mark.asyncio
async def test_ingest_propagates_privacy_tag_to_all_chunks(db_session):
    from app.services.file_ingest_service import ingest_file
    entry = await ingest_file(
        project_id=uuid.uuid4(),
        filename="results.csv",
        content_bytes=b"col_a,col_b\n1,2\n3,4\n",
        source="manual",
        mime_type="text/csv",
        user_tags=["privacy:local-only"],
        db=db_session,
    )
    tags = (entry.metadata_ or {}).get("tags", [])
    assert "privacy:local-only" in tags
```

- [ ] **Step 3: Run, observe pass/fail, fix if needed**

```
docker compose exec backend pytest tests/test_leak_fixes.py -k propagate -v
```

Expected: PASS today because `ingest_file` already merges user_tags. If FAIL (chunked path doesn't copy), copy the user_tags forward in the chunk loop.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_leak_fixes.py backend/app/services/file_ingest_service.py
git commit -m "test(privacy): pin tag propagation through file ingest"
```

### Task 3.3: API endpoints for entry tags + project default

**Files:**
- Modify: `backend/app/routers/memory.py` — add `PATCH /memory/{entry_id}/tags`
- Modify: `backend/app/routers/projects.py` — add `PATCH /projects/{project_id}/privacy-default`

- [ ] **Step 1: Add memory tags endpoint**

In `backend/app/routers/memory.py`, append:

```python
from app.services.privacy_tags import _RESERVED as PRIVACY_TAGS

class _TagsPatch(BaseModel):
    tags: List[str]


@router.patch("/{entry_id}/tags")
async def patch_tags(
    entry_id: uuid.UUID,
    body: _TagsPatch,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(MemoryEntry, entry_id)
    if entry is None:
        raise HTTPException(404, "memory entry not found")
    # privacy:* tags are mutually exclusive — dedup to last writer
    explicit_privacy = [t for t in body.tags if t in PRIVACY_TAGS]
    if len(explicit_privacy) > 1:
        body.tags = [t for t in body.tags if t not in PRIVACY_TAGS] + [explicit_privacy[-1]]
    md = dict(entry.metadata_ or {})
    md["tags"] = list(body.tags)
    entry.metadata_ = md
    await db.commit()
    return {"id": str(entry.id), "tags": md["tags"]}
```

(Imports / decorators may already exist — match the file's style.)

- [ ] **Step 2: Add project default endpoint**

In `backend/app/routers/projects.py`, append:

```python
class _PrivacyDefaultPatch(BaseModel):
    privacy_default: str  # 'open' | 'strict'


@router.patch("/{project_id}/privacy-default")
async def patch_privacy_default(
    project_id: uuid.UUID,
    body: _PrivacyDefaultPatch,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if body.privacy_default not in {"open", "strict"}:
        raise HTTPException(400, "privacy_default must be 'open' or 'strict'")
    project = await db.get(Project, project_id)
    if project is None or project.user_id != user_id:
        raise HTTPException(404, "project not found")
    project.privacy_default = body.privacy_default
    await db.commit()
    return {"id": str(project.id), "privacy_default": body.privacy_default}
```

- [ ] **Step 3: Smoke-test both endpoints**

```
docker compose exec backend pytest tests/test_endpoints.py -v -k "tags or privacy_default"
```

Expected: if no test exists yet, the run completes with 0 selected (acceptable for this task — UI workstream W9 adds e2e coverage). Manually verify with curl:

```
curl -X PATCH http://localhost:9000/api/v1/projects/<id>/privacy-default \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"privacy_default":"strict"}'
```

Expected: `{"id":"...","privacy_default":"strict"}`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/memory.py backend/app/routers/projects.py
git commit -m "feat(privacy): PATCH endpoints for memory tags + project privacy_default"
```

---

## Phase 4 — W4: Tag-resolving prompt assembler

### Task 4.1: Stub formatters

**Files:**
- Create: `backend/app/services/privacy_assembler.py`
- Test: `backend/tests/test_privacy_assembler.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tag-resolving prompt assembler — turns memory entries into stubs."""
from __future__ import annotations

import uuid

import pytest

from app.models.memory import MemoryEntry
from app.services.privacy_tags import LOCAL_ONLY, REDACT_CONTENT
from app.services.privacy_assembler import assemble_context


def _entry(content: str, tags=None, entry_type="narrative_fact", filename=None) -> MemoryEntry:
    md = {"tags": list(tags or [])}
    if filename:
        md["filename"] = filename
    return MemoryEntry(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        entry_type=entry_type,
        content=content,
        metadata_=md,
    )


def test_local_only_entry_is_replaced_with_stub():
    e = _entry("87.3% accuracy on private corpus", tags=[LOCAL_ONLY], filename="results.csv")
    out, summary = assemble_context([e], project_default="open")

    assert "87.3%" not in out
    assert "not sent to cloud" in out
    assert "results.csv" in out
    assert summary.entries_stubbed == 1


def test_redact_content_entry_keeps_type_and_filename_drops_body():
    e = _entry("secret body text", tags=[REDACT_CONTENT], filename="methods.md")
    out, summary = assemble_context([e], project_default="open")

    assert "secret body text" not in out
    assert "methods.md" in out
    assert "body redacted" in out


def test_public_entry_is_emitted_verbatim():
    e = _entry("This is public note content.", tags=[])
    out, summary = assemble_context([e], project_default="open")

    assert "This is public note content." in out
    assert summary.entries_stubbed == 0


def test_strict_default_applies_to_untagged_entry():
    e = _entry("body content", tags=[])
    out, summary = assemble_context([e], project_default="strict")

    assert "body content" not in out
    assert "body redacted" in out
```

- [ ] **Step 2: Run to verify it fails**

```
docker compose exec backend pytest tests/test_privacy_assembler.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the assembler**

```python
"""Tag-resolving prompt assembler.

Given a list of MemoryEntry + the project's privacy_default, return:
  - one assembled context string with privacy stubs for tagged entries
  - a RedactionSummary recording what was replaced

Callers wrap their cloud-prompt construction with assemble_context()
and feed the result into get_cloud_client().complete(). Tagged content
never reaches the cloud.

See docs/privacy/measurement-and-redaction.md#part-2a-tag-based-file-entry-redaction-primary.
"""
from __future__ import annotations

from typing import List, Tuple

from app.models.memory import MemoryEntry
from app.services.egress_recorder import RedactionSummary
from app.services.privacy_tags import PrivacyPolicy, resolve_policy


def _filename_of(entry: MemoryEntry) -> str:
    md = entry.metadata_ or {}
    return md.get("filename") or entry.entry_type


def _structural_hint(entry: MemoryEntry) -> str:
    """One-line shape hint for a stub: row × col counts, page counts, etc."""
    md = entry.metadata_ or {}
    if "shape" in md:
        return md["shape"]
    if entry.entry_type == "file":
        size_bytes = md.get("size_bytes")
        if size_bytes:
            return f"{size_bytes} bytes"
    return ""


def _stub_local_only(entry: MemoryEntry) -> str:
    fn = _filename_of(entry)
    hint = _structural_hint(entry)
    hint_part = f" — {hint}" if hint else ""
    return f"[private — {entry.entry_type} — {fn}{hint_part} — not sent to cloud]"


def _stub_redact_content(entry: MemoryEntry) -> str:
    fn = _filename_of(entry)
    # Keep the first 80 chars as a title-ish hint
    snippet = (entry.content or "").splitlines()[0][:80] if entry.content else ""
    return f"[partial — {entry.entry_type} — {fn} — \"{snippet}\" — body redacted]"


def assemble_context(
    entries: List[MemoryEntry],
    project_default: str = "open",
) -> Tuple[str, RedactionSummary]:
    """Assemble a privacy-aware context string from the given entries.

    Returns:
      (context_string, redaction_summary)
    """
    parts: List[str] = []
    summary = RedactionSummary()

    for entry in entries:
        tags = (entry.metadata_ or {}).get("tags") or []
        policy = resolve_policy(tags, project_default=project_default)

        if policy is PrivacyPolicy.LOCAL_ONLY:
            parts.append(_stub_local_only(entry))
            summary.entries_stubbed += 1
            summary.bytes_replaced += len((entry.content or "").encode("utf-8"))
        elif policy is PrivacyPolicy.REDACT_CONTENT:
            parts.append(_stub_redact_content(entry))
            summary.entries_stubbed += 1
            summary.bytes_replaced += len((entry.content or "").encode("utf-8"))
        elif policy is PrivacyPolicy.REDACT_VALUES:
            # v1: treat as redact-content. True table-cell redaction is a
            # later refinement once we have parsed tabular data in memory.
            parts.append(_stub_redact_content(entry))
            summary.entries_stubbed += 1
            summary.bytes_replaced += len((entry.content or "").encode("utf-8"))
        else:  # PUBLIC
            parts.append(entry.content or "")

    return "\n\n".join(parts), summary
```

- [ ] **Step 4: Re-run the tests**

```
docker compose exec backend pytest tests/test_privacy_assembler.py -v
```

Expected: PASS (all 4 cases).

- [ ] **Step 5: Add a stub-bytes property test**

Append to `tests/test_privacy_assembler.py`:

```python
def test_no_tagged_bytes_leak_into_output():
    """For every LOCAL_ONLY / REDACT_CONTENT entry, no substring of the
    original content of length >= 8 may appear in the output."""
    sensitive = "verylongsecretvalue123456789"
    e = _entry(sensitive, tags=[LOCAL_ONLY])
    out, _ = assemble_context([e], project_default="open")
    for n in range(8, len(sensitive) + 1):
        for i in range(0, len(sensitive) - n + 1):
            chunk = sensitive[i:i + n]
            assert chunk not in out, f"sensitive chunk {chunk!r} leaked into output"
```

- [ ] **Step 6: Run the property test**

```
docker compose exec backend pytest tests/test_privacy_assembler.py::test_no_tagged_bytes_leak_into_output -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/privacy_assembler.py backend/tests/test_privacy_assembler.py
git commit -m "feat(privacy): privacy_assembler.assemble_context() + stub formatters

Pure function. Given memory entries + project default, returns an
assembled context string with stubs replacing privacy:local-only and
privacy:redact-content entries, plus a RedactionSummary for the
EgressRecorder.

Property test verifies no 8+ char substring of tagged content
leaks into the output."
```

---

## Final integration check

### Task 5.1: End-to-end smoke

- [ ] **Step 1: Bring backend up cleanly**

```
docker compose up --build -d backend && docker compose logs backend --tail 40
```

Expected: starts without error; `alembic upgrade head` ran during boot or has been run manually.

- [ ] **Step 2: Run the full backend test suite**

```
docker compose exec backend pytest tests/ -v --tb=short
```

Expected: all tests pass. New tests added in this plan:
- `test_leak_fixes.py` (L-1 regression + L-2 structural)
- `test_egress_recorder.py`
- `test_egress_router.py`
- `test_privacy_tags.py`
- `test_privacy_assembler.py`

Existing tests must not regress.

- [ ] **Step 3: Hand-verify the audit endpoint**

```bash
curl http://localhost:9000/api/v1/egress/recent \
  -H "X-API-Key: $API_KEY" | jq .
```

Expected: `{"records":[],"total_bytes_today":0}` if no cloud calls have run, or actual records if they have.

- [ ] **Step 4: Hand-verify TUI event**

In another shell, subscribe to the events SSE feed:

```
curl -N http://localhost:9000/api/v1/events/stream -H "X-API-Key: $API_KEY"
```

In a browser, trigger a generation (e.g., /drafts) and watch for a `data.egress` event in the stream.

Expected: one line like `data: {"level":"info","source":"data.egress","summary":"<service> → gemini: <N> B sent",...}`.

- [ ] **Step 5: Performance bar check**

Measure the overhead added by `EgressRecorder` + `assemble_context()` on a representative surface (worklog). Compare before/after by running the worklog generation 5x with and without the recorder enabled (use a feature flag at the call site temporarily). Median wall-clock added must be < 50 ms per call.

- [ ] **Step 6: Code-review subagent pass**

Dispatch a `code-reviewer` subagent on the diff between this branch's base and HEAD:

```
git log --oneline main..HEAD
```

Pass the diff to the code-reviewer subagent and ask for the standard review: correctness, privacy contract upheld, no leaks introduced.

- [ ] **Step 7: Final commit if reviewer found anything**

Address any findings, then:

```bash
git commit -m "fix(privacy): address code-reviewer findings from foundation pass"
```

### Task 5.2: Mark plan complete

- [ ] **Step 1: Update the spec's status**

In `docs/superpowers/specs/2026-05-28-privacy-prototype-design.md`, change:

```markdown
**Status:** Draft (brainstorming) — pending user review
```

to:

```markdown
**Status:** Foundation landed 2026-MM-DD. Plans 2-7 (W5-W10) pending.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-28-privacy-prototype-design.md
git commit -m "docs(privacy): mark foundation as landed"
```

---

## Self-review checklist (for the executing engineer)

Before marking the plan done:

- [ ] All four standards from the spec satisfied:
  - [ ] Unit + integration tests per task
  - [ ] Code-reviewer subagent pass on the whole plan
  - [ ] Manual end-to-end verified (egress endpoint + TUI event)
  - [ ] Performance: < 50 ms added per surface
- [ ] No new file > 400 lines (matrix exceeded → split it)
- [ ] No direct `OpenAIClient()` outside `ai_client.py` (the L-2 regression test still passes)
- [ ] No `get_cloud_client().embed(...)` anywhere (the L-1 regression test still passes)
- [ ] `egress_logs` has rows after exercising any surface
- [ ] TUI emits `data.egress` events on every cloud call
- [ ] `privacy:local-only` entry never appears in any assembled prompt (property test passes)
