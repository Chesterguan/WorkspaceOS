"""
JWT authentication service.

Handles password hashing (bcrypt) and JWT token creation/verification.
Tokens are signed with the api_secret_key from settings.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72  # 3 days
REFRESH_TOKEN_EXPIRE_DAYS = 7  # Reduced from 30 for security


def _get_jwt_secret() -> str:
    """Get the JWT signing secret. Falls back to api_secret_key if jwt_secret_key is not set."""
    if settings.jwt_secret_key:
        return settings.jwt_secret_key
    return settings.api_secret_key


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a refresh token (7 days) with jti for future revocation support."""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate an access JWT. Returns the payload or None.

    Rejects any token whose ``type`` claim is not ``"access"`` so that refresh
    tokens and OAuth state tokens (which are signed with the same secret)
    cannot be replayed as access tokens. Pre-existing tokens without a ``type``
    claim are accepted for a single rotation window so in-flight logins don't
    break — remove that branch after all tokens have been reissued.
    """
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
    except JWTError:
        return None
    token_type = payload.get("type")
    if token_type is not None and token_type != "access":
        return None
    return payload


def decode_refresh_token(token: str) -> Optional[str]:
    """Decode a refresh token. Returns user_id or None."""
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def create_oauth_state_token(user_id: str, purpose: str) -> str:
    """Create a short-lived signed state token for OAuth flows.

    Used as the ``state`` parameter sent to the OAuth provider and echoed back
    in the callback — lets us know which user initiated the flow and prevents
    CSRF/linking attacks. Expires in 15 minutes.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {
        "sub": user_id,
        "type": "oauth_state",
        "purpose": purpose,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=ALGORITHM)


def decode_oauth_state_token(token: str, expected_purpose: str) -> Optional[str]:
    """Verify and decode an OAuth state token. Returns user_id or None."""
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        if payload.get("type") != "oauth_state":
            return None
        if payload.get("purpose") != expected_purpose:
            return None
        return payload.get("sub")
    except JWTError:
        return None


async def authenticate_user(
    email: str, password: str, db: AsyncSession
) -> Optional[User]:
    """Verify email + password. Returns the User or None."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
