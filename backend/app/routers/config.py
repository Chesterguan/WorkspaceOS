"""Serve the active domain config to the frontend + onboarding endpoints.

`GET /domain` returns the loaded config in resolved shape (used by the bench UI
on every page load).

`POST /generate` runs the wizard answers through the generator service and
streams progress captions over SSE, terminating with the proposed config
preview. The preview is NOT written to disk — the wizard's preview pane
renders it, the user confirms with /apply.

`POST /apply` writes the proposed config files to CONFIG_DIR and triggers
the domain_config loader to reload. Marks the calling user's
tutorial_completed flag.

`POST /apply` and `POST /generate` require a JWT (no API key path) since
both mutate user state.
"""
import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_db,
    get_optional_user_id,
    parse_jwt_user_uuid,
    verify_api_key,
)
from app.models.user import User
from app.schemas.onboarding import (
    ApplyConfigRequest,
    GeneratedConfig,
    OnboardingAnswers,
)
from app.services import config_generator
from app.services.domain_config import get_loader
from app.services.event_stream import emit as emit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    """Same resolution rule as DomainConfigLoader._DEFAULT_CONFIG_DIR."""
    docker_path = Path("/app/config")
    return docker_path if docker_path.exists() else Path("config")


async def _require_user(
    jwt_user_id: Optional[str],
    db: AsyncSession,
) -> User:
    if not jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Onboarding requires a logged-in user (JWT).",
        )
    user_uuid = parse_jwt_user_uuid(jwt_user_id)
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


# ---------------------------------------------------------------------------
# Read endpoint
# ---------------------------------------------------------------------------


@router.get("/domain")
async def get_domain_config(_: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """Return the active domain config with taxonomies + persona pools inlined."""
    loader = get_loader()
    surfaces: List[Dict[str, Any]] = []
    for s in loader.get_surfaces():
        surface_dict: Dict[str, Any] = {
            "type": s.type,
            "id": s.id,
            "letter": s.letter,
            "label": s.label,
            "accent": s.accent,
        }
        if s.taxonomy:
            tax = loader.get_taxonomy_by_path(s.taxonomy)
            surface_dict["taxonomy"] = {
                "node_types": [n.model_dump() for n in tax.node_types],
                "edge_types": [e.model_dump() for e in tax.edge_types],
            }
        if s.personas:
            pool = loader._load_persona_file(s.personas)
            surface_dict["personas"] = {
                "pool_id": pool.pool_id,
                "mode_label": pool.mode_label,
                "items": [
                    {"id": p.id, "name": p.name, "color": p.color, "avatar": p.avatar}
                    for p in pool.personas
                ],
            }
        surfaces.append(surface_dict)

    app_cfg = loader.get_app()
    return {
        "app": {
            "name": app_cfg.name,
            "accent": app_cfg.accent,
            "tagline": app_cfg.tagline,
        },
        "surfaces": surfaces,
        "integrations": loader.get_integrations(),
    }


# ---------------------------------------------------------------------------
# Onboarding wizard endpoints
# ---------------------------------------------------------------------------


@router.post("/generate")
async def generate_config_sse(
    answers: OnboardingAnswers,
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Run the wizard answers through the generator, streaming captions.

    SSE events:
      event: progress  data: {"caption": "..."}        — wait-state captions
      event: done      data: <GeneratedConfig JSON>    — terminal success
      event: error     data: {"message": "..."}        — terminal failure

    The frontend's wait-state animation listens to `progress` for caption
    updates and waits for `done` to flip into the preview pane. Animation
    chapter timing is INDEPENDENT — captions update text only, not which
    SVG chapter is playing.

    We persist the answers so re-running the wizard can prefill, but we do
    NOT mark tutorial_completed here — that happens in /apply, after the
    user confirms.
    """
    user = await _require_user(jwt_user_id, db)
    user.onboarding_answers = answers.model_dump(mode="json")
    await db.flush()

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for kind, payload in config_generator.generate_with_progress(answers):
                if kind == "progress":
                    body = json.dumps({"caption": payload})
                    yield f"event: progress\ndata: {body}\n\n".encode("utf-8")
                elif kind == "done":
                    # payload is GeneratedConfig — serialize via pydantic
                    body = payload.model_dump_json() if isinstance(payload, GeneratedConfig) else json.dumps(payload)
                    yield f"event: done\ndata: {body}\n\n".encode("utf-8")
                elif kind == "error":
                    body = json.dumps({"message": str(payload)})
                    yield f"event: error\ndata: {body}\n\n".encode("utf-8")
        except asyncio.CancelledError:
            # Client navigated away mid-stream; nothing to do.
            raise
        except Exception as exc:  # pragma: no cover — defensive
            logger.exception("config_generator failed")
            body = json.dumps({"message": str(exc)})
            yield f"event: error\ndata: {body}\n\n".encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/apply")
async def apply_config(
    body: ApplyConfigRequest,
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Write the proposed config files and reload the domain config.

    Files in `body.raw_files` are keyed by path relative to CONFIG_DIR
    (e.g. "domain.yaml", "personas/cofounder.yaml"). Each is written
    verbatim. After all writes succeed, the loader re-reads from disk.

    Sets tutorial_completed=true on the calling user.
    """
    user = await _require_user(jwt_user_id, db)
    config_dir = _config_dir()

    # Reject path traversal — every key must resolve inside CONFIG_DIR.
    safe_writes: List[tuple[Path, str]] = []
    config_dir_resolved = config_dir.resolve()
    for rel, content in body.raw_files.items():
        candidate = (config_dir / rel).resolve()
        try:
            candidate.relative_to(config_dir_resolved)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid path '{rel}' — must be inside config dir",
            )
        safe_writes.append((candidate, content))

    try:
        for path, content in safe_writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    except OSError as exc:
        logger.exception("apply_config write failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write config files: {exc}",
        )

    # Reload the live domain config so subsequent /config/domain calls
    # serve the new content without a container restart.
    loader = get_loader()
    loader.load()

    user.tutorial_completed = True
    await db.flush()

    files_written = [str(p.relative_to(config_dir_resolved)) for p, _ in safe_writes]
    emit_event(
        "success", "wizard",
        f"Workbench applied — {len(files_written)} files written, config reloaded",
        meta={"files": files_written},
    )

    return {
        "applied": True,
        "files_written": files_written,
        "tutorial_completed": True,
    }


@router.get("/onboarding/me")
async def get_my_onboarding(
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return the calling user's onboarding state — used by the wizard
    on mount to prefill prior answers and decide whether to show first-run
    hints vs. a "re-personalize" framing."""
    user = await _require_user(jwt_user_id, db)
    return {
        "tutorial_completed": user.tutorial_completed,
        "onboarding_answers": user.onboarding_answers,
    }
