# DataMaster Capability Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an opt-in Phase-2 `slash_command` capability `/run_data_experiment` that runs SJTU DataMaster in an isolated sidecar, grounds the task in the project knowledge graph, streams the trajectory into the bench TUI log, and lands an `Experiment` knowledge node linked to the nodes that seeded it.

**Architecture:** WorkspaceOS stays the workbench. A new pure-data extension declares the slash command. The trigger handler validates input, assembles a brief from the KG, persists a job row, and spawns a background task that submits the job to an external sidecar over a small HTTP contract, relays its SSE trajectory into the existing `event_stream.emit` bench log, and on completion writes an `Experiment` node + `derived_from` edges. The heavy agent never runs in the backend container.

**Tech Stack:** Python 3.9 (FastAPI, SQLAlchemy async, Alembic, httpx 0.27, pytest/pytest-asyncio), Next.js 16 + Tailwind v4 (frontend dialog), YAML extension manifest.

**Spec:** `docs/superpowers/specs/2026-05-18-datamaster-capability-design.md`

**Conventions (from CLAUDE.md — non-negotiable):**
- Python 3.9 typing: `Optional[X]`, `List[X]`, `Dict[K,V]` from `typing` — never `X | None`.
- Minimal diffs. Follow patterns in adjacent files. Don't rename public APIs.
- All KG reads/writes scoped by `user_id`. Never log secrets.
- Tests must pass before committing.
- Stage specific files, not `git add -A`. End commit messages with the Co-Authored-By trailer used in this repo's history.
- Frontend ONLY: before writing any frontend code, read the relevant guide under `frontend/node_modules/next/dist/docs/` (Next.js in this repo has breaking changes vs. training data — see `frontend/AGENTS.md`).

**Run tests with:** `docker compose exec backend bash -c "cd /app && python -m pytest <path> -v"` (HTTP-contract tests need `docker compose up -d backend`; pure-unit and `db_session` tests do not need the HTTP server but do need the DB container).

---

### Task 1: Extension manifest (pure data) + sidecar_token redaction

**Files:**
- Create: `config/extensions/datamaster/manifest.yaml`
- Modify: `backend/app/services/capability_settings_service.py:37-40` (add `sidecar_token` to `SENSITIVE_KEYS`)
- Test: `backend/tests/test_datamaster_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_datamaster_manifest.py
"""DataMaster extension manifest is well-formed and discoverable."""
from app.services import extensions as ext_service
from app.services.capability_settings_service import SENSITIVE_KEYS


def test_datamaster_extension_loads_with_slash_capability():
    exts = {e.manifest.id: e for e in ext_service.get_all_extensions()}
    assert "datamaster" in exts, "datamaster extension not loaded"
    caps = exts["datamaster"].manifest.capabilities
    cap = next((c for c in caps if c.name == "run_data_experiment"), None)
    assert cap is not None, "run_data_experiment capability missing"
    assert cap.kind == "slash_command"
    cfg = cap.config or {}
    assert cfg.get("handler_kind") == "api_call"
    assert cfg.get("handler_target") == "/capabilities/runners/run_data_experiment/trigger"
    assert cfg.get("sidecar_base_url")
    assert isinstance(cfg.get("inputs"), list) and len(cfg["inputs"]) >= 2
    field_names = {f["name"] for f in cfg["inputs"]}
    assert {"objective", "dataset_ref"}.issubset(field_names)


def test_sidecar_token_is_sensitive():
    assert "sidecar_token" in SENSITIVE_KEYS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_manifest.py -v"`
Expected: FAIL — `"datamaster" not in exts` and `"sidecar_token" not in SENSITIVE_KEYS`.

- [ ] **Step 3: Create the manifest**

```yaml
# config/extensions/datamaster/manifest.yaml
id: datamaster
name: DataMaster Data Experiment
description: |
  Runs SJTU DataMaster's data-centric DataTree search as an isolated
  sidecar service. Grounds the task in the current project's knowledge
  graph (open Experiments, Claims, paper references), streams the
  trajectory into the bench TUI log, and lands the result as an
  Experiment node linked to the nodes that seeded it. Opt-in: enable
  and point sidecar_base_url at a running DataMaster sidecar in
  Settings. No framework code runs in the WorkspaceOS backend.
version: 0.1.0
author: workspaceos

matches:
  domain_keywords: []   # opt-in only — user enables via Settings

capabilities:
  - kind: slash_command
    name: run_data_experiment
    description: |
      Run a DataMaster data-pipeline search for the current project,
      grounded in the knowledge graph. Result becomes an Experiment node.
    config:
      label: "Run DataMaster experiment"
      keywords: [datamaster, data experiment, pipeline search, run datamaster]
      icon: "flask-conical"
      handler_kind: api_call
      handler_target: "/capabilities/runners/run_data_experiment/trigger"
      sidecar_base_url: "http://datamaster:8800"
      sidecar_token: ""
      default_max_minutes: 30
      allowed_dataset_root: ""
      inputs:
        - name: objective
          label: "Objective"
          type: textarea
          required: true
          placeholder: "e.g. improve validation AUC by finding better feature transforms"
        - name: dataset_ref
          label: "Dataset"
          type: text
          required: true
          placeholder: "hf:org/name  or  /projects/<allowed path>"
        - name: max_minutes
          label: "Max minutes"
          type: number
          required: false
          placeholder: "30"
```

- [ ] **Step 4: Add `sidecar_token` to SENSITIVE_KEYS**

In `backend/app/services/capability_settings_service.py`, change the `SENSITIVE_KEYS` set (currently lines 37-40):

```python
SENSITIVE_KEYS: Set[str] = {
    "api_key", "api_token", "token", "access_token", "password",
    "secret", "client_secret", "sidecar_token",
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_manifest.py -v"`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add config/extensions/datamaster/manifest.yaml backend/app/services/capability_settings_service.py backend/tests/test_datamaster_manifest.py
git commit -m "$(cat <<'EOF'
feat(datamaster F1): extension manifest + sidecar_token redaction

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Job model + Alembic migration 0021

**Files:**
- Create: `backend/app/models/data_experiment.py`
- Create: `backend/alembic/versions/0021_data_experiment_jobs.py`
- Modify: `backend/app/models/__init__.py` (register model import if that file aggregates models — verify first; if models are imported elsewhere follow that pattern)
- Test: `backend/tests/test_data_experiment_model.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_data_experiment_model.py
import uuid
import pytest
from sqlalchemy import select
from app.models.data_experiment import DataExperimentJob


@pytest.mark.asyncio
async def test_data_experiment_job_roundtrip(db_session, sample_user, sample_project):
    job = DataExperimentJob(
        user_id=sample_user.id,
        project_id=sample_project.id,
        sidecar_job_id="sc-123",
        objective="improve AUC",
        dataset_ref="hf:acme/widgets",
        status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.id is not None
    assert job.status == "queued"
    assert job.score is None
    assert job.result_node_id is None

    got = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert got.objective == "improve AUC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_data_experiment_model.py -v"`
Expected: FAIL — `ModuleNotFoundError: app.models.data_experiment` (and table missing).

- [ ] **Step 3: Create the model**

```python
# backend/app/models/data_experiment.py
"""DataMaster job rows — state, ownership, and restart recovery for the
run_data_experiment capability. The Experiment knowledge node it produces
lives in knowledge_nodes; this table only tracks the run lifecycle."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DataExperimentJob(Base):
    __tablename__ = "data_experiment_jobs"

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
    sidecar_job_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", index=True
    )  # queued | running | done | error | cancelled
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    result_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
```

- [ ] **Step 4: Verify model registration pattern, then register**

Run: `docker compose exec backend bash -c "cd /app && grep -rn 'data_experiment\|import knowledge' app/models/__init__.py app/database.py 2>/dev/null | head"`
If `app/models/__init__.py` imports sibling models (e.g. `from app.models.knowledge import ...`), add the analogous line:

```python
from app.models.data_experiment import DataExperimentJob  # noqa: F401
```

If models are instead imported by Alembic's `env.py` / app startup, follow that existing mechanism instead. Do not invent a new registration path.

- [ ] **Step 5: Create the migration**

```python
# backend/alembic/versions/0021_data_experiment_jobs.py
"""data_experiment_jobs

Revision ID: 0021
Revises: 0020
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_experiment_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sidecar_job_id", sa.String(length=80), nullable=True),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("dataset_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="queued"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("result_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_data_experiment_jobs_user_id",
                    "data_experiment_jobs", ["user_id"])
    op.create_index("ix_data_experiment_jobs_project_id",
                    "data_experiment_jobs", ["project_id"])
    op.create_index("ix_data_experiment_jobs_status",
                    "data_experiment_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_data_experiment_jobs_status",
                  table_name="data_experiment_jobs")
    op.drop_index("ix_data_experiment_jobs_project_id",
                  table_name="data_experiment_jobs")
    op.drop_index("ix_data_experiment_jobs_user_id",
                  table_name="data_experiment_jobs")
    op.drop_table("data_experiment_jobs")
```

- [ ] **Step 6: Apply migration and verify up/down**

Run:
```bash
docker compose exec backend bash -c "cd /app && alembic upgrade head && alembic downgrade -1 && alembic upgrade head"
```
Expected: no errors; final state at revision `0021`.

- [ ] **Step 7: Run model test to verify it passes**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_data_experiment_model.py -v"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/data_experiment.py backend/alembic/versions/0021_data_experiment_jobs.py backend/tests/test_data_experiment_model.py
git add backend/app/models/__init__.py 2>/dev/null || true
git commit -m "$(cat <<'EOF'
feat(datamaster F2): data_experiment_jobs model + migration 0021

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Sidecar HTTP client + SSE parser

**Files:**
- Create: `backend/app/capabilities/datamaster_sidecar.py`
- Test: `backend/tests/test_datamaster_sidecar.py`

This module is the single boundary to the external agent. It is a thin
function module (not a class) so tests monkeypatch it cleanly (`respx` is
NOT available in this repo — only `httpx==0.27.2`).

- [ ] **Step 1: Write the failing test (pure SSE parser)**

```python
# backend/tests/test_datamaster_sidecar.py
from app.capabilities.datamaster_sidecar import parse_sse_block


def test_parse_sse_block_event_and_json_data():
    block = 'event: node\ndata: {"color": "red", "summary": "fetch external"}'
    evt = parse_sse_block(block)
    assert evt == {"type": "node",
                   "data": {"color": "red", "summary": "fetch external"}}


def test_parse_sse_block_defaults_to_message_and_raw_data():
    evt = parse_sse_block("data: hello world")
    assert evt == {"type": "message", "data": {"raw": "hello world"}}


def test_parse_sse_block_ignores_comments_and_blank():
    assert parse_sse_block(": keep-alive") is None
    assert parse_sse_block("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_sidecar.py -v"`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the sidecar client**

```python
# backend/app/capabilities/datamaster_sidecar.py
"""HTTP client for the DataMaster sidecar — the only boundary between
WorkspaceOS and the external agent. The sidecar implements:

  POST /jobs                  -> {"status": "accepted"}
  GET  /jobs/{id}/stream      -> text/event-stream (phase|node|metric|log|done|error)
  GET  /jobs/{id}             -> {"status", "progress", "result"?}
  POST /jobs/{id}/cancel
  GET  /healthz

Functions are module-level so tests can monkeypatch them. The sidecar
owns its own LLM/Serper/HF credentials; WorkspaceOS never proxies them.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0, read=None)  # no read timeout on the stream


def _headers(token: Optional[str]) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def parse_sse_block(block: str) -> Optional[Dict[str, Any]]:
    """Parse one SSE event block (lines split on \\n) into
    {"type": <event>, "data": <dict>}. Returns None for comments/blanks.
    `data:` is parsed as JSON when possible, else wrapped as {"raw": ...}.
    """
    block = block.strip("\n")
    if not block or block.startswith(":"):
        return None
    event = "message"
    data_lines = []
    for line in block.split("\n"):
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    if not data_lines:
        return None
    raw = "\n".join(data_lines)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {"raw": data}
    except (ValueError, TypeError):
        data = {"raw": raw}
    return {"type": event, "data": data}


async def healthz(base_url: str, token: Optional[str]) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{base_url.rstrip('/')}/healthz",
                             headers=_headers(token))
            return r.status_code == 200
    except httpx.HTTPError as exc:
        logger.warning("datamaster sidecar healthz failed: %s", exc)
        return False


async def submit_job(base_url: str, token: Optional[str],
                     body: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{base_url.rstrip('/')}/jobs",
                         headers=_headers(token), json=body)
        if r.status_code >= 400:
            raise RuntimeError(
                f"sidecar POST /jobs -> {r.status_code}: {r.text[:500]}")


async def stream_job(base_url: str, token: Optional[str],
                     job_id: str) -> AsyncIterator[Dict[str, Any]]:
    """Yield parsed SSE events until the connection closes."""
    url = f"{base_url.rstrip('/')}/jobs/{job_id}/stream"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        async with c.stream("GET", url, headers=_headers(token)) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise RuntimeError(
                    f"sidecar stream -> {resp.status_code}: {body[:500]}")
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    evt = parse_sse_block(block)
                    if evt is not None:
                        yield evt


async def get_job(base_url: str, token: Optional[str],
                   job_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{base_url.rstrip('/')}/jobs/{job_id}",
                         headers=_headers(token))
        if r.status_code >= 400:
            raise RuntimeError(
                f"sidecar GET /jobs/{job_id} -> {r.status_code}: {r.text[:300]}")
        return r.json()


async def cancel_job(base_url: str, token: Optional[str],
                     job_id: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            await c.post(f"{base_url.rstrip('/')}/jobs/{job_id}/cancel",
                         headers=_headers(token))
    except httpx.HTTPError as exc:
        logger.warning("datamaster sidecar cancel failed: %s", exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_sidecar.py -v"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/capabilities/datamaster_sidecar.py backend/tests/test_datamaster_sidecar.py
git commit -m "$(cat <<'EOF'
feat(datamaster F3): sidecar HTTP client + SSE parser

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Runner pure helpers — dataset validation + event mapping

**Files:**
- Create: `backend/app/capabilities/datamaster_runner.py` (helpers only this task)
- Test: `backend/tests/test_datamaster_runner_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_datamaster_runner_helpers.py
from app.capabilities.datamaster_runner import validate_dataset, map_event


def test_validate_dataset_accepts_hf_ref():
    ok, msg = validate_dataset({"kind": "hf", "ref": "acme/widgets"}, "")
    assert ok is True, msg


def test_validate_dataset_rejects_bad_hf_ref():
    ok, _ = validate_dataset({"kind": "hf", "ref": "../etc/passwd"}, "")
    assert ok is False


def test_validate_dataset_path_must_be_under_allowed_root():
    ok, _ = validate_dataset({"kind": "path", "ref": "/projects/d1"},
                             "/projects")
    assert ok is True
    ok, _ = validate_dataset({"kind": "path", "ref": "/etc/shadow"},
                             "/projects")
    assert ok is False
    ok, _ = validate_dataset({"kind": "path", "ref": "/projects/../etc"},
                             "/projects")
    assert ok is False


def test_validate_dataset_path_rejected_when_no_allowed_root():
    ok, _ = validate_dataset({"kind": "path", "ref": "/projects/d1"}, "")
    assert ok is False


def test_map_event_levels_and_summaries():
    lvl, summ, meta = map_event({"type": "done",
                                 "data": {"score": 0.91}})
    assert lvl == "success" and "0.91" in summ
    lvl, summ, _ = map_event({"type": "error",
                              "data": {"message": "boom"}})
    assert lvl == "error" and "boom" in summ
    lvl, summ, _ = map_event({"type": "node",
                              "data": {"color": "red", "summary": "explore"}})
    assert lvl == "info" and "red" in summ
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_runner_helpers.py -v"`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the runner module with helpers only**

```python
# backend/app/capabilities/datamaster_runner.py
"""run_data_experiment — slash_command handler.

Validates input, assembles a brief from the project knowledge graph,
persists a job row, and spawns a background task that drives an external
DataMaster sidecar (submit -> relay SSE trajectory -> persist result as
an Experiment node). The heavy agent never runs in this process.

Spec: docs/superpowers/specs/2026-05-18-datamaster-capability-design.md
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

_HF_REF_RE = re.compile(r"^[\w.\-]+/[\w.\-]+$")


def validate_dataset(dataset: Dict[str, Any],
                     allowed_root: str) -> Tuple[bool, str]:
    """Allow hf:<org/name> always; path datasets only when they resolve
    strictly inside a configured allowed_root. Reject everything else."""
    kind = (dataset or {}).get("kind")
    ref = str((dataset or {}).get("ref") or "").strip()
    if not ref:
        return False, "dataset ref is empty"
    if kind == "hf":
        if _HF_REF_RE.match(ref):
            return True, ""
        return False, f"invalid HuggingFace dataset id: {ref!r}"
    if kind == "path":
        if not allowed_root:
            return False, "path datasets disabled (allowed_dataset_root unset)"
        root = os.path.normpath(allowed_root)
        target = os.path.normpath(ref)
        if not os.path.isabs(target):
            return False, "path dataset must be absolute"
        if target != root and not target.startswith(root + os.sep):
            return False, f"path {ref!r} is outside allowed root {root!r}"
        return True, ""
    return False, f"unsupported dataset kind: {kind!r}"


def map_event(evt: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    """Map a sidecar SSE event to (level, summary, meta) for event_stream.emit."""
    etype = evt.get("type", "message")
    data = evt.get("data") or {}
    if etype == "done":
        return ("success",
                f"DataMaster done — score {data.get('score')}",
                {"score": data.get("score")})
    if etype == "error":
        return ("error",
                f"DataMaster error: {data.get('message') or data.get('raw') or 'unknown'}",
                {})
    if etype == "node":
        return ("info",
                f"DataMaster {data.get('color', '?')} node: "
                f"{data.get('summary', '')}".strip(),
                {})
    if etype == "metric":
        return ("info",
                f"DataMaster metric {data.get('name')}={data.get('value')}",
                {})
    if etype == "phase":
        return ("info", f"DataMaster: {data.get('name', 'phase')}", {})
    # log / message / unknown
    line = data.get("line") or data.get("raw") or ""
    return ("info", f"DataMaster: {str(line)[:180]}", {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_runner_helpers.py -v"`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/capabilities/datamaster_runner.py backend/tests/test_datamaster_runner_helpers.py
git commit -m "$(cat <<'EOF'
feat(datamaster F4): runner pure helpers (dataset validation, event map)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Brief assembly + result persistence (DB seams)

**Files:**
- Modify: `backend/app/capabilities/datamaster_runner.py` (add `_CONTEXT_NODE_TYPES`, `assemble_brief`, `persist_result`)
- Test: `backend/tests/test_datamaster_persist.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_datamaster_persist.py
import uuid
import pytest
from sqlalchemy import select
from app.models.knowledge import KnowledgeNode, KnowledgeEdge
from app.capabilities.datamaster_runner import assemble_brief, persist_result


@pytest.mark.asyncio
async def test_assemble_brief_includes_nodes_and_objective(
    db_session, sample_user, sample_project
):
    node = KnowledgeNode(
        user_id=sample_user.id, project_id=sample_project.id,
        node_type="claim", title="Data leakage suspected",
        content="val split overlaps train", source_refs=[], metadata_={},
        created_by="manual",
    )
    db_session.add(node)
    await db_session.commit()

    brief, seed_ids = await assemble_brief(
        db_session, sample_user.id, sample_project.id, "boost AUC"
    )
    assert "boost AUC" in brief
    assert "Data leakage suspected" in brief
    assert node.id in seed_ids


@pytest.mark.asyncio
async def test_assemble_brief_empty_kg_notes_no_context(
    db_session, sample_user, sample_project
):
    brief, seed_ids = await assemble_brief(
        db_session, sample_user.id, sample_project.id, "cold start"
    )
    assert "cold start" in brief
    assert "no prior context" in brief.lower()
    assert seed_ids == []


@pytest.mark.asyncio
async def test_persist_result_creates_experiment_node_and_edges(
    db_session, sample_user, sample_project
):
    seed = KnowledgeNode(
        user_id=sample_user.id, project_id=sample_project.id,
        node_type="claim", title="seed", content="x",
        source_refs=[], metadata_={}, created_by="manual",
    )
    db_session.add(seed)
    await db_session.commit()
    await db_session.refresh(seed)

    node_id = await persist_result(
        db_session,
        user_id=sample_user.id,
        project_id=sample_project.id,
        objective="boost AUC",
        sidecar_job_id="sc-1",
        result={"score": 0.93, "pipeline_summary_md": "## Pipeline\nfoo",
                "artifacts": [{"name": "loader.py", "uri": "s3://x"}]},
        seed_node_ids=[seed.id],
    )
    exp = (await db_session.execute(
        select(KnowledgeNode).where(KnowledgeNode.id == node_id)
    )).scalar_one()
    assert exp.node_type == "experiment"
    assert exp.title == "boost AUC"
    assert "0.93" in exp.content
    assert exp.created_by == "capability"

    edges = (await db_session.execute(
        select(KnowledgeEdge).where(KnowledgeEdge.source_node_id == node_id)
    )).scalars().all()
    assert len(edges) == 1
    assert edges[0].target_node_id == seed.id
    assert edges[0].edge_type == "derived_from"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_persist.py -v"`
Expected: FAIL — `ImportError: cannot import name 'assemble_brief'`.

- [ ] **Step 3: Add brief assembly + persistence to `datamaster_runner.py`**

Append to `backend/app/capabilities/datamaster_runner.py` (and add the imports shown at the top of the block to the existing import section, keeping `from __future__ import annotations` first):

```python
import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode

# Node types that seed the DataMaster brief. Experiments/claims are the
# direct "what are we trying to establish" anchors; paper_reference adds
# external grounding. Mirrors methods_drafter's project-then-user scoping.
_CONTEXT_NODE_TYPES = ("experiment", "claim", "paper_reference")
_PER_TYPE_LIMIT = 15
_TOTAL_NODE_LIMIT = 45


async def assemble_brief(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    objective: str,
) -> Tuple[str, List[uuid.UUID]]:
    """Build the task brief markdown from the project KG + objective.
    Returns (brief_md, seed_node_ids). Empty KG still returns a usable
    brief that explicitly notes the absence of prior context."""
    blocks: List[str] = []
    seed_ids: List[uuid.UUID] = []
    total = 0
    for node_type in _CONTEXT_NODE_TYPES:
        if total >= _TOTAL_NODE_LIMIT:
            break
        remaining = min(_PER_TYPE_LIMIT, _TOTAL_NODE_LIMIT - total)
        stmt = (
            select(KnowledgeNode)
            .where(
                KnowledgeNode.user_id == user_id,
                KnowledgeNode.node_type == node_type,
                KnowledgeNode.archived.is_(False),
            )
            .where(
                (KnowledgeNode.project_id == project_id)
                | (KnowledgeNode.project_id.is_(None))
            )
            .order_by(KnowledgeNode.updated_at.desc())
            .limit(remaining)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        if not rows:
            continue
        total += len(rows)
        lines = [f"## {node_type.upper()} ({len(rows)})"]
        for n in rows:
            seed_ids.append(n.id)
            lines.append(f"\n### {n.title}\n{(n.content or '').strip()[:1000]}")
        blocks.append("\n".join(lines))

    header = f"# DataMaster task brief\n\n**Objective:** {objective}\n\n"
    if blocks:
        body = ("Project knowledge-graph context (use as ground truth; "
                "do not invent entities not listed):\n\n" + "\n\n".join(blocks))
    else:
        body = ("No prior context: this project has no Experiment, Claim, "
                "or paper_reference nodes yet. Proceed from the objective "
                "alone.")
    return header + body, seed_ids


def _render_result_content(result: Dict[str, Any]) -> str:
    summary = (result.get("pipeline_summary_md") or "").strip()
    score = result.get("score")
    artifacts = result.get("artifacts") or []
    parts = [summary or "_(no pipeline summary returned)_",
             "\n## Result", f"\nFinal score: **{score}**"]
    if artifacts:
        parts.append("\n## Artifacts")
        for a in artifacts:
            parts.append(f"- {a.get('name', 'artifact')}: {a.get('uri', '')}")
    return "\n".join(parts)


async def persist_result(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: Optional[uuid.UUID],
    objective: str,
    sidecar_job_id: str,
    result: Dict[str, Any],
    seed_node_ids: List[uuid.UUID],
) -> uuid.UUID:
    """Create the Experiment node and `derived_from` edges to each seed
    node. Returns the new node id. user-scoped throughout."""
    node = KnowledgeNode(
        user_id=user_id,
        project_id=project_id,
        node_type="experiment",
        title=objective[:160],
        content=_render_result_content(result),
        source_refs=[{"kind": "capability",
                      "source": "datamaster:run_data_experiment",
                      "sidecar_job_id": sidecar_job_id}],
        metadata_={"capability_source": "datamaster",
                   "score": result.get("score"),
                   "artifacts": result.get("artifacts") or [],
                   "objective": objective},
        created_by="capability",
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)

    for target_id in seed_node_ids:
        edge = KnowledgeEdge(
            user_id=user_id,
            source_node_id=node.id,
            target_node_id=target_id,
            edge_type="derived_from",
            created_by="capability",
        )
        db.add(edge)
        try:
            await db.commit()
        except Exception:
            # Duplicate (uq_knowledge_edges_triple) or vanished target —
            # the result node still stands; skip this edge.
            await db.rollback()
    return node.id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_persist.py -v"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/capabilities/datamaster_runner.py backend/tests/test_datamaster_persist.py
git commit -m "$(cat <<'EOF'
feat(datamaster F5): KG brief assembly + Experiment-node persistence

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Background job runner + trigger handler + registration

**Files:**
- Modify: `backend/app/capabilities/datamaster_runner.py` (add `effective_config`, `_run_job`, `run_data_experiment_handler`)
- Modify: `backend/app/capabilities/slash.py:96-98` (register the runner)
- Test: `backend/tests/test_datamaster_runner_flow.py`

- [ ] **Step 1: Write the failing test (fake sidecar via monkeypatch)**

```python
# backend/tests/test_datamaster_runner_flow.py
import uuid
import pytest
from sqlalchemy import select

import app.capabilities.datamaster_runner as R
from app.capabilities import datamaster_sidecar as SC
from app.models.data_experiment import DataExperimentJob
from app.models.knowledge import KnowledgeNode


@pytest.mark.asyncio
async def test_run_job_happy_path_persists_experiment_and_marks_done(
    db_session, sample_user, sample_project, monkeypatch
):
    events = []
    monkeypatch.setattr(R, "emit",
                         lambda *a, **k: events.append((a, k)))

    async def fake_submit(base, token, body): return None

    async def fake_stream(base, token, jid):
        yield {"type": "phase", "data": {"name": "explore"}}
        yield {"type": "node", "data": {"color": "red", "summary": "ext"}}
        yield {"type": "done",
               "data": {"score": 0.88, "pipeline_summary_md": "## P",
                        "artifacts": []}}

    monkeypatch.setattr(SC, "submit_job", fake_submit)
    monkeypatch.setattr(SC, "stream_job", fake_stream)

    job = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="sc-x", objective="boost AUC",
        dataset_ref="hf:a/b", status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await R._run_job(
        job_id=job.id, base_url="http://sidecar", token=None,
        max_minutes=5, brief="# brief", seed_node_ids=[],
        dataset={"kind": "hf", "ref": "a/b"}, objective="boost AUC",
    )

    refreshed = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert refreshed.status == "done"
    assert refreshed.score == 0.88
    assert refreshed.result_node_id is not None
    exp = (await db_session.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == refreshed.result_node_id)
    )).scalar_one()
    assert exp.node_type == "experiment"


@pytest.mark.asyncio
async def test_run_job_sidecar_error_marks_error_no_node(
    db_session, sample_user, sample_project, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)

    async def fake_submit(base, token, body): return None

    async def fake_stream(base, token, jid):
        yield {"type": "error", "data": {"message": "sandbox OOM"}}

    monkeypatch.setattr(SC, "submit_job", fake_submit)
    monkeypatch.setattr(SC, "stream_job", fake_stream)

    job = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="sc-e", objective="x", dataset_ref="hf:a/b",
        status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await R._run_job(
        job_id=job.id, base_url="http://sidecar", token=None,
        max_minutes=5, brief="# b", seed_node_ids=[],
        dataset={"kind": "hf", "ref": "a/b"}, objective="x",
    )
    refreshed = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert refreshed.status == "error"
    assert "sandbox OOM" in (refreshed.error or "")
    assert refreshed.result_node_id is None


@pytest.mark.asyncio
async def test_handler_rejects_invalid_dataset(
    db_session, sample_user, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)
    out = await R.run_data_experiment_handler(
        {"project_id": str(uuid.uuid4()), "objective": "x",
         "dataset_ref": "/etc/passwd"},
        db_session, sample_user.id,
    )
    assert out["ok"] is False
    assert "dataset" in out["toast"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_runner_flow.py -v"`
Expected: FAIL — `AttributeError: module ... has no attribute '_run_job'`.

- [ ] **Step 3: Add config loader, background runner, and handler**

Append to `backend/app/capabilities/datamaster_runner.py`. Add these imports to the import block: `import asyncio`, `import logging`, `from app.database import AsyncSessionLocal`, `from app.services import extensions as ext_service`, `from app.services import capability_settings_service as cs`, `from app.services.event_stream import emit`, `from app.capabilities import datamaster_sidecar as sidecar`, `from app.models.data_experiment import DataExperimentJob`.

```python
logger = logging.getLogger(__name__)

_EXTENSION_ID = "datamaster"
_CAP_NAME = "run_data_experiment"
_SOURCE = "datamaster"


async def effective_config() -> Dict[str, Any]:
    """Manifest config merged with the user's encrypted Settings overlay."""
    manifest_cfg: Dict[str, Any] = {}
    for ext in ext_service.get_all_extensions():
        if ext.manifest.id != _EXTENSION_ID:
            continue
        for cap in ext.manifest.capabilities:
            if cap.name == _CAP_NAME:
                manifest_cfg = cap.config or {}
                break
    overlay = await cs.get_overlay(_EXTENSION_ID, _CAP_NAME)
    return cs.effective_config(manifest_cfg, overlay)


async def _set_status(db: AsyncSession, job_id: uuid.UUID, **fields: Any) -> None:
    job = (await db.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job_id)
    )).scalar_one_or_none()
    if job is None:
        return
    for k, v in fields.items():
        setattr(job, k, v)
    await db.commit()


async def _run_job(
    *,
    job_id: uuid.UUID,
    base_url: str,
    token: Optional[str],
    max_minutes: int,
    brief: str,
    seed_node_ids: List[uuid.UUID],
    dataset: Dict[str, Any],
    objective: str,
) -> None:
    """Background worker: submit -> relay SSE -> persist. Owns its own
    DB session (the request session is closed by the time this runs)."""
    async with AsyncSessionLocal() as db:
        await _set_status(db, job_id, status="running")
    sidecar_job_id = str(job_id)
    try:
        await sidecar.submit_job(base_url, token, {
            "job_id": sidecar_job_id,
            "objective": objective,
            "brief_md": brief,
            "dataset": dataset,
            "limits": {"max_minutes": max_minutes},
        })

        result: Optional[Dict[str, Any]] = None
        err: Optional[str] = None

        async def _consume() -> None:
            nonlocal result, err
            async for evt in sidecar.stream_job(base_url, token, sidecar_job_id):
                level, summary, _meta = map_event(evt)
                emit(level, _SOURCE, summary)
                if evt.get("type") == "done":
                    result = evt.get("data") or {}
                    return
                if evt.get("type") == "error":
                    d = evt.get("data") or {}
                    err = d.get("message") or d.get("raw") or "sidecar error"
                    return

        try:
            await asyncio.wait_for(_consume(), timeout=max_minutes * 60)
        except asyncio.TimeoutError:
            err = f"run exceeded {max_minutes} min — cancelled"
            await sidecar.cancel_job(base_url, token, sidecar_job_id)

        if err is not None or result is None:
            msg = err or "sidecar closed stream without a result"
            emit("error", _SOURCE, f"DataMaster failed: {msg}")
            async with AsyncSessionLocal() as db:
                await _set_status(db, job_id, status="error", error=msg[:4000])
            return

        async with AsyncSessionLocal() as db:
            job = (await db.execute(
                select(DataExperimentJob).where(
                    DataExperimentJob.id == job_id)
            )).scalar_one()
            node_id = await persist_result(
                db,
                user_id=job.user_id,
                project_id=job.project_id,
                objective=objective,
                sidecar_job_id=sidecar_job_id,
                result=result,
                seed_node_ids=seed_node_ids,
            )
            await _set_status(db, job_id, status="done",
                              score=result.get("score"),
                              result_node_id=node_id)
        emit("success", _SOURCE,
             f"DataMaster experiment landed as an Experiment node "
             f"(score {result.get('score')})")
    except Exception as exc:  # noqa: BLE001 — surface, never crash the loop
        logger.exception("datamaster _run_job failed")
        emit("error", _SOURCE, f"DataMaster run crashed: {exc}")
        async with AsyncSessionLocal() as db:
            await _set_status(db, job_id, status="error", error=str(exc)[:4000])


async def run_data_experiment_handler(
    payload: Dict[str, Any],
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Dict[str, Any]:
    """Slash handler. Validates, healthchecks, guards concurrency,
    persists the job row, spawns the background runner, returns fast."""
    project_id_raw = payload.get("project_id")
    objective = str(payload.get("objective") or "").strip()
    dataset_ref = str(payload.get("dataset_ref") or "").strip()
    if not project_id_raw:
        return {"ok": False, "toast": "Open a project first — DataMaster "
                "needs project context."}
    if not objective:
        return {"ok": False, "toast": "Objective is required."}
    try:
        project_id = uuid.UUID(str(project_id_raw))
    except ValueError:
        return {"ok": False, "toast": f"invalid project_id {project_id_raw!r}"}

    if dataset_ref.startswith("hf:"):
        dataset = {"kind": "hf", "ref": dataset_ref[3:].strip()}
    else:
        dataset = {"kind": "path", "ref": dataset_ref}

    cfg = await effective_config()
    ok, why = validate_dataset(dataset, cfg.get("allowed_dataset_root") or "")
    if not ok:
        return {"ok": False, "toast": f"Bad dataset: {why}"}

    base_url = cfg.get("sidecar_base_url") or ""
    token = cfg.get("sidecar_token") or None
    if not base_url:
        return {"ok": False, "toast": "DataMaster sidecar not configured — "
                "set sidecar_base_url in Settings."}
    if not await sidecar.healthz(base_url, token):
        return {"ok": False,
                "toast": f"DataMaster sidecar unreachable at {base_url}."}

    # Concurrency guard: one in-flight run per user.
    inflight = (await db.execute(
        select(DataExperimentJob).where(
            DataExperimentJob.user_id == user_id,
            DataExperimentJob.status.in_(("queued", "running")),
        ).limit(1)
    )).scalar_one_or_none()
    if inflight is not None:
        return {"ok": False, "toast": "A DataMaster run is already in "
                "progress — wait for it to finish."}

    try:
        max_minutes = int(payload.get("max_minutes")
                          or cfg.get("default_max_minutes") or 30)
    except (TypeError, ValueError):
        max_minutes = int(cfg.get("default_max_minutes") or 30)
    max_minutes = max(1, min(max_minutes, 240))

    brief, seed_ids = await assemble_brief(db, user_id, project_id, objective)

    job = DataExperimentJob(
        user_id=user_id, project_id=project_id,
        objective=objective, dataset_ref=dataset_ref, status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    emit("info", _SOURCE,
         f"DataMaster run queued for project {project_id} "
         f"({len(seed_ids)} KG seeds, ≤{max_minutes} min)")

    asyncio.create_task(_run_job(
        job_id=job.id, base_url=base_url, token=token,
        max_minutes=max_minutes, brief=brief, seed_node_ids=seed_ids,
        dataset=dataset, objective=objective,
    ))

    return {"ok": True, "job_id": str(job.id),
            "toast": "DataMaster run started — watch the TUI log; the "
            "result will appear as an Experiment node."}
```

- [ ] **Step 4: Register the runner in `slash.py`**

In `backend/app/capabilities/slash.py`, after the methods_drafter registration block (lines 96-98), add:

```python
# v0.2.7 — DataMaster data-experiment runner (ai-research capability)
from app.capabilities.datamaster_runner import run_data_experiment_handler  # noqa: E402
register_slash_runner("run_data_experiment", run_data_experiment_handler)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_runner_flow.py -v"`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full datamaster suite**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_manifest.py tests/test_data_experiment_model.py tests/test_datamaster_sidecar.py tests/test_datamaster_runner_helpers.py tests/test_datamaster_persist.py tests/test_datamaster_runner_flow.py -v"`
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/capabilities/datamaster_runner.py backend/app/capabilities/slash.py backend/tests/test_datamaster_runner_flow.py
git commit -m "$(cat <<'EOF'
feat(datamaster F6): background runner + trigger handler + registration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Startup reconcile of orphaned running jobs

**Files:**
- Modify: `backend/app/capabilities/datamaster_runner.py` (add `reconcile_running_jobs`)
- Modify: backend startup wiring — locate where `ingest_runner` is started and call reconcile alongside it
- Test: `backend/tests/test_datamaster_reconcile.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_datamaster_reconcile.py
import pytest
from sqlalchemy import select
import app.capabilities.datamaster_runner as R
from app.capabilities import datamaster_sidecar as SC
from app.models.data_experiment import DataExperimentJob


@pytest.mark.asyncio
async def test_reconcile_marks_dead_running_job_error(
    db_session, sample_user, sample_project, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)

    async def fake_eff_cfg():
        return {"sidecar_base_url": "http://sidecar", "sidecar_token": None}

    async def fake_get_job(base, token, jid):
        raise RuntimeError("sidecar forgot this job after restart")

    monkeypatch.setattr(R, "effective_config", fake_eff_cfg)
    monkeypatch.setattr(SC, "get_job", fake_get_job)

    job = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="sc-dead", objective="x", dataset_ref="hf:a/b",
        status="running",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await R.reconcile_running_jobs()

    refreshed = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert refreshed.status == "error"
    assert "restart" in (refreshed.error or "").lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_reconcile.py -v"`
Expected: FAIL — `AttributeError: ... 'reconcile_running_jobs'`.

- [ ] **Step 3: Add `reconcile_running_jobs`**

Append to `backend/app/capabilities/datamaster_runner.py`:

```python
async def reconcile_running_jobs() -> None:
    """On startup, any job still 'running' lost its background task when
    the process died. Ask the sidecar; if it can't confirm a result,
    mark the job error so it doesn't dangle. Best-effort — never raises."""
    try:
        cfg = await effective_config()
        base_url = cfg.get("sidecar_base_url") or ""
        token = cfg.get("sidecar_token") or None
        async with AsyncSessionLocal() as db:
            rows = list((await db.execute(
                select(DataExperimentJob).where(
                    DataExperimentJob.status == "running")
            )).scalars().all())
            for job in rows:
                done_result: Optional[Dict[str, Any]] = None
                if base_url:
                    try:
                        info = await sidecar.get_job(
                            base_url, token, str(job.id))
                        if info.get("status") == "done":
                            done_result = info.get("result") or {}
                    except Exception:  # noqa: BLE001
                        done_result = None
                if done_result is not None:
                    node_id = await persist_result(
                        db, user_id=job.user_id, project_id=job.project_id,
                        objective=job.objective,
                        sidecar_job_id=str(job.id),
                        result=done_result, seed_node_ids=[])
                    job.status = "done"
                    job.score = done_result.get("score")
                    job.result_node_id = node_id
                else:
                    job.status = "error"
                    job.error = ("orphaned by a backend restart; sidecar "
                                 "could not confirm a result")
                await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("datamaster reconcile_running_jobs failed")
```

- [ ] **Step 4: Wire it into startup**

Run: `docker compose exec backend bash -c "cd /app && grep -rn 'ingest_runner\|create_task\|lifespan\|on_event' app/main.py | head"`
At the same place the ingest poller is launched at app startup, add a best-effort schedule (do not block startup):

```python
import asyncio
from app.capabilities.datamaster_runner import reconcile_running_jobs
asyncio.create_task(reconcile_running_jobs())
```

Match the surrounding style (FastAPI `lifespan` vs `@app.on_event("startup")`). Place it next to the existing ingest-runner startup call. Keep the diff to the added lines only.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/test_datamaster_reconcile.py -v"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/capabilities/datamaster_runner.py backend/app/main.py backend/tests/test_datamaster_reconcile.py
git commit -m "$(cat <<'EOF'
feat(datamaster F7): reconcile orphaned running jobs on startup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Expose capability `inputs` to the palette

**Files:**
- Modify: `backend/app/routers/capabilities.py:115-124` (add `inputs` to the slash-commands payload)
- Test: `backend/tests/test_slash_commands_inputs.py`

- [ ] **Step 1: Write the failing test (HTTP contract — needs running backend)**

```python
# backend/tests/test_slash_commands_inputs.py
import os
import pytest
from httpx import AsyncClient

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
API_HEADERS = {"X-API-Key": os.environ.get("TEST_API_KEY", "dev-secret-key")}


@pytest.mark.asyncio
async def test_slash_commands_includes_inputs_for_datamaster():
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as c:
        r = await c.get("/api/v1/capabilities/slash-commands",
                         headers=API_HEADERS)
    assert r.status_code == 200
    entry = next((e for e in r.json()
                  if e["name"] == "run_data_experiment"), None)
    assert entry is not None, "run_data_experiment not listed"
    assert isinstance(entry.get("inputs"), list)
    names = {f["name"] for f in entry["inputs"]}
    assert {"objective", "dataset_ref"}.issubset(names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose up -d backend && docker compose exec backend bash -c "cd /app && python -m pytest tests/test_slash_commands_inputs.py -v"`
Expected: FAIL — `inputs` key absent (KeyError / assertion).

- [ ] **Step 3: Add `inputs` to the payload**

In `backend/app/routers/capabilities.py`, inside `list_slash_commands`, the appended dict (lines 115-124) gains one line:

```python
            items.append({
                "id": f"{ext.manifest.id}/{cap.name}",
                "name": cap.name,
                "label": cfg.get("label") or cap.name,
                "keywords": cfg.get("keywords") or [],
                "icon": cfg.get("icon"),
                "handler_kind": cfg.get("handler_kind", "api_call"),
                "handler_target": cfg.get("handler_target"),
                "inputs": cfg.get("inputs") or [],
                "source_extension": ext.manifest.id,
            })
```

- [ ] **Step 4: Rebuild backend and run test to verify it passes**

Run: `docker compose up --build -d backend && docker compose exec backend bash -c "cd /app && python -m pytest tests/test_slash_commands_inputs.py -v"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/capabilities.py backend/tests/test_slash_commands_inputs.py
git commit -m "$(cat <<'EOF'
feat(datamaster F8): expose capability inputs[] in slash-commands API

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Frontend — input dialog + palette wiring

**Files:**
- Modify: `frontend/lib/capabilities.ts` (extend `SlashCommandEntry` with `inputs`)
- Create: `frontend/components/bench/CapabilityInputDialog.tsx`
- Modify: `frontend/components/bench/CommandPalette.tsx:77-90` (open dialog when `cmd.inputs?.length`)
- Verification: `npm run lint` + `npm run build` (this repo has no frontend unit harness; build+lint is the gate)

> **READ FIRST:** `frontend/AGENTS.md` says this Next.js has breaking changes vs. training data. Before writing/modifying any frontend file, read the relevant guide under `frontend/node_modules/next/dist/docs/` (client components, app router). Follow existing component conventions in `frontend/components/bench/` (shadcn/ui, lucide-react, Tailwind v4). Do not introduce new shared modules.

- [ ] **Step 1: Extend the `SlashCommandEntry` type**

In `frontend/lib/capabilities.ts`, add to the `SlashCommandEntry` interface (after `handler_target`):

```typescript
export interface SlashCommandInput {
  name: string;
  label: string;
  type: 'text' | 'textarea' | 'number';
  required?: boolean;
  placeholder?: string;
}

export interface SlashCommandEntry {
  id: string;
  name: string;
  label: string;
  keywords: string[];
  icon?: string | null;
  handler_kind: 'api_call' | 'navigate';
  handler_target: string;
  inputs?: SlashCommandInput[];
  source_extension: string;
}
```

- [ ] **Step 2: Create the input dialog component**

Match the styling of the existing palette modal in `CommandPalette.tsx` (fixed overlay, `bg-card`, `border-border`, `rounded-lg`). Render one control per `inputs` entry; collect values into a payload object.

```tsx
// frontend/components/bench/CapabilityInputDialog.tsx
'use client';

import { useState } from 'react';
import type { SlashCommandInput } from '@/lib/capabilities';

interface Props {
  title: string;
  inputs: SlashCommandInput[];
  onSubmit: (values: Record<string, unknown>) => void;
  onClose: () => void;
}

export function CapabilityInputDialog({ title, inputs, onSubmit, onClose }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});

  const missingRequired = inputs.some(
    (f) => f.required && !(values[f.name] || '').trim(),
  );

  const set = (name: string, v: string) =>
    setValues((prev) => ({ ...prev, [name]: v }));

  const submit = () => {
    const payload: Record<string, unknown> = {};
    for (const f of inputs) {
      const raw = (values[f.name] || '').trim();
      if (!raw) continue;
      payload[f.name] = f.type === 'number' ? Number(raw) : raw;
    }
    onSubmit(payload);
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 pt-24"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-[560px] max-w-[90vw] rounded-lg border border-border bg-card p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-sm font-medium text-foreground">{title}</h2>
        <div className="space-y-3">
          {inputs.map((f) => (
            <label key={f.name} className="block text-xs text-muted-foreground">
              {f.label}{f.required ? ' *' : ''}
              {f.type === 'textarea' ? (
                <textarea
                  className="mt-1 w-full rounded border border-border/60 bg-transparent px-2 py-1.5 text-sm text-foreground outline-none"
                  rows={3}
                  placeholder={f.placeholder}
                  value={values[f.name] || ''}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              ) : (
                <input
                  type={f.type === 'number' ? 'number' : 'text'}
                  className="mt-1 w-full rounded border border-border/60 bg-transparent px-2 py-1.5 text-sm text-foreground outline-none"
                  placeholder={f.placeholder}
                  value={values[f.name] || ''}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              )}
            </label>
          ))}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            className="rounded px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
            disabled={missingRequired}
            onClick={submit}
          >
            Run
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire the dialog into the palette**

In `frontend/components/bench/CommandPalette.tsx`: import the dialog and `useProjects`/active-project context already present (`onProjectSelect` exists; the palette already imports `useProjects`). Add state for a pending command, and change the slash-command `run` to open the dialog when `cmd.inputs?.length`, otherwise dispatch as before. The dialog's `onSubmit` merges `project_id` (the currently filtered/active project) into the payload before dispatch.

Add near the other `useState` hooks:

```tsx
import { CapabilityInputDialog } from './CapabilityInputDialog';
// ...
const [pendingCmd, setPendingCmd] = useState<SlashCommandEntry | null>(null);
```

(Import `SlashCommandEntry` type from `@/lib/capabilities`.)

Replace the slash-command mapping block (lines 77-90) with:

```tsx
    ...slashCommands.map((cmd) => ({
      id: `cmd-${cmd.id}`,
      label: cmd.label,
      hint: cmd.source_extension,
      group: 'commands' as const,
      run: async () => {
        if (cmd.inputs && cmd.inputs.length > 0) {
          setPendingCmd(cmd);
          return; // dialog handles dispatch; keep palette context
        }
        onClose();
        await dispatch(
          cmd.handler_kind,
          cmd.handler_target,
          (path) => router.push(path),
        );
      },
    })),
```

Render the dialog at the end of the component's returned JSX (sibling of the palette root), passing the active project id. The palette receives the active project via the existing project filter — use the same value `onProjectSelect` toggles; if the palette does not already hold it as state, accept it via a new optional prop `activeProjectId?: string` threaded from the parent that renders `<CommandPalette>` (grep the parent for where `onProjectSelect` is wired and pass the current filter value):

```tsx
{pendingCmd && (
  <CapabilityInputDialog
    title={pendingCmd.label}
    inputs={pendingCmd.inputs || []}
    onClose={() => setPendingCmd(null)}
    onSubmit={async (vals) => {
      const cmd = pendingCmd;
      setPendingCmd(null);
      onClose();
      await dispatch(
        cmd.handler_kind,
        cmd.handler_target,
        (path) => router.push(path),
        { ...vals, project_id: activeProjectId },
      );
    }}
  />
)}
```

If threading `activeProjectId` requires a parent change, make that minimal prop addition in the parent that renders `CommandPalette` (one prop, passing the existing selected-project filter value). Do not refactor the parent otherwise.

- [ ] **Step 4: Lint + typecheck + build**

Run (from `frontend/`):
```bash
npm run lint && npm run build
```
Expected: lint clean, build succeeds (no TS errors). Fix any type errors surfaced (e.g., import paths, the new prop).

- [ ] **Step 5: Manual smoke (documented, not automated)**

With `docker compose up -d` and a DataMaster sidecar reachable (or `sidecar_base_url` pointed at a stub): open ⌘K → "Run DataMaster experiment" → dialog appears → submit with `hf:acme/widgets` → toast "DataMaster run started" → TUI log shows `DataMaster:` lines. Record the result in the PR description.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/capabilities.ts frontend/components/bench/CapabilityInputDialog.tsx frontend/components/bench/CommandPalette.tsx
# include the parent file ONLY if the activeProjectId prop was threaded
git commit -m "$(cat <<'EOF'
feat(datamaster F9): ⌘K input dialog for capabilities with inputs[]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Contributor docs — sidecar job API contract + compose profile

**Files:**
- Create: `sidecars/datamaster/README.md` (the contract any sidecar must implement)
- Modify: `docker-compose.yml` (add an opt-in, profile-gated `datamaster` service referencing a user-supplied image)

The reference sidecar Dockerfile/implementation is an explicit post-v1
follow-up (see spec "Open follow-ups"). v1 ships only the documented
contract + a profile-gated compose entry so a contributor can drop in an
image without touching core.

- [ ] **Step 1: Write the contract doc**

```markdown
# DataMaster Sidecar Contract

WorkspaceOS's `run_data_experiment` capability talks to an external
sidecar over this HTTP contract. Any agent backend implementing it works
unchanged. The sidecar owns its own LLM / Serper / HuggingFace
credentials (its own `.env`); WorkspaceOS never sends them.

## Endpoints

- `GET /healthz` → `200` when ready.
- `POST /jobs` — body:
  `{ "job_id": str, "objective": str, "brief_md": str,
     "dataset": { "kind": "hf"|"path", "ref": str },
     "limits": { "max_minutes": int } }`
  → `{ "status": "accepted" }` (any `>=400` is treated as failure).
- `GET /jobs/{job_id}/stream` — `text/event-stream`. Each event:
  `event: <phase|node|metric|log|done|error>` + `data: <json>`.
  - `node.data`: `{ "color": "red"|"black", "summary": str }`
  - `metric.data`: `{ "name": str, "value": number }`
  - `done.data`: `{ "score": number, "pipeline_summary_md": str,
                     "artifacts": [{ "name": str, "uri": str }] }`
  - `error.data`: `{ "message": str }`
- `GET /jobs/{job_id}` → `{ "status": "...", "progress": ...,
  "result"?: <done.data shape> }` (poll fallback + restart recovery).
- `POST /jobs/{job_id}/cancel`.

`job_id` sent by WorkspaceOS is the canonical id; use it as the path id.

## Auth

If `sidecar_token` is set in the capability Settings, WorkspaceOS sends
`Authorization: Bearer <token>` on every request. Validate it.

## Running

Set `sidecar_base_url` in WorkspaceOS Settings → Capabilities →
DataMaster to your sidecar's URL. With the bundled compose profile:
`DATAMASTER_SIDECAR_IMAGE=<your-image> docker compose --profile sidecars up datamaster`
```

- [ ] **Step 2: Add the profile-gated compose service**

In `docker-compose.yml`, add under `services:` (match indentation/style of existing services; attach to the existing `workspaceos` network). It is gated by the `sidecars` profile so default `docker compose up` does NOT start it:

```yaml
  datamaster:
    image: ${DATAMASTER_SIDECAR_IMAGE:-ghcr.io/REPLACE_ME/datamaster-sidecar:latest}
    profiles: ["sidecars"]
    networks: [workspaceos]
    ports:
      - "8800:8800"
    env_file:
      - ./sidecars/datamaster/.env
    restart: unless-stopped
```

- [ ] **Step 3: Verify default compose is unaffected**

Run: `docker compose config --services`
Expected: lists `db`, `backend`, `frontend` — and `datamaster` only appears with `docker compose --profile sidecars config --services`.

- [ ] **Step 4: Commit**

```bash
git add sidecars/datamaster/README.md docker-compose.yml
git commit -m "$(cat <<'EOF'
docs(datamaster F10): sidecar contract + opt-in compose profile

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Full-suite regression + spec verification

- [ ] **Step 1: Run the entire backend suite**

Run: `docker compose exec backend bash -c "cd /app && python -m pytest tests/ -q"`
Expected: no new failures vs. the pre-change baseline. Investigate any regression before proceeding.

- [ ] **Step 2: Frontend build**

Run (from `frontend/`): `npm run lint && npm run build`
Expected: clean.

- [ ] **Step 3: Spec checklist walk-through**

Open `docs/superpowers/specs/2026-05-18-datamaster-capability-design.md` and confirm each item: sidecar isolation (Task 3/10), one slash_command (Task 1/6), KG-grounded brief + objective + dataset (Task 4/5/6), Experiment node + derived_from edges (Task 5), SSE relay + poll fallback + restart recovery (Task 3/6/7), all error-handling rows (Task 6/7), security (Task 1 redaction, Task 4 dataset validation, Task 5/6 user scoping), testing (Tasks 1-8). Note any gap and add a task before sign-off.

- [ ] **Step 4: Hand off for code review**

Use `superpowers:requesting-code-review` (or the `code-reviewer` agent per the user's global standard) against the branch before merge. Do not self-review.

---

## Self-Review (performed during planning)

**Spec coverage:** Every spec section maps to a task — sidecar comms/isolation (T3,T10), manifest/slash_command (T1,T6), KG brief + inputs (T4,T5,T6,T8,T9), Experiment node + F3 `derived_from` linking (T5), SSE relay + poll fallback + restart recovery (T3,T6,T7), all error-handling rows incl. concurrency guard & timeout & empty-KG (T6) and orphan recovery (T7), security: `sidecar_token` redaction (T1), dataset validation (T4), user-scoped reads/writes (T5,T6), no-live-DataMaster testing via monkeypatched fake sidecar (T6). Out-of-scope items remain out (no EvoMaster runner, no self-evolution, no methods handoff, reference Dockerfile deferred — T10 ships only the contract + profile).

**Placeholder scan:** No TBD/TODO; every code step is complete. The two "locate the existing X then add one line" steps (model registration in T2.S4, startup wiring in T7.S4) include the exact grep command and the exact lines to add — the indirection is because the repo's registration mechanism must be confirmed, not invented.

**Type consistency:** `validate_dataset`/`map_event`/`assemble_brief`/`persist_result`/`effective_config`/`_run_job`/`run_data_experiment_handler`/`reconcile_running_jobs` signatures are defined once and called consistently across tasks and tests. `SlashCommandEntry.inputs` (frontend) matches the backend `inputs` payload added in T8 and the manifest `inputs` in T1. `DataExperimentJob` fields used in T6/T7 match the model defined in T2. Edge type string `"derived_from"` and `created_by="capability"` are consistent in T5 and T7.
