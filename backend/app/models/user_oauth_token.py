"""
Per-user, per-provider OAuth token record.

Access + refresh tokens are Fernet-encrypted at rest (see migration 0017
for rationale). Encryption/decryption is NOT handled inside the model —
callers use `app.services.encryption.encrypt` / `decrypt` explicitly so
the storage boundary is visible in diff reviews.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserOAuthToken(Base):
    __tablename__ = "user_oauth_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_oauth_user_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "google" | "slack" | "notion" | … — free-form VARCHAR so new providers
    # don't need a migration; validated at the service boundary.
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    # Fernet ciphertext (base64 text). Never store plaintext here.
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Null for providers whose tokens don't expire (rare).
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
