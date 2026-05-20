"""STUB DataMaster sidecar — reference implementation of the contract in
README.md. Emits a canned DataTree trajectory. NOT a real ML agent; do
NOT use for real experiments.

Endpoints implemented per the contract:
  GET  /healthz              -> 200 {"ok": true}
  POST /jobs                 -> {"status": "accepted"}
  GET  /jobs/{id}/stream     -> text/event-stream (canned trajectory)
  GET  /jobs/{id}            -> {"status", "result"?}  (poll fallback)
  POST /jobs/{id}/cancel     -> 204
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="datamaster-stub")

# In-memory job state keyed by job_id sent in POST body.
_JOBS: Dict[str, Dict[str, Any]] = {}

# Canned trajectory shape. Each tuple is (event_name, data_dict).
_TRAJECTORY = [
    ("phase",  {"name": "explore"}),
    ("node",   {"color": "red",   "summary": "fetch synthetic dataset variant"}),
    ("metric", {"name": "baseline_auc", "value": 0.72}),
    ("phase",  {"name": "exploit"}),
    ("node",   {"color": "black", "summary": "scale features + tune regularization"}),
    ("metric", {"name": "auc", "value": 0.86}),
    ("log",    {"line": "stub pipeline finalized after 2 DataTree levels"}),
    ("done",   {"score": 0.86,
                "pipeline_summary_md": (
                    "## Stub pipeline\n"
                    "- standardized numeric features\n"
                    "- tuned L2 regularization via 5-fold CV"
                ),
                "artifacts": [
                    {"name": "loader.py", "uri": "stub://artifact/loader.py"}
                ]}),
]

_FINAL_RESULT = _TRAJECTORY[-1][1]


class _SubmitBody(BaseModel):
    job_id: str
    objective: str
    brief_md: str
    dataset: Dict[str, Any]
    limits: Dict[str, Any] = {}


@app.get("/healthz")
async def healthz() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/jobs")
async def submit_job(body: _SubmitBody) -> Dict[str, str]:
    _JOBS[body.job_id] = {"status": "queued", "result": None,
                          "cancelled": False}
    return {"status": "accepted"}


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/jobs/{job_id}/stream")
async def stream(job_id: str) -> StreamingResponse:
    if job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="unknown job")

    async def gen():
        _JOBS[job_id]["status"] = "running"
        for event, data in _TRAJECTORY:
            if _JOBS[job_id].get("cancelled"):
                yield _format_sse("error", {"message": "cancelled"})
                _JOBS[job_id]["status"] = "cancelled"
                return
            yield _format_sse(event, data)
            await asyncio.sleep(0.4)  # realistic-ish pacing
        _JOBS[job_id]["status"] = "done"
        _JOBS[job_id]["result"] = _FINAL_RESULT

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/jobs/{job_id}")
async def poll(job_id: str) -> Dict[str, Any]:
    if job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="unknown job")
    j = _JOBS[job_id]
    out: Dict[str, Any] = {"status": j["status"]}
    if j.get("result") is not None:
        out["result"] = j["result"]
    return out


@app.post("/jobs/{job_id}/cancel", status_code=204)
async def cancel(job_id: str) -> Response:
    if job_id in _JOBS:
        _JOBS[job_id]["cancelled"] = True
    return Response(status_code=204)
