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
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEdge, KnowledgeNode

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
