"""run_data_experiment — slash_command handler.

Validates input, assembles a brief from the project knowledge graph,
persists a job row, and spawns a background task that drives an external
DataMaster sidecar (submit -> relay SSE trajectory -> persist result as
an Experiment node). The heavy agent never runs in this process.

Spec: docs/superpowers/specs/2026-05-18-datamaster-capability-design.md
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.data_experiment import DataExperimentJob
from app.models.knowledge import KnowledgeEdge, KnowledgeNode
from app.services import capability_settings_service as cs
from app.services import extensions as ext_service
from app.services.event_stream import emit
from app.capabilities import datamaster_sidecar as sidecar

_HF_REF_RE = re.compile(r"^[\w.\-]+/[\w.\-]+$")


def validate_dataset(dataset: Dict[str, Any],
                     allowed_root: str) -> Tuple[bool, str]:
    """Policy gate on the user-supplied dataset pointer. hf:<org/name>
    accepted by shape. A `path` dataset is accepted only when the
    normalized, absolute path string is the configured allowed_root or
    lies under it — a SYNTACTIC containment check. The path itself is
    resolved and read by the external sidecar in its own filesystem;
    this function does not (and cannot) resolve symlinks here. Reject
    everything else."""
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
        # Use a savepoint so a duplicate-edge IntegrityError (uq_knowledge_edges_triple)
        # or a vanished-target FK violation drops only this edge without rolling back
        # the result node or previously written edges.
        async with db.begin_nested() as sp:
            try:
                db.add(KnowledgeEdge(
                    user_id=user_id,
                    source_node_id=node.id,
                    target_node_id=target_id,
                    edge_type="derived_from",
                    created_by="capability",
                ))
                await db.flush()
            except IntegrityError:
                await sp.rollback()
    await db.commit()
    return node.id


logger = logging.getLogger(__name__)

_EXTENSION_ID = "datamaster"
_CAP_NAME = "run_data_experiment"
_SOURCE = "datamaster"

# Module-level set retains task references so CPython's GC cannot collect a
# running task before it completes (asyncio only holds a weak reference).
_background_tasks: "set[asyncio.Task]" = set()


def _spawn_run_job(**kwargs: Any) -> None:
    task = asyncio.create_task(_run_job(**kwargs))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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


@asynccontextmanager
async def _session(  # type: ignore[misc]
    _db: Optional[AsyncSession] = None,
):
    """Async-context helper that yields either the caller-supplied session
    (test seam, not closed on exit) or a fresh ``AsyncSessionLocal()``
    (production path, closed on exit)."""
    if _db is not None:
        yield _db
    else:
        async with AsyncSessionLocal() as s:
            yield s


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
    _db: Optional[AsyncSession] = None,
) -> None:
    """Background worker: submit -> relay SSE -> persist. Owns its own
    DB session (the request session is closed by the time this runs).

    ``_db`` is a test-only seam: when provided, all DB operations use
    that session instead of opening new ``AsyncSessionLocal()`` sessions.
    Production callers leave it ``None``.
    """
    async with _session(_db) as db:
        await _set_status(db, job_id, status="running")
    sidecar_job_id = str(job_id)
    persisted_node_id: Optional[uuid.UUID] = None
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
            async with _session(_db) as db:
                await _set_status(db, job_id, status="error", error=msg[:4000])
            return

        async with _session(_db) as db:
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
            persisted_node_id = node_id
            await _set_status(db, job_id, status="done",
                              score=result.get("score"),
                              result_node_id=node_id)
        emit("success", _SOURCE,
             f"DataMaster experiment landed as an Experiment node "
             f"(score {result.get('score')})")
    except Exception as exc:  # noqa: BLE001 — surface, never crash the loop
        logger.exception("datamaster _run_job failed")
        try:
            if persisted_node_id is not None:
                # The experiment landed; only post-persist bookkeeping failed.
                emit("warn", _SOURCE,
                     f"DataMaster experiment persisted but status update "
                     f"hiccuped: {exc}")
                async with _session(_db) as db:
                    await _set_status(db, job_id, status="done",
                                      result_node_id=persisted_node_id)
            else:
                emit("error", _SOURCE, f"DataMaster run crashed: {exc}")
                async with _session(_db) as db:
                    await _set_status(db, job_id, status="error",
                                      error=str(exc)[:4000])
        except Exception:  # noqa: BLE001 — last-resort: never let the task die uncaught
            logger.exception("datamaster _run_job error-handler also failed")


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
    if not dataset_ref:
        return {"ok": False, "toast": "Dataset is required."}
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
         f"({len(seed_ids)} KG seeds, <={max_minutes} min)")

    _spawn_run_job(
        job_id=job.id, base_url=base_url, token=token,
        max_minutes=max_minutes, brief=brief, seed_node_ids=seed_ids,
        dataset=dataset, objective=objective,
    )

    return {"ok": True, "job_id": str(job.id),
            "toast": "DataMaster run started — watch the TUI log; the "
            "result will appear as an Experiment node."}


async def reconcile_running_jobs(
    _db: Optional[AsyncSession] = None,
) -> None:
    """On startup, any job still 'running' lost its background task when
    the process died. Ask the sidecar; if it can't confirm a result,
    mark the job error so it doesn't dangle. Best-effort — never raises.

    ``_db`` is a test-only seam: when provided, all DB operations use
    that session instead of opening a new ``AsyncSessionLocal()``.
    Production callers (startup wiring) leave it ``None``.
    """
    try:
        cfg = await effective_config()
        base_url = cfg.get("sidecar_base_url") or ""
        token = cfg.get("sidecar_token") or None
        async with _session(_db) as db:
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
