import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import ARRAY, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Narrative(Base):
    __tablename__ = "narratives"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    # One narrative per project — enforced by unique FK
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    one_liner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin_story: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ARRAY(Text) stores a list of preferred angle strings
    preferred_angles: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    avoided_angles: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    # FAQ stored as a JSON array of {q, a} objects
    faq: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tone_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="narrative")  # noqa: F821
