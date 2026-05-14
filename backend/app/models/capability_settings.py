"""ORM for capability_settings — encrypted per-capability config overlay."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CapabilitySetting(Base):
    __tablename__ = "capability_settings"
    __table_args__ = (
        UniqueConstraint("extension_id", "capability_name",
                         name="uq_capability_settings_ext_cap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    extension_id: Mapped[str] = mapped_column(String(80), nullable=False)
    capability_name: Mapped[str] = mapped_column(String(80), nullable=False)
    encrypted_config: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
