"""
Google OAuth 2.0 service — one token per user, multi-scope.

Design:
  * Tokens live in `user_oauth_tokens(user_id, provider='google', ...)`,
    Fernet-encrypted. No per-scope rows — one Google connection covers
    Calendar (today) and Gmail / Drive (future).
  * `load_valid_token_for_user` auto-refreshes when `expires_at` is within
    60 s — callers never see an expired token.
  * We depend on `httpx` only (already installed). No `google-auth` dance
    for the token lifecycle itself — it's three HTTPS calls and clearer
    to own. `google-api-python-client` will handle the *API* calls
    (Calendar, Gmail) in separate services; those can be constructed from
    a raw access_token via `google.oauth2.credentials.Credentials`.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user_oauth_token import UserOAuthToken
from app.services.encryption import decrypt, encrypt

logger = logging.getLogger(__name__)

PROVIDER = "google"

# Scopes requested on first connect. Calendar read-only for v1; email/openid
# give us the connected Google account's identity (shown on the settings
# card) without any API surface beyond the token endpoint itself.
_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Buffer for the auto-refresh check — if the token expires within this
# window we refresh proactively rather than serving an almost-dead token.
_EXPIRY_BUFFER_SECONDS = 60


# ---------------------------------------------------------------------------
# Auth URL
# ---------------------------------------------------------------------------

def get_auth_url(state: Optional[str] = None) -> str:
    """Build the Google OAuth consent URL. access_type=offline + prompt=consent
    ensures we get a refresh_token on first connect AND on reconnects."""
    if not settings.google_client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "access_type": "offline",
        # prompt=consent is needed every time to guarantee a refresh_token;
        # Google only returns one on the FIRST consent by default.
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    if state:
        params["state"] = state
    return f"{_AUTH_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Code exchange (first-time connect)
# ---------------------------------------------------------------------------

async def exchange_code(
    code: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> UserOAuthToken:
    """Swap an auth code for tokens and persist (or update) the user's row."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise RuntimeError("Google OAuth not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Google token exchange failed ({resp.status_code}): {resp.text[:300]}"
            )
        payload = resp.json()

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")  # seconds
    granted_scopes = payload.get("scope", "")
    if not access_token:
        raise RuntimeError("Google response missing access_token")

    expires_at: Optional[datetime] = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # Upsert semantics — a user reconnecting must overwrite their row, not
    # spawn a second. The (user_id, provider) unique constraint would
    # enforce this at the DB level but we do a SELECT-then-update so we
    # never lose a valid refresh_token when Google chooses not to re-issue
    # one (re-consent usually does, but belt + suspenders).
    existing = await _load_row(user_id, db)
    if existing is not None:
        existing.access_token = encrypt(access_token)
        if refresh_token:
            existing.refresh_token = encrypt(refresh_token)
        existing.expires_at = expires_at
        existing.scopes = granted_scopes
        await db.flush()
        await db.refresh(existing)
        logger.info("google oauth: refreshed token row for user %s", user_id)
        return existing

    row = UserOAuthToken(
        user_id=user_id,
        provider=PROVIDER,
        access_token=encrypt(access_token),
        refresh_token=encrypt(refresh_token) if refresh_token else None,
        expires_at=expires_at,
        scopes=granted_scopes,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    logger.info("google oauth: created token row for user %s", user_id)
    return row


# ---------------------------------------------------------------------------
# Refresh + load
# ---------------------------------------------------------------------------

async def _refresh_access_token(row: UserOAuthToken, db: AsyncSession) -> str:
    """Use the refresh_token to mint a new access_token; persist and return
    the plaintext access token."""
    if not row.refresh_token:
        raise RuntimeError("No refresh_token stored; user must reconnect Google")

    refresh_plain = decrypt(row.refresh_token)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_plain,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            # 400/401 here usually means the refresh_token was revoked —
            # surface clearly so the caller can tell the user to reconnect.
            raise RuntimeError(
                f"Google refresh failed ({resp.status_code}): {resp.text[:300]}"
            )
        payload = resp.json()

    new_access = payload.get("access_token")
    if not new_access:
        raise RuntimeError("Google refresh response missing access_token")
    expires_in = payload.get("expires_in")
    new_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if expires_in else None
    )

    row.access_token = encrypt(new_access)
    row.expires_at = new_expires_at
    # Google sometimes returns a rotated refresh_token; keep the old one
    # otherwise. Never clear a working refresh_token on refresh.
    rotated = payload.get("refresh_token")
    if rotated:
        row.refresh_token = encrypt(rotated)
    await db.flush()
    return new_access


async def _load_row(user_id: uuid.UUID, db: AsyncSession) -> Optional[UserOAuthToken]:
    result = await db.execute(
        select(UserOAuthToken).where(
            UserOAuthToken.user_id == user_id,
            UserOAuthToken.provider == PROVIDER,
        )
    )
    return result.scalar_one_or_none()


async def load_valid_token_for_user(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[str]:
    """
    Return a plaintext access_token for the user, refreshing if expired.
    Returns None when the user has never connected or when the refresh
    path fails (caller should prompt reconnect).
    """
    row = await _load_row(user_id, db)
    if row is None:
        return None

    now = datetime.now(timezone.utc)
    needs_refresh = (
        row.expires_at is not None
        and row.expires_at <= now + timedelta(seconds=_EXPIRY_BUFFER_SECONDS)
    )
    if needs_refresh:
        try:
            return await _refresh_access_token(row, db)
        except Exception as exc:
            logger.warning("google oauth: refresh failed for %s: %s", user_id, exc)
            return None

    try:
        return decrypt(row.access_token)
    except Exception as exc:
        logger.warning("google oauth: decrypt failed for %s: %s", user_id, exc)
        return None


async def disconnect(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Delete the user's Google token row. Returns True if a row existed."""
    row = await _load_row(user_id, db)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    logger.info("google oauth: disconnected user %s", user_id)
    return True


async def is_connected(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Cheap boolean — does this user have a token row at all."""
    return (await _load_row(user_id, db)) is not None
