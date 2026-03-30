"""
LinkedIn OAuth 2.0 + posting service.

OAuth flow:
  1. Frontend redirects user to get_auth_url().
  2. LinkedIn redirects back to /linkedin/callback with ?code=...
  3. exchange_code() swaps the code for an access token and stores it
     in the module-level _access_token variable (in-memory, single-user MVP).
  4. publish_post() uses that token to create a post via the REST Posts API.
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
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"

# Required scopes:
#   openid profile — for userinfo (person URN via `sub`)
#   w_member_social — for creating posts
LINKEDIN_SCOPES = "openid profile w_member_social"

# ---------------------------------------------------------------------------
# In-memory token store (MVP: single user, not persisted across restarts)
# ---------------------------------------------------------------------------

_access_token: Optional[str] = None


def get_stored_token() -> Optional[str]:
    """Return the currently stored access token, if any."""
    return _access_token


def store_token(token: str) -> None:
    """Persist a fresh access token in memory."""
    global _access_token
    _access_token = token
    logger.info("LinkedIn access token stored in memory.")


def clear_token() -> None:
    """Remove the stored token (disconnect)."""
    global _access_token
    _access_token = None


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_auth_url() -> str:
    """
    Build the LinkedIn OAuth 2.0 authorization URL.

    The user should be redirected to this URL to begin the OAuth flow.
    """
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": LINKEDIN_SCOPES,
        # state param omitted for MVP; add CSRF token here in production
    }
    return f"{LINKEDIN_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """
    Exchange an authorization code for an access token.

    Stores the token in memory and returns the raw token response dict.
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

    return token_data


# ---------------------------------------------------------------------------
# Profile (author URN)
# ---------------------------------------------------------------------------

async def get_profile(access_token: str) -> dict:
    """
    Fetch the authenticated user's LinkedIn profile.

    Returns the userinfo dict. The `sub` field is the person ID used
    to construct the author URN: urn:li:person:{sub}.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


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
        "LinkedIn-Version": "202401",
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
