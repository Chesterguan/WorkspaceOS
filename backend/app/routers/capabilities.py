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
                "inputs": cfg.get("inputs") or [],
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


# ---------------------------------------------------------------------------
# Per-capability config — Settings → Configure form
# ---------------------------------------------------------------------------


def _find_capability(extension_id: str, capability_name: str):
    """Locate a capability by (extension_id, name). 404 if missing."""
    for ext in ext_service.get_all_extensions():
        if ext.manifest.id != extension_id:
            continue
        for cap in ext.manifest.capabilities:
            if cap.name == capability_name:
                return ext, cap
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"capability {extension_id}/{capability_name} not found",
    )


@router.get("/{extension_id}/{capability_name}/config")
async def get_capability_config(
    extension_id: str,
    capability_name: str,
    _: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Return the effective config for this capability, sensitive
    values masked. Frontend uses this to prefill the Configure form."""
    from app.services import capability_settings_service as cs
    _, cap = _find_capability(extension_id, capability_name)
    overlay = await cs.get_overlay(extension_id, capability_name)
    effective = cs.effective_config(cap.config or {}, overlay)
    return {
        "extension_id": extension_id,
        "capability_name": capability_name,
        "config": cs.redact_for_display(effective),
        # Which keys came from the user vs the manifest. Lets the
        # frontend show a "saved" indicator on overlaid fields.
        "overlay_keys": sorted(overlay.keys()),
    }


@router.put("/{extension_id}/{capability_name}/config")
async def put_capability_config(
    extension_id: str,
    capability_name: str,
    payload: Dict[str, Any],
    _: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Write the config overlay. Encrypted at rest.

    Behavior: if a sensitive field comes through as exactly "***" we
    treat it as "keep existing" — the frontend doesn't have the real
    value (we redacted on GET), so it would otherwise overwrite a real
    key with a literal "***".
    """
    from app.services import capability_settings_service as cs
    _, cap = _find_capability(extension_id, capability_name)
    existing = await cs.get_overlay(extension_id, capability_name)

    cleaned: Dict[str, Any] = {}
    manifest_config = cap.config or {}
    for k, v in (payload.get("config") or {}).items():
        if k in cs.SENSITIVE_KEYS and v == "***":
            # Preserve existing value for fields the UI displayed as
            # masked.
            if k in existing:
                cleaned[k] = existing[k]
            continue
        # Type-coerce based on the manifest's default for this field.
        # Frontend `<input type=text>` always sends strings; storing
        # "30" as the poll interval would break runners that do int
        # arithmetic on the value.
        #
        # Guardrails:
        #   - Bound input length before int/float parsing. Python 3.11+
        #     caps int() at 4300 digits by default but a 4299-digit string
        #     still parses in O(n^2); float("1e9999") = inf which then
        #     gets stored and could cause issues downstream.
        #   - Reject non-finite floats (inf, -inf, nan).
        #   - If the manifest has no default for this key, conservatively
        #     attempt int/bool coercion from common patterns so brand-new
        #     overlay-only fields don't silently store strings.
        default = manifest_config.get(k)
        if isinstance(v, str) and len(v) > 64:
            # Anything longer than 64 chars isn't a number/bool the user
            # typed into a config input — store as-is and let validation
            # downstream handle it.
            cleaned[k] = v
            continue
        if isinstance(default, bool) and isinstance(v, str):
            v = v.strip().lower() in ("true", "1", "yes")
        elif isinstance(default, int) and not isinstance(default, bool) and isinstance(v, str):
            try:
                v = int(v.strip())
            except (TypeError, ValueError):
                pass
        elif isinstance(default, float) and isinstance(v, str):
            try:
                parsed = float(v.strip())
                import math as _math
                if _math.isnan(parsed) or _math.isinf(parsed):
                    # nan/inf/-inf — reject by leaving the original string
                    pass
                else:
                    v = parsed
            except (TypeError, ValueError):
                pass
        elif isinstance(default, (list, dict)) and isinstance(v, str):
            # The form serialises list/dict values as JSON. Parse it back
            # if we can; otherwise keep as a string and let the runner
            # surface the type mismatch.
            try:
                import json as _json
                parsed = _json.loads(v)
                if isinstance(parsed, type(default)):
                    v = parsed
            except (TypeError, ValueError):
                pass
        elif default is None and isinstance(v, str):
            # No manifest default — best-effort coercion from string for
            # the most common cases so overlay-only fields don't drift.
            stripped = v.strip()
            if stripped.lower() in ("true", "false"):
                v = stripped.lower() == "true"
            elif stripped.lstrip("-").isdigit() and len(stripped) < 20:
                try:
                    v = int(stripped)
                except (TypeError, ValueError):
                    pass
        cleaned[k] = v

    await cs.set_overlay(extension_id, capability_name, cleaned)
    return {"saved": True, "overlay_keys": sorted(cleaned.keys())}


@router.post("/{extension_id}/{capability_name}/test")
async def test_capability_config(
    extension_id: str,
    capability_name: str,
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
    _: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Run the capability once with current effective config; report
    success / failure. Returns the same shape as the runner's run()
    plus a `success` boolean."""
    from app.capabilities.base import IngestContext
    from app.capabilities.registry import INGEST_SOURCES
    from app.services import capability_settings_service as cs

    _, cap = _find_capability(extension_id, capability_name)
    if cap.kind != "ingest_source":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test is only supported for ingest_source capabilities.",
        )
    runner_cls = INGEST_SOURCES.get(cap.name)
    if runner_cls is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"runner {cap.name!r} not registered",
        )

    user_id = parse_jwt_user_uuid(jwt_user_id) if jwt_user_id else None
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Test requires a JWT (results attribute to your user).",
        )

    overlay = await cs.get_overlay(extension_id, capability_name)
    effective = cs.effective_config(cap.config or {}, overlay)

    runner = runner_cls()
    ctx = IngestContext(user_id=user_id, source=f"{extension_id}:{cap.name}:test")
    try:
        count = await runner.run(effective, ctx)
        return {"success": True, "ingested": count,
                "message": f"Test tick succeeded — {count} new item(s)."}
    except Exception as exc:
        logger.exception("test_capability_config failed")
        return {"success": False, "ingested": 0, "message": str(exc)}


@router.post("/{extension_id}/{capability_name}/auto-fill")
async def auto_fill_capability_config(
    extension_id: str,
    capability_name: str,
    payload: Dict[str, Any],
    _: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Given a partial config (typically just an API key), introspect
    the provider's own API to derive other fields. Currently supports:

      zotero_sync: api_key → library_id + library_type

    Returns {derived: {...}, message: "..."}. Frontend merges
    `derived` into the form. Auto-fill is opt-in — user clicks the
    button. We never auto-save.
    """
    import httpx
    if capability_name == "zotero_sync":
        api_key = (payload.get("config") or {}).get("api_key", "").strip()
        if not api_key or api_key == "***":
            return {"derived": {}, "message": "Provide an api_key first."}
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://api.zotero.org/keys/{api_key}",
                headers={"Zotero-API-Version": "3"},
            )
        if r.status_code != 200:
            return {"derived": {}, "message": f"Zotero auth failed ({r.status_code})."}
        data = r.json()
        user_id = str(data.get("userID") or "").strip()
        if not user_id:
            return {"derived": {}, "message": "Zotero key valid but no userID returned."}
        return {
            "derived": {"library_id": user_id, "library_type": "user"},
            "message": f"Resolved library_id = {user_id} (user library).",
        }
    return {
        "derived": {},
        "message": "Auto-fill isn't supported for this capability — fill the fields by hand.",
    }
