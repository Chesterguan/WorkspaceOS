import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AIFeedback(Base):
    """Stores human feedback on AI-generated drafts to improve future generation."""

    __tablename__ = "ai_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Outcome values: approved, rejected, heavily_edited
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    # Levenshtein-style edit distance between generated and final content; None if outcome is approved/rejected
    edit_distance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    draft: Mapped["Draft"] = relationship("Draft", back_populates="ai_feedbacks")  # noqa: F821
    project: Mapped["Project"] = relationship("Project", back_populates="ai_feedbacks")  # noqa: F821
