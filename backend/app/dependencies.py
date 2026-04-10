import hmac
import uuid
from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal


def _is_valid_api_key(candidate: Optional[str]) -> bool:
    """Constant-time compare the candidate against the configured admin key.

    Returns False if either value is empty. Uses ``hmac.compare_digest`` so the
    comparison does not leak information about the secret via timing side
    channels — cheap insurance even though remote timing attacks against a
    string compare are rarely practical.
    """
    if not candidate or not settings.api_secret_key:
        return False
    return hmac.compare_digest(candidate, settings.api_secret_key)


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
    if _is_valid_api_key(x_api_key):
        return x_api_key  # type: ignore[return-value]

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


async def require_admin(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Require admin access (valid X-API-Key header only).

    Use this dependency on endpoints that manage global, app-wide state:
    shared API keys, database backups, backfill jobs, etc. JWT users are
    rejected with 403. This is stricter than ``verify_api_key`` because it
    refuses the JWT path entirely — the X-API-Key secret is the one and only
    credential that grants admin.
    """
    if _is_valid_api_key(x_api_key):
        return x_api_key  # type: ignore[return-value]
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


def parse_jwt_user_uuid(jwt_user_id: str) -> uuid.UUID:
    """Parse a JWT ``sub`` claim into a UUID, 401 on failure.

    Callers that convert ``jwt_user_id`` to UUID and then query on it should
    use this helper so a malformed ``sub`` cleanly 401s instead of 500ing
    from an uncaught ``ValueError``.
    """
    try:
        return uuid.UUID(jwt_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id in token",
        )


async def require_owned_project(
    project_id: uuid.UUID,
    db: AsyncSession,
    jwt_user_id: Optional[str],
):
    """Fetch a project and 404 if it doesn't exist or isn't owned by the JWT user.

    When ``jwt_user_id`` is None (API key / admin mode), ownership is not enforced
    and the project is returned as long as it exists. This is the single
    authoritative helper used by every nested /projects/{project_id}/... route.
    """
    from app.models.project import Project

    query = select(Project).where(Project.id == project_id)
    if jwt_user_id:
        owner_uuid = parse_jwt_user_uuid(jwt_user_id)
        query = query.where(Project.user_id == owner_uuid)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project
