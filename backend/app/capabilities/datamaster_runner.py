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
