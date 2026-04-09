"""
LinkedIn OAuth router.

Endpoints:
  GET /linkedin/auth      — Return the OAuth authorization URL for the frontend.
  GET /linkedin/callback  — OAuth redirect target; exchanges code for token.
  GET /linkedin/status    — Check whether a LinkedIn token is stored and valid.
"""
import html
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.services import linkedin_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linkedin", tags=["linkedin"])


# ---------------------------------------------------------------------------
# Auth URL
# ---------------------------------------------------------------------------

@router.get(
    "/auth",
    summary="Get LinkedIn OAuth authorization URL",
)
async def get_auth_url() -> dict:
    """
    Return the LinkedIn OAuth 2.0 authorization URL.

    The frontend should open this URL (e.g. in a popup or redirect) to
    start the OAuth flow. After the user authorizes, LinkedIn will redirect
    to the configured callback URL.
    """
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "LinkedIn OAuth is not configured. "
                "Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your environment."
            ),
        )
    url = linkedin_service.get_auth_url()
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

    Exchanges the authorization code for an access token and stores it.
    Returns a small HTML page the user can close.
    """
    code = request.query_params.get("code")
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

    try:
        await linkedin_service.exchange_code(code, db=db)
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

    logger.info("LinkedIn OAuth flow completed successfully.")
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
async def get_status(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Return whether a LinkedIn access token is stored and the associated
    profile name when available.

    Response: { connected: bool, name?: str }
    """
    token = linkedin_service.get_stored_token()
    if not token:
        # Try loading from DB (e.g. after container restart)
        token = await linkedin_service.load_token_from_db(db)
    if not token:
        return {"connected": False}

    # We have a token — report connected. Profile lookup requires extra scopes
    # (openid/profile) that may not be approved, so we skip it and just confirm
    # the token exists. If it's expired, the publish call will surface the error.
    return {"connected": True}


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

@router.post(
    "/disconnect",
    summary="Disconnect LinkedIn (clear stored token)",
)
async def disconnect(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Clear the stored LinkedIn access token from both the in-memory cache and
    the database, effectively disconnecting the account.

    Response: { disconnected: true }
    """
    linkedin_service.clear_token()

    # Also wipe the persisted token in the DB so it does not reload on restart
    try:
        from sqlalchemy import select
        from app.models.user import User
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if user and user.linkedin_access_token:
            user.linkedin_access_token = None
            await db.commit()
            logger.info("LinkedIn access token removed from database.")
    except Exception as exc:
        logger.warning("Could not clear LinkedIn token from DB: %s", exc)

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
