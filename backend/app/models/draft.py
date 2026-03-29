import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Draft(Base):
    __tablename__ = "drafts"

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
    # Platform values: linkedin, twitter, xiaohongshu, medium_outline, github_release
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Status values: draft, approved, published, archived
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    # The rendered prompt that produced this draft — useful for debugging regressions
    generation_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sync_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Self-referential FK for version chains: all revisions point to the first draft
    parent_draft_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("drafts.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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
    project: Mapped["Project"] = relationship("Project", back_populates="drafts")  # noqa: F821
    post_schedules: Mapped[list["PostSchedule"]] = relationship(  # noqa: F821
        "PostSchedule", back_populates="draft", cascade="all, delete-orphan"
    )
    post_records: Mapped[list["PostRecord"]] = relationship(  # noqa: F821
        "PostRecord", back_populates="draft", cascade="all, delete-orphan"
    )
    ai_feedbacks: Mapped[list["AIFeedback"]] = relationship(  # noqa: F821
        "AIFeedback", back_populates="draft", cascade="all, delete-orphan"
    )
    parent_draft: Mapped[Optional["Draft"]] = relationship(
        "Draft", remote_side="Draft.id", foreign_keys=[parent_draft_id]
    )
    child_drafts: Mapped[list["Draft"]] = relationship(
        "Draft", foreign_keys=[parent_draft_id], back_populates="parent_draft"
    )
