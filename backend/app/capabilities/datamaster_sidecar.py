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
