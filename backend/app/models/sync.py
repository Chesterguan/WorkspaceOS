import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SyncRun(Base):
    __tablename__ = "sync_runs"

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
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Status values: pending, running, completed, failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    commits_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    releases_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    readme_changed: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Full raw API payload stored for debugging and re-processing
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    evolution_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Structured themes extracted from commits/releases by the extraction service
    themes_extracted: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    extraction_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="sync_runs")  # noqa: F821
    commits: Mapped[list["GitHubCommit"]] = relationship(
        "GitHubCommit", back_populates="sync_run", cascade="all, delete-orphan"
    )
    releases: Mapped[list["GitHubRelease"]] = relationship(
        "GitHubRelease", back_populates="sync_run", cascade="all, delete-orphan"
    )


class GitHubCommit(Base):
    __tablename__ = "github_commits"
    __table_args__ = (
        UniqueConstraint("project_id", "sha", name="uq_github_commits_project_sha"),
    )

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
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="commits")  # noqa: F821
    sync_run: Mapped["SyncRun"] = relationship("SyncRun", back_populates="commits")


class GitHubRelease(Base):
    __tablename__ = "github_releases"
    __table_args__ = (
        UniqueConstraint("project_id", "tag_name", name="uq_github_releases_project_tag"),
    )

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
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag_name: Mapped[str] = mapped_column(String(255), nullable=False)
    release_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="releases")  # noqa: F821
    sync_run: Mapped["SyncRun"] = relationship("SyncRun", back_populates="releases")
