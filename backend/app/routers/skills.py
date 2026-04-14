"""
Skills router — user-triggered ingest jobs that pull external data into
project-scoped memory. Currently one skill: Google Calendar.

Each skill exposes:
  GET  /skills/<name>/status   — connected + last run summary
  POST /skills/<name>/sync     — run the ingest cycle now

We keep it deliberately flat (one path per skill) rather than a generic
/skills/{name}/sync. That lets the OpenAPI schema document each skill's
response shape explicitly and makes failure modes easier to diagnose.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_db,
    get_optional_user_id,
    parse_jwt_user_uuid,
    verify_api_key,
)
from app.services import (
    google_calendar_service,
    google_oauth_service,
    microsoft_oauth_service,
    outlook_calendar_service,
    outlook_mail_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["skills"])


def _require_user(jwt_user_id: Optional[str]):
    """Skills are per-user — require JWT, don't fall back to admin mode."""
    if not jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Skills require JWT authentication (tokens are per-user).",
        )
    return parse_jwt_user_uuid(jwt_user_id)


@router.get("/google-calendar/status", summary="Google Calendar skill status")
async def google_calendar_status(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    user_id = _require_user(jwt_user_id)
    connected = await google_oauth_service.is_connected(user_id, db)
    return {"skill": "google-calendar", "connected": connected}


@router.post(
    "/google-calendar/sync",
    summary="Ingest recent Google Calendar events now",
)
async def google_calendar_sync(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """
    Pull events from -7d to +14d, classify each into one of the user's
    projects (Inbox fallback for low-confidence), store as memory entries,
    emit one `ingest.calendar` activity event per newly stored event.
    Idempotent: re-running only ingests events we haven't seen before.
    """
    user_id = _require_user(jwt_user_id)
    try:
        summary = await google_calendar_service.ingest_recent(user_id, db)
    except RuntimeError as exc:
        # Service raises RuntimeError for known failure modes (not connected,
        # fetch blew up). Surface cleanly as 502/409.
        message = str(exc)
        code = (
            status.HTTP_409_CONFLICT
            if "not connected" in message.lower()
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=message)
    # ingest_recent only staged writes via db.flush(); make them durable.
    await db.commit()
    return summary


# ---------------------------------------------------------------------------
# Outlook Calendar (Microsoft Graph)
# ---------------------------------------------------------------------------

@router.get("/outlook-calendar/status", summary="Outlook Calendar skill status")
async def outlook_calendar_status(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    user_id = _require_user(jwt_user_id)
    connected = await microsoft_oauth_service.is_connected(user_id, db)
    return {"skill": "outlook-calendar", "connected": connected}


@router.post(
    "/outlook-calendar/sync",
    summary="Ingest recent Outlook calendar events now",
)
async def outlook_calendar_sync(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """Window and classification behaviour mirror the Google Calendar path.
    Uses the same MemoryEntry / activity-feed sinks so the result shape is
    identical and the UI can share handling."""
    user_id = _require_user(jwt_user_id)
    try:
        summary = await outlook_calendar_service.ingest_recent(user_id, db)
    except RuntimeError as exc:
        message = str(exc)
        code = (
            status.HTTP_409_CONFLICT
            if "not connected" in message.lower()
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=message)
    await db.commit()
    return summary


# ---------------------------------------------------------------------------
# Outlook Mail (Microsoft Graph)
# ---------------------------------------------------------------------------

@router.get("/outlook-mail/status", summary="Outlook Mail skill status")
async def outlook_mail_status(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    user_id = _require_user(jwt_user_id)
    connected = await microsoft_oauth_service.is_connected(user_id, db)
    return {"skill": "outlook-mail", "connected": connected}


@router.post(
    "/outlook-mail/sync",
    summary="Ingest recent Outlook messages now",
)
async def outlook_mail_sync(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    user_id = _require_user(jwt_user_id)
    try:
        summary = await outlook_mail_service.ingest_recent(user_id, db)
    except RuntimeError as exc:
        message = str(exc)
        code = (
            status.HTTP_409_CONFLICT
            if "not connected" in message.lower()
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=code, detail=message)
    await db.commit()
    return summary
