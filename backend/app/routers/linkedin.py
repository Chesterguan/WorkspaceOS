"""
LinkedIn OAuth router.

Endpoints:
  GET /linkedin/auth      — Return the OAuth authorization URL for the frontend.
  GET /linkedin/callback  — OAuth redirect target; exchanges code for token.
  GET /linkedin/status    — Check whether a LinkedIn token is stored and valid.

Tokens are per-user: the OAuth ``state`` parameter carries a signed JWT
identifying the initiating user so the callback can persist the token on
the correct ``users.linkedin_access_token`` row. Cross-user leakage is
prevented by always scoping /status and /disconnect by the JWT user.
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
from app.services import linkedin_service
from app.services.auth_service import (
    create_oauth_state_token,
    decode_oauth_state_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linkedin", tags=["linkedin"])

_LINKEDIN_STATE_PURPOSE = "linkedin_connect"


# ---------------------------------------------------------------------------
# Auth URL
# ---------------------------------------------------------------------------

@router.get(
    "/auth",
    summary="Get LinkedIn OAuth authorization URL",
)
async def get_auth_url(
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """
    Return the LinkedIn OAuth 2.0 authorization URL.

    Requires authentication — the caller's user ID is embedded in a signed
    ``state`` token so that the callback can attach the resulting access
    token to the correct user. API-key callers get None (legacy single-user
    mode) and skip the state parameter.
    """
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "LinkedIn OAuth is not configured. "
                "Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your environment."
            ),
        )
    state = None
    if jwt_user_id:
        state = create_oauth_state_token(jwt_user_id, _LINKEDIN_STATE_PURPOSE)
    url = linkedin_service.get_auth_url(state=state)
    return {"url": url}


# ---------------------------------------------------------------------------
# OAuth callback
# ---------------------------------------------------------------------------

@router.get(
    "/callback",
    response_class=HTMLResponse,
    summary="LinkedIn OAuth callback",
    include_in_schema=False,  # Not a public API endpoint; only LinkedIn calls this
)
async def oauth_callback(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """
    Handle the OAuth redirect from LinkedIn.

    Verifies the signed ``state`` token to identify the initiating user,
    exchanges the code for an access token, and persists the token on that
    user's row. Returns an HTML page the popup window can close.
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description", "")

    if error:
        logger.warning("LinkedIn OAuth error: %s — %s", error, error_description)
        return HTMLResponse(
            content=_html_page(
                title="LinkedIn Connection Failed",
                body=f"<p>OAuth error: <strong>{html.escape(error)}</strong></p>"
                     f"<p>{html.escape(error_description)}</p>"
                     "<p>You can close this window and try again.</p>",
                success=False,
            ),
            status_code=200,
        )

    if not code:
        return HTMLResponse(
            content=_html_page(
                title="LinkedIn Connection Failed",
                body="<p>No authorization code was received. You can close this window and try again.</p>",
                success=False,
            ),
            status_code=200,
        )

    if not state:
        logger.warning("LinkedIn OAuth callback missing state parameter")
        return HTMLResponse(
            content=_html_page(
                title="LinkedIn Connection Failed",
                body="<p>Missing OAuth state. Please start the connection flow again.</p>",
                success=False,
            ),
            status_code=200,
        )

    user_id_str = decode_oauth_state_token(state, _LINKEDIN_STATE_PURPOSE)
    if not user_id_str:
        logger.warning("LinkedIn OAuth state token invalid or expired")
        return HTMLResponse(
            content=_html_page(
                title="LinkedIn Connection Failed",
                body="<p>OAuth state token is invalid or expired. Please start the connection flow again.</p>",
                success=False,
            ),
            status_code=200,
        )

    try:
        user_uuid = uuid.UUID(user_id_str)
        await linkedin_service.exchange_code(code, user_id=user_uuid, db=db)
        await db.commit()
    except Exception as exc:
        logger.exception("LinkedIn token exchange failed: %s", exc)
        return HTMLResponse(
            content=_html_page(
                title="LinkedIn Connection Failed",
                body=f"<p>Failed to exchange authorization code: {html.escape(str(exc))}</p>"
                     "<p>You can close this window and try again.</p>",
                success=False,
            ),
            status_code=200,
        )

    logger.info("LinkedIn OAuth flow completed for user %s", user_id_str)
    return HTMLResponse(
        content=_html_page(
            title="LinkedIn Connected",
            body="<p>Connected! You can close this window.</p>",
            success=True,
        ),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Status check
# ---------------------------------------------------------------------------

@router.get(
    "/status",
    summary="Check LinkedIn connection status",
)
async def get_status(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """
    Return whether a LinkedIn access token is stored for the authenticated
    user. API-key callers see the first user's token (admin/legacy).

    Response: { connected: bool }
    """
    if jwt_user_id:
        token = await linkedin_service.load_token_for_user(
            parse_jwt_user_uuid(jwt_user_id), db
        )
    else:
        # Admin / API key — look at the first user (legacy behavior)
        from sqlalchemy import select
        from app.models.user import User
        result = await db.execute(
            select(User).order_by(User.created_at.asc()).limit(1)
        )
        user = result.scalar_one_or_none()
        token = user.linkedin_access_token if user else None

    return {"connected": bool(token)}


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

@router.post(
    "/disconnect",
    summary="Disconnect LinkedIn (clear stored token)",
)
async def disconnect(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> dict:
    """
    Clear the stored LinkedIn access token for the authenticated user.

    Response: { disconnected: true }
    """
    if jwt_user_id:
        try:
            await linkedin_service.persist_token_for_user(
                parse_jwt_user_uuid(jwt_user_id), None, db
            )
            await db.commit()
        except Exception as exc:
            logger.warning("Could not clear LinkedIn token for user %s: %s", jwt_user_id, exc)
    else:
        # Admin / API key — clear the first user (legacy behavior)
        try:
            from sqlalchemy import select
            from app.models.user import User
            result = await db.execute(
                select(User).order_by(User.created_at.asc()).limit(1)
            )
            user = result.scalar_one_or_none()
            if user and user.linkedin_access_token:
                user.linkedin_access_token = None
                await db.commit()
        except Exception as exc:
            logger.warning("Could not clear LinkedIn token (admin mode): %s", exc)

    return {"disconnected": True}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _html_page(title: str, body: str, success: bool) -> str:
    """Minimal HTML page returned to the OAuth popup window."""
    color = "#22c55e" if success else "#ef4444"
    icon = "&#x2713;" if success else "&#x2717;"
    safe_title = html.escape(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_title}</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #0f172a;
      color: #e2e8f0;
    }}
    .card {{
      text-align: center;
      padding: 2rem 3rem;
      background: #1e293b;
      border-radius: 12px;
      border: 1px solid #334155;
      max-width: 400px;
    }}
    .icon {{
      font-size: 3rem;
      color: {color};
      margin-bottom: 1rem;
    }}
    h1 {{ font-size: 1.25rem; margin: 0 0 1rem; color: {color}; }}
    p {{ color: #94a3b8; margin: 0.5rem 0; font-size: 0.9rem; }}
    strong {{ color: #e2e8f0; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{safe_title}</h1>
    {body}
  </div>
</body>
</html>"""
