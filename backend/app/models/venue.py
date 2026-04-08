import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VenueCache(Base):
    """Cached venue submission guidelines resolved from the web, AI inference, or manual entry."""

    __tablename__ = "venue_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    venue_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    venue_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    page_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    word_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # LaTeX template identifier, e.g. "acmart", "neurips", "ieee"
    template: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    anonymization: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Free-form deadline string, e.g. "2026-05-15" or "May 15, 2026 AoE"
    deadline: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    topics: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    # Source of this cache entry: "web" | "ai_inferred" | "manual" | "cached"
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
