from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session and ensure it is closed when the request ends."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Validate authentication via API key OR JWT Bearer token.

    Accepts either:
    - X-API-Key header matching settings.api_secret_key (backward compat)
    - Authorization: Bearer <jwt> header with valid JWT token

    Returns the user identifier (API key string or JWT subject).
    """
    # Try API key first (backward compat for scripts, tests, cURL)
    if x_api_key and x_api_key == settings.api_secret_key:
        return x_api_key

    # Try JWT Bearer token
    if authorization and authorization.startswith("Bearer "):
        from app.services.auth_service import decode_access_token

        token = authorization[7:]  # strip "Bearer "
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            return payload["sub"]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key / token",
    )


async def get_optional_user_id(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> Optional[str]:
    """Extract user ID from JWT if present. Returns None for API key auth.

    This allows endpoints to scope queries by user when JWT auth is used,
    while preserving backward compat for API key auth (admin/scripts see all).
    """
    if authorization and authorization.startswith("Bearer "):
        from app.services.auth_service import decode_access_token

        token = authorization[7:]
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            return payload["sub"]
    return None
