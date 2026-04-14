"""
Microsoft Graph OAuth router — clone of routers/google_oauth.py with
different service + state-purpose. See that file's docstring for the
per-user state-token reasoning.
"""
import html
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_db,
    get_optional_user_id,
    parse_jwt_user_uuid,
    verify_api_key,
)
from app.services import microsoft_oauth_service
from app.services.auth_service import (
    create_oauth_state_token,
    decode_oauth_state_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/microsoft", tags=["microsoft"])

_STATE_PURPOSE = "microsoft_connect"


def _html_page(title: str, body: str, success: bool) -> str:
    colour = "#16a34a" if success else "#dc2626"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:460px;margin:48px auto;
padding:24px;color:#111}}h1{{color:{colour};font-size:18px;margin:0 0 12px}}
p{{line-height:1.5}}</style></head>
<body><h1>{html.escape(title)}</h1>{body}</body></html>"""


def _config_guard() -> None:
    if not settings.ms_client_id or not settings.ms_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Microsoft OAuth is not configured. "
                "Set MS_CLIENT_ID and MS_CLIENT_SECRET in your environment."
            ),
        )


@router.get("/auth", summary="Get Microsoft OAuth authorization URL")
async def get_auth_url(
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    _config_guard()
    if not jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication required to connect Microsoft.",
        )
    state = create_oauth_state_token(jwt_user_id, _STATE_PURPOSE)
    return {"url": microsoft_oauth_service.get_auth_url(state=state)}


@router.get(
    "/callback",
    response_class=HTMLResponse,
    summary="Microsoft OAuth callback",
    include_in_schema=False,
)
async def oauth_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description", "")

    if error:
        logger.warning("Microsoft OAuth error: %s — %s", error, error_description)
        return HTMLResponse(
            _html_page(
                "Microsoft Connection Failed",
                f"<p>OAuth error: <strong>{html.escape(error)}</strong></p>"
                f"<p>{html.escape(error_description)}</p>",
                success=False,
            ),
            status_code=200,
        )
    if not code:
        return HTMLResponse(
            _html_page("Microsoft Connection Failed",
                       "<p>No authorization code received.</p>", success=False),
            status_code=200,
        )
    if not state:
        return HTMLResponse(
            _html_page("Microsoft Connection Failed",
                       "<p>Missing OAuth state. Restart the flow.</p>", success=False),
            status_code=200,
        )
    user_id_str = decode_oauth_state_token(state, _STATE_PURPOSE)
    if not user_id_str:
        return HTMLResponse(
            _html_page("Microsoft Connection Failed",
                       "<p>OAuth state invalid or expired.</p>", success=False),
            status_code=200,
        )
    try:
        user_uuid = uuid.UUID(user_id_str)
        await microsoft_oauth_service.exchange_code(code, user_id=user_uuid, db=db)
        await db.commit()
    except Exception as exc:
        logger.exception("Microsoft token exchange failed: %s", exc)
        return HTMLResponse(
            _html_page(
                "Microsoft Connection Failed",
                f"<p>Failed to exchange authorization code: {html.escape(str(exc))}</p>",
                success=False,
            ),
            status_code=200,
        )

    logger.info("Microsoft OAuth flow completed for user %s", user_id_str)
    return HTMLResponse(
        _html_page("Microsoft Connected",
                   "<p>Connected! You can close this window.</p>", success=True),
        status_code=200,
    )


@router.get("/status", summary="Check Microsoft connection status")
async def get_status(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    if not jwt_user_id:
        return {"connected": False}
    uid = parse_jwt_user_uuid(jwt_user_id)
    return {"connected": await microsoft_oauth_service.is_connected(uid, db)}


@router.post("/disconnect", summary="Disconnect Microsoft account")
async def post_disconnect(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    if not jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication required.",
        )
    uid = parse_jwt_user_uuid(jwt_user_id)
    removed = await microsoft_oauth_service.disconnect(uid, db)
    await db.commit()
    return {"disconnected": removed}
