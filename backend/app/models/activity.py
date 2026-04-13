"""ORM model for the per-project activity feed. See migration 0016 for rationale."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ActivityEvent(Base):
    __tablename__ = "project_activity_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: system-triggered events (auto-sync, background jobs) have
    # no user; SET NULL on user delete so history survives account removal.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Dotted path, e.g. "sync.completed" / "worklog.generated". Free-form
    # VARCHAR rather than an enum so new event kinds don't need migrations.
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Short human-readable line the UI renders directly.
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    # Structured payload: entity ids for click-through, counts, durations.
    # Shape is per-event and intentionally not enforced.
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Coarse category for filtering the feed by who/what triggered it.
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # No back-populates from Project — queries always go through the
    # indexed (project_id, created_at DESC) path, never by walking the
    # relationship, so the eager/lazy load semantics aren't worth the
    # cross-module import churn.
    project = relationship("Project", foreign_keys=[project_id])
    user = relationship("User", foreign_keys=[user_id])
