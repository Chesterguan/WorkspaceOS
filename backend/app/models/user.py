import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # LinkedIn OAuth access token — persisted to survive container restarts.
    # Written by linkedin_service after exchange_code(); read by publish_post().
    linkedin_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Onboarding state — wizard runs on first signup, re-runnable from
    # Settings → "Personalize". tutorial_completed gates the wait-state
    # tutorial animation chapters from auto-firing again.
    tutorial_completed: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    onboarding_answers: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        "Project", back_populates="user", cascade="all, delete-orphan"
    )
