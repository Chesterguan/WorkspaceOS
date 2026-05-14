"""POST /feedback — user-submitted issue → GitHub.

Captures a small text payload plus auto-collected context (current
surface, project id, recent bench events, browser hint) and creates
a GitHub issue on the configured FEEDBACK_REPO.

Trust + privacy notes:
  - The user types title + body themselves. We don't auto-attach the
    raw conversation history, the file watcher's recent paths, or any
    secret material from settings.
  - Context block is rendered as a fenced JSON block under the user's
    body. Easy to audit, easy to redact before submit if needed.
  - The GitHub PAT is the one already in GITHUB_TOKEN (read+write
    issues scope). No new credential.
  - Rate limited by the global slowapi middleware (120 req/min).
    Combined with the GitHub API's own per-PAT limit, feedback spam
    is bounded.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, get_optional_user_id, verify_api_key
from app.services.event_stream import emit, get_buffer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackContext(BaseModel):
    """Auto-collected page state. All fields optional — frontend sends
    what it can introspect. Never contains secrets."""

    surface: Optional[str] = None
    project_id: Optional[str] = None
    url: Optional[str] = None
    user_agent: Optional[str] = None
    viewport: Optional[Dict[str, int]] = None
    extra: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=140,
                       description="Short summary, becomes the issue title.")
    body: str = Field(..., min_length=10, max_length=8000,
                      description="What happened; what was expected. Markdown supported.")
    kind: str = Field(default="bug",
                      description="bug | feature | question — drives the label.")
    context: Optional[FeedbackContext] = None
    include_recent_events: bool = Field(default=True,
        description="If true, includes the last ~10 bench TUI events as context.")


class FeedbackResponse(BaseModel):
    issue_url: str
    issue_number: int


_LABEL_BY_KIND: Dict[str, List[str]] = {
    "bug":      ["user-feedback", "bug"],
    "feature":  ["user-feedback", "enhancement"],
    "question": ["user-feedback", "question"],
}


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """Create a GitHub issue from the feedback payload."""
    if not settings.feedback_repo:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feedback is disabled (FEEDBACK_REPO not set).",
        )
    if not settings.github_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_TOKEN not configured — can't create issues.",
        )

    issue_body = _compose_body(body, jwt_user_id)
    labels = _LABEL_BY_KIND.get(body.kind, ["user-feedback"])

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"https://api.github.com/repos/{settings.feedback_repo}/issues",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "WorkspaceOS/0.2",
            },
            json={
                "title": body.title.strip(),
                "body": issue_body,
                "labels": labels,
            },
        )
    if resp.status_code not in (200, 201):
        logger.warning("GitHub issue create failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {resp.status_code}",
        )
    data = resp.json()
    issue_url = data.get("html_url") or ""
    issue_number = data.get("number") or 0

    emit("success", "feedback",
         f"User feedback filed → issue #{issue_number}",
         meta={"issue_url": issue_url, "kind": body.kind})

    return FeedbackResponse(issue_url=issue_url, issue_number=issue_number)


# ── Helpers ────────────────────────────────────────────────────────


def _compose_body(req: FeedbackRequest, jwt_user_id: Optional[str]) -> str:
    """Assemble the issue body: user text + fenced context block."""
    parts: List[str] = [req.body.strip(), ""]

    ctx_lines: List[str] = []
    if req.context:
        c = req.context
        if c.surface:     ctx_lines.append(f"- surface: `{c.surface}`")
        if c.project_id:  ctx_lines.append(f"- project_id: `{c.project_id}`")
        if c.url:         ctx_lines.append(f"- url: `{c.url}`")
        if c.viewport:    ctx_lines.append(f"- viewport: `{c.viewport.get('w', '?')}x{c.viewport.get('h', '?')}`")
        if c.user_agent:  ctx_lines.append(f"- user_agent: `{c.user_agent[:120]}`")
        if c.extra:
            ctx_lines.append("- extra:")
            ctx_lines.append("  ```json")
            for line in json.dumps(c.extra, indent=2).splitlines():
                ctx_lines.append(f"  {line}")
            ctx_lines.append("  ```")
    if jwt_user_id:
        ctx_lines.append(f"- submitter_user_id: `{jwt_user_id}`")
    ctx_lines.append(f"- ts: `{int(time.time())}`")

    parts.append("---")
    parts.append("**Context**")
    parts.extend(ctx_lines)

    if req.include_recent_events:
        events = get_buffer()[-10:]
        if events:
            parts.append("")
            parts.append("**Recent bench events**")
            parts.append("```")
            for e in events:
                ts = time.strftime("%H:%M:%S", time.localtime(e.get("ts", time.time())))
                parts.append(f"{ts}  [{e.get('level', '?')}] {e.get('source', '?')}: {e.get('summary', '')}")
            parts.append("```")

    parts.append("")
    parts.append("_Auto-filed by WorkspaceOS in-app feedback._")
    return "\n".join(parts)
