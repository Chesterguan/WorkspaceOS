"""
LinkedIn OAuth 2.0 + posting service.

OAuth flow:
  1. Frontend redirects user to get_auth_url().
  2. LinkedIn redirects back to /linkedin/callback with ?code=...
  3. exchange_code() swaps the code for an access token and persists it
     in the users table (linkedin_access_token column) so it survives
     container restarts. Falls back to module-level cache when no DB
     session is available (e.g. during the callback before we know the user).
  4. publish_post() uses that token to create a post via the REST Posts API.

Scope note:
  Only w_member_social is requested. The openid/profile scopes require
  LinkedIn app review approval. /v2/me is used instead of /v2/userinfo
  to obtain the member ID without openid scope.
"""
import logging
import urllib.parse
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LinkedIn API constants
# ---------------------------------------------------------------------------

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
# /v2/me works with w_member_social scope (no openid required)
LINKEDIN_ME_URL = "https://api.linkedin.com/v2/me"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"

# openid + profile: get member ID (via "Sign In with LinkedIn using OpenID Connect" product)
# w_member_social: create posts on behalf of the user
LINKEDIN_SCOPES = "openid profile w_member_social"

# ---------------------------------------------------------------------------
# In-memory token cache (fallback when no DB session is provided)
# ---------------------------------------------------------------------------

_access_token: Optional[str] = None
_member_id: Optional[str] = None


def get_stored_token() -> Optional[str]:
    """Return the in-memory access token, if any."""
    return _access_token


def store_token(token: str) -> None:
    """Cache a fresh access token in memory (no DB persistence here)."""
    global _access_token
    _access_token = token
    logger.info("LinkedIn access token stored in memory.")


def get_stored_member_id() -> Optional[str]:
    """Return the cached LinkedIn member ID, if any."""
    return _member_id


def store_member_id(member_id: str) -> None:
    """Cache the LinkedIn member ID."""
    global _member_id
    _member_id = member_id


def clear_token() -> None:
    """Clear the in-memory token and member ID (disconnect)."""
    global _access_token, _member_id
    _access_token = None
    _member_id = None


# ---------------------------------------------------------------------------
# DB-backed token helpers (call these when a session is available)
# ---------------------------------------------------------------------------

async def load_token_from_db(db) -> Optional[str]:
    """
    Read the LinkedIn token for the first user in the DB.

    This is an MVP single-user design. Returns None if no token is stored.
    Also populates the in-memory cache so get_stored_token() stays in sync.
    """
    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user and user.linkedin_access_token:
        global _access_token
        _access_token = user.linkedin_access_token
        return user.linkedin_access_token
    return None


async def persist_token_to_db(token: str, db) -> None:
    """
    Persist the LinkedIn token to the first user row.

    Creates a placeholder user row if none exists (shouldn't happen in normal
    use, but guards against an empty users table during initial setup).
    Also updates the in-memory cache.
    """
    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if user:
        user.linkedin_access_token = token
        await db.flush()
    store_token(token)
    logger.info("LinkedIn access token persisted to database.")


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_auth_url() -> str:
    """
    Build the LinkedIn OAuth 2.0 authorization URL.

    The user should be redirected to this URL to begin the OAuth flow.
    Only w_member_social scope is requested — this is the minimum needed
    to post on behalf of the member and does not require LinkedIn app review.
    """
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": LINKEDIN_SCOPES,
        # state param omitted for MVP; add CSRF token here in production
    }
    return f"{LINKEDIN_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str, db=None) -> dict:
    """
    Exchange an authorization code for an access token.

    Stores the token in memory (always) and in the DB (when db is provided).
    Returns the raw token response dict.
    Raises httpx.HTTPStatusError on non-2xx responses.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.linkedin_redirect_uri,
        "client_id": settings.linkedin_client_id,
        "client_secret": settings.linkedin_client_secret,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            LINKEDIN_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token_data = response.json()

    access_token = token_data.get("access_token")
    if access_token:
        store_token(access_token)
        if db is not None:
            await persist_token_to_db(access_token, db)

    return token_data


# ---------------------------------------------------------------------------
# Profile (author URN)
# ---------------------------------------------------------------------------

async def get_profile(access_token: str) -> dict:
    """
    Fetch the authenticated member's LinkedIn profile.

    Tries multiple endpoints since scope availability varies:
    1. /v2/userinfo (works with openid)
    2. /v2/me (works with profile or r_liteprofile)
    3. /v2/me without version header (legacy, sometimes works with w_member_social)

    Returns a dict with 'id' or 'sub' field for building the author URN.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try 1: /v2/userinfo
        try:
            resp = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                # userinfo returns 'sub' as the member ID
                if data.get("sub"):
                    data["id"] = data["sub"]
                    store_member_id(data["sub"])
                return data
        except Exception:
            pass

        # Try 2: /v2/me with version header
        try:
            resp = await client.get(
                LINKEDIN_ME_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "LinkedIn-Version": "202501",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("id"):
                    store_member_id(data["id"])
                return data
        except Exception:
            pass

        # Try 3: /v2/me without version header (legacy)
        resp = await client.get(
            LINKEDIN_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("id"):
            store_member_id(data["id"])
        return data


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------

async def publish_post(access_token: str, author_urn: str, text: str) -> dict:
    """
    Publish a text post to LinkedIn via the REST Posts API.

    Returns the raw response body on success.
    Raises httpx.HTTPStatusError on non-2xx responses.
    """
    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        # LinkedIn REST API requires this version header
        "LinkedIn-Version": "202501",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            LINKEDIN_POSTS_URL,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        # LinkedIn REST Posts API returns 201 with the post URN in the
        # X-RestLi-Id header and an empty body on success.
        post_urn = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")
        return {"post_urn": post_urn}
