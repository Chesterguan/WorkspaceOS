"""SQLAlchemy model for egress_logs. One row per cloud-egress AI call.

See docs/privacy/measurement-and-redaction.md#part-1--measurement for
the shape of the `fields` and `redaction` JSONB columns.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EgressLog(Base):
    __tablename__ = "egress_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    surface: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    redaction: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tokens_estimated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
