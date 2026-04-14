"""
Microsoft Graph OAuth 2.0 — one token per user, multi-scope.

Structural clone of google_oauth_service.py; the OAuth spec is the same
three HTTPS calls, the differences are:
  * Auth/token endpoints on login.microsoftonline.com
  * Tenant = "common" so personal @outlook.com AND work @company.com both
    work through a single app registration
  * Scopes include `offline_access` to get a refresh token (Google uses
    access_type=offline instead — same intent, different spelling)
  * Token row stored with provider="microsoft" in user_oauth_tokens so
    it coexists with the google row (one per user per provider).
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

PROVIDER = "microsoft"

# Scopes for v1: Calendar + Mail read-only. Teams chat (Chat.Read) lands
# in the follow-up commit so the first rollout has a smaller consent
# surface. offline_access is required to get a refresh_token.
_SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Calendars.Read",
    "Mail.Read",
]

# "common" accepts both personal Microsoft accounts and work/school
# accounts. If the user later wants to lock to their org's tenant,
# swap in the tenant GUID here.
_TENANT = "common"
_AUTH_URL = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/authorize"
_TOKEN_URL = f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token"

_EXPIRY_BUFFER_SECONDS = 60


# ---------------------------------------------------------------------------
# Auth URL
# ---------------------------------------------------------------------------

def get_auth_url(state: Optional[str] = None) -> str:
    """Build Microsoft's OAuth consent URL. `prompt=consent` guarantees a
    refresh_token every time (Microsoft, like Google, only issues one on
    first consent unless you force-prompt)."""
    if not settings.ms_client_id:
        raise RuntimeError("MS_CLIENT_ID is not configured")
    params = {
        "client_id": settings.ms_client_id,
        "redirect_uri": settings.ms_redirect_uri,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "response_mode": "query",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{_AUTH_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Code exchange
# ---------------------------------------------------------------------------

async def exchange_code(
    code: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> UserOAuthToken:
    if not settings.ms_client_id or not settings.ms_client_secret:
        raise RuntimeError("Microsoft OAuth not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.ms_client_id,
                "client_secret": settings.ms_client_secret,
                "redirect_uri": settings.ms_redirect_uri,
                "grant_type": "authorization_code",
                # Microsoft requires scope on the token call too
                "scope": " ".join(_SCOPES),
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Microsoft token exchange failed ({resp.status_code}): {resp.text[:300]}"
            )
        payload = resp.json()

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    granted_scopes = payload.get("scope", "")
    if not access_token:
        raise RuntimeError("Microsoft response missing access_token")

    expires_at: Optional[datetime] = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # Upsert — same pattern as Google: preserve existing refresh_token if
    # Microsoft declines to re-issue on reconnect (rare but possible).
    existing = await _load_row(user_id, db)
    if existing is not None:
        existing.access_token = encrypt(access_token)
        if refresh_token:
            existing.refresh_token = encrypt(refresh_token)
        existing.expires_at = expires_at
        existing.scopes = granted_scopes
        await db.flush()
        await db.refresh(existing)
        logger.info("microsoft oauth: refreshed token row for user %s", user_id)
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
    logger.info("microsoft oauth: created token row for user %s", user_id)
    return row


# ---------------------------------------------------------------------------
# Refresh + load
# ---------------------------------------------------------------------------

async def _refresh_access_token(row: UserOAuthToken, db: AsyncSession) -> str:
    if not row.refresh_token:
        raise RuntimeError("No refresh_token stored; user must reconnect Microsoft")

    refresh_plain = decrypt(row.refresh_token)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.ms_client_id,
                "client_secret": settings.ms_client_secret,
                "refresh_token": refresh_plain,
                "grant_type": "refresh_token",
                "scope": " ".join(_SCOPES),
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Microsoft refresh failed ({resp.status_code}): {resp.text[:300]}"
            )
        payload = resp.json()

    new_access = payload.get("access_token")
    if not new_access:
        raise RuntimeError("Microsoft refresh response missing access_token")
    expires_in = payload.get("expires_in")
    new_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if expires_in else None
    )

    row.access_token = encrypt(new_access)
    row.expires_at = new_expires_at
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
            logger.warning("microsoft oauth: refresh failed for %s: %s", user_id, exc)
            return None
    try:
        return decrypt(row.access_token)
    except Exception as exc:
        logger.warning("microsoft oauth: decrypt failed for %s: %s", user_id, exc)
        return None


async def disconnect(user_id: uuid.UUID, db: AsyncSession) -> bool:
    row = await _load_row(user_id, db)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    logger.info("microsoft oauth: disconnected user %s", user_id)
    return True


async def is_connected(user_id: uuid.UUID, db: AsyncSession) -> bool:
    return (await _load_row(user_id, db)) is not None
