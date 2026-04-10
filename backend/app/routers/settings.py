"""
Settings router: manage API keys via the UI.

Keys are Fernet-encrypted in the app_settings table. Endpoints let the
frontend list configured keys (masked), save new values, and delete keys.
Also provides database backup endpoints.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_admin
from app.schemas.settings import KeysStatusResponse, KeyStatus, SetKeysRequest
from app.services import settings_service
from app.services.settings_service import SETTINGS_KEY_MAP, _mask_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/usage",
    summary="Get AI usage stats (admin only)",
)
async def get_usage(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_admin),
) -> dict:
    """Return AI usage statistics: today, this week, this month, by provider."""
    from app.services.usage_service import get_usage_stats
    return await get_usage_stats(db)


@router.get(
    "/keys",
    response_model=KeysStatusResponse,
    summary="List all API key statuses (admin only)",
)
async def list_keys(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_admin),
) -> KeysStatusResponse:
    """Return all recognized keys with masked values and source indicators.

    For each key in SETTINGS_KEY_MAP:
    1. Check if stored in DB (source='db', masked from DB value).
    2. If not in DB, check if set in .env (non-empty on settings object).
    3. Skip keys that are not configured anywhere.
    """
    db_keys = await settings_service.get_all_keys(db)
    db_map = {k["key"]: k for k in db_keys}

    result = []
    for key_name, settings_attr in SETTINGS_KEY_MAP.items():
        if key_name in db_map:
            entry = db_map[key_name]
            result.append(KeyStatus(
                key=key_name,
                masked_value=entry["masked_value"],
                updated_at=entry["updated_at"],
                source="db",
            ))
        else:
            # Check if set via .env / runtime settings
            env_value = getattr(settings, settings_attr, "")
            if env_value:
                result.append(KeyStatus(
                    key=key_name,
                    masked_value=_mask_value(env_value),
                    source="env",
                ))
            else:
                # Show unconfigured keys so the user knows to set them
                result.append(KeyStatus(
                    key=key_name,
                    masked_value="Not set",
                    source="env",
                ))

    return KeysStatusResponse(keys=result)


@router.put(
    "/keys",
    response_model=KeysStatusResponse,
    summary="Save one or more API keys (admin only)",
)
async def save_keys(
    body: SetKeysRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_admin),
) -> KeysStatusResponse:
    """Encrypt and store keys, then reload into runtime settings."""
    for key_name, value in body.keys.items():
        if key_name not in SETTINGS_KEY_MAP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unrecognized key: {key_name}",
            )
        await settings_service.set_key(key_name, value, db)

    # Apply to runtime immediately
    loaded = await settings_service.load_db_keys_into_settings(db)
    logger.info("Saved %d key(s), %d loaded into runtime", len(body.keys), loaded)

    # Return updated status — call list_keys directly (both paths are admin-only)
    return await list_keys(db=db, _key=_key)  # type: ignore[arg-type]


@router.delete(
    "/keys/{key_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API key from the database (admin only)",
)
async def delete_key(
    key_name: str,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(require_admin),
) -> None:
    """Remove a key from DB. The .env fallback value (if any) takes effect."""
    if key_name not in SETTINGS_KEY_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unrecognized key: {key_name}",
        )
    deleted = await settings_service.delete_key(key_name, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Key '{key_name}' not found in database",
        )


# ---------------------------------------------------------------------------
# Database backup endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/backup",
    summary="Trigger a manual database backup (admin only)",
)
async def trigger_backup(
    _key: str = Depends(require_admin),
) -> dict:
    """Run pg_dump and save to the backup directory."""
    import subprocess
    try:
        result = subprocess.run(
            ["bash", "/app/scripts/backup.sh"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            return {"success": True, "message": lines[-1] if lines else "Backup complete"}
        return {"success": False, "error": result.stderr[:200]}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get(
    "/backups",
    summary="List available database backups (admin only)",
)
async def list_backups(
    _key: str = Depends(require_admin),
) -> dict:
    """List all backup files with sizes and dates."""
    import os
    from pathlib import Path

    backup_dir = Path("/app/backend_data/backups")
    if not backup_dir.exists():
        return {"backups": []}

    backups = []
    for f in sorted(backup_dir.glob("projectscribe_*.sql.gz"), reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "size_human": f"{stat.st_size / 1024 / 1024:.1f} MB" if stat.st_size > 1024 * 1024 else f"{stat.st_size / 1024:.1f} KB",
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return {"backups": backups}
