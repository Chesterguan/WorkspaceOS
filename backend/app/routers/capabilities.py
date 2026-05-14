"""Capability discovery + dispatch endpoints.

The frontend uses these to:
  - render the Settings → Capabilities tab (`GET /capabilities`)
  - merge slash_commands into the ⌘K palette (`GET /capabilities/slash-commands`)
  - render action buttons on knowledge nodes etc. (`GET /capabilities/actions?target=...`)
  - dispatch user clicks (`POST /capabilities/runners/{name}/trigger`
    and `POST /capabilities/actions/{name}/invoke`)

All POST endpoints require a JWT — actions mutate user-scoped data.
GET endpoints accept either JWT or X-API-Key.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities import actions as action_handlers
from app.capabilities import slash as slash_handlers
from app.capabilities.registry import INGEST_SOURCES
from app.dependencies import (
    get_db,
    get_optional_user_id,
    parse_jwt_user_uuid,
    verify_api_key,
)
from app.services import extensions as ext_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _serialize_capability(extension_id: str, cap) -> Dict[str, Any]:
    """Flatten a Capability + the source extension into the response shape."""
    runner_registered = False
    if cap.kind == "ingest_source":
        runner_registered = cap.name in INGEST_SOURCES
    elif cap.kind == "slash_command":
        target = cap.config.get("handler_target") if cap.config else None
        # api_call slash_commands resolve to a runner name; navigate ones don't.
        handler_kind = (cap.config or {}).get("handler_kind", "api_call")
        if handler_kind == "navigate":
            runner_registered = True  # nothing to register; route is data-only
        elif handler_kind == "api_call":
            runner_registered = bool(target) and (
                # The endpoint is the framework's responsibility — we trust it
                # if the manifest points at /capabilities/runners/<known-name>.
                target.startswith("/capabilities/runners/")
                and target.split("/")[-2] in slash_handlers.SLASH_RUNNERS
            )
    elif cap.kind == "action_button":
        runner_registered = cap.name in action_handlers.ACTION_HANDLERS

    return {
        "extension": extension_id,
        "kind": cap.kind,
        "name": cap.name,
        "description": cap.description,
        "config": cap.config or {},
        "runner_registered": runner_registered,
    }


@router.get("")
async def list_capabilities(
    _: str = Depends(verify_api_key),
) -> Dict[str, List[Dict[str, Any]]]:
    """Return every capability across every loaded extension, grouped by kind.

    Used by Settings → Capabilities tab. `runner_registered=false` means
    the manifest declared a capability but the framework has no handler
    for it — typically Phase 3 stuff or a typo in the manifest.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "ingest_source": [],
        "slash_command": [],
        "action_button": [],
        "surface_widget": [],
    }
    for ext in ext_service.get_all_extensions():
        for cap in ext.manifest.capabilities:
            entry = _serialize_capability(ext.manifest.id, cap)
            grouped.setdefault(cap.kind, []).append(entry)
    return grouped


@router.get("/slash-commands")
async def list_slash_commands(
    _: str = Depends(verify_api_key),
) -> List[Dict[str, Any]]:
    """Return active slash_command capabilities for the palette to render.

    Filters to entries whose runner is registered or which use the
    `navigate` handler kind (no backend code needed). Frontend merges
    these with its built-in palette items.
    """
    items: List[Dict[str, Any]] = []
    for ext in ext_service.get_all_extensions():
        for cap in ext.manifest.capabilities:
            if cap.kind != "slash_command":
                continue
            entry = _serialize_capability(ext.manifest.id, cap)
            if not entry["runner_registered"]:
                continue
            cfg = cap.config or {}
            items.append({
                "id": f"{ext.manifest.id}/{cap.name}",
                "name": cap.name,
                "label": cfg.get("label") or cap.name,
                "keywords": cfg.get("keywords") or [],
                "icon": cfg.get("icon"),
                "handler_kind": cfg.get("handler_kind", "api_call"),
                "handler_target": cfg.get("handler_target"),
                "source_extension": ext.manifest.id,
            })
    return items


@router.get("/actions")
async def list_actions(
    target: str = Query(..., description="Item kind: chat_message | knowledge_node | draft | paper | project"),
    _: str = Depends(verify_api_key),
) -> List[Dict[str, Any]]:
    """Return action_button capabilities that attach to the given target."""
    items: List[Dict[str, Any]] = []
    for ext in ext_service.get_all_extensions():
        for cap in ext.manifest.capabilities:
            if cap.kind != "action_button":
                continue
            cfg = cap.config or {}
            if cfg.get("target") != target:
                continue
            entry = _serialize_capability(ext.manifest.id, cap)
            if not entry["runner_registered"]:
                continue
            items.append({
                "id": f"{ext.manifest.id}/{cap.name}",
                "name": cap.name,
                "label": cfg.get("label") or cap.name,
                "icon": cfg.get("icon"),
                "target": cfg.get("target"),
                "visible_when": cfg.get("visible_when") or {},
                "source_extension": ext.manifest.id,
            })
    return items


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _require_user_id(jwt_user_id: Optional[str]):
    if not jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Capability dispatch requires a JWT (user-scoped action).",
        )
    return parse_jwt_user_uuid(jwt_user_id)


@router.post("/runners/{name}/trigger")
async def trigger_slash_runner(
    name: str,
    payload: Dict[str, Any],
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Invoke a registered slash_command runner by name."""
    user_id = _require_user_id(jwt_user_id)
    handler = slash_handlers.SLASH_RUNNERS.get(name)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"slash runner '{name}' is not registered",
        )
    try:
        return await handler(payload or {}, db, user_id)
    except Exception as exc:
        logger.exception("slash runner %s failed", name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"runner failed: {exc}",
        )


@router.post("/actions/{name}/invoke")
async def invoke_action(
    name: str,
    payload: Dict[str, Any],
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Invoke a registered action_button handler by name."""
    user_id = _require_user_id(jwt_user_id)
    handler = action_handlers.ACTION_HANDLERS.get(name)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"action '{name}' is not registered",
        )
    try:
        return await handler(payload or {}, db, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("action %s failed", name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"action failed: {exc}",
        )
