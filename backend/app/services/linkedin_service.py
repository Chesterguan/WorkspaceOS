"""
LinkedIn OAuth 2.0 + posting service.

OAuth flow:
  1. Frontend calls GET /linkedin/auth while authenticated; the router signs a
     short-lived state token embedding the user's UUID and returns the auth URL.
  2. LinkedIn redirects back to /linkedin/callback with ?code=...&state=...
  3. exchange_code() swaps the code for an access token and persists it on the
     ``users.linkedin_access_token`` column of the user identified by the state.
  4. publish_post() uses that user's token to create a post via the REST Posts API.

Tokens are per-user (no module-level cache). Multi-tenant safe.

Scope note:
  ``w_member_social`` lets us post on behalf of the member.
  ``openid profile`` gives us a member ID without LinkedIn app review.
"""
import logging
import urllib.parse
import uuid
from typing import Optional

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LinkedIn API constants
# ---------------------------------------------------------------------------

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_ME_URL = "https://api.linkedin.com/v2/me"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"

LINKEDIN_SCOPES = "openid profile w_member_social"


# ---------------------------------------------------------------------------
# Per-user token helpers
# ---------------------------------------------------------------------------

async def load_token_for_user(user_id: uuid.UUID, db) -> Optional[str]:
    """Return the stored LinkedIn access token for ``user_id``, or None."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    return user.linkedin_access_token if user else None


async def persist_token_for_user(
    user_id: uuid.UUID, token: Optional[str], db
) -> None:
    """Persist (or clear) the LinkedIn access token for a specific user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"User {user_id} not found")
    user.linkedin_access_token = token
    await db.flush()
    logger.info(
        "LinkedIn token %s for user %s",
        "cleared" if token is None else "persisted",
        user_id,
    )


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_auth_url(state: Optional[str] = None) -> str:
    """
    Build the LinkedIn OAuth 2.0 authorization URL.

    ``state`` is a signed token containing the initiating user's ID; it is
    echoed back in the callback so we know which user to attach the token to.
    """
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": LINKEDIN_SCOPES,
    }
    if state:
        params["state"] = state
    return f"{LINKEDIN_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(
    code: str, user_id: uuid.UUID, db
) -> dict:
    """
    Exchange an authorization code for an access token and persist it on the
    user row identified by ``user_id``.

    Raises httpx.HTTPStatusError on non-2xx token responses.
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
        await persist_token_for_user(user_id, access_token, db)

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
                if data.get("sub"):
                    data["id"] = data["sub"]
                return data
        except Exception:
            pass

        # Try 2: /v2/me with version header
        try:
            resp = await client.get(
                LINKEDIN_ME_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "LinkedIn-Version": "202603",
                },
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        # Try 3: /v2/me without version header (legacy)
        resp = await client.get(
            LINKEDIN_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


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
        "LinkedIn-Version": "202603",
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
