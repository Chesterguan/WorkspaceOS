import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_projects_user_slug"),)

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    github_repo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    github_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="main")
    # Local filesystem path for workspace scanning (mounted via Docker volume)
    local_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
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
    user: Mapped["User"] = relationship("User", back_populates="projects")  # noqa: F821
    narrative: Mapped[Optional["Narrative"]] = relationship(  # noqa: F821
        "Narrative", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    sync_runs: Mapped[list["SyncRun"]] = relationship(  # noqa: F821
        "SyncRun", back_populates="project", cascade="all, delete-orphan"
    )
    commits: Mapped[list["GitHubCommit"]] = relationship(  # noqa: F821
        "GitHubCommit", back_populates="project", cascade="all, delete-orphan"
    )
    releases: Mapped[list["GitHubRelease"]] = relationship(  # noqa: F821
        "GitHubRelease", back_populates="project", cascade="all, delete-orphan"
    )
    drafts: Mapped[list["Draft"]] = relationship(  # noqa: F821
        "Draft", back_populates="project", cascade="all, delete-orphan"
    )
    memory_entries: Mapped[list["MemoryEntry"]] = relationship(  # noqa: F821
        "MemoryEntry", back_populates="project", cascade="all, delete-orphan"
    )
    post_schedules: Mapped[list["PostSchedule"]] = relationship(  # noqa: F821
        "PostSchedule", back_populates="project", cascade="all, delete-orphan"
    )
    post_records: Mapped[list["PostRecord"]] = relationship(  # noqa: F821
        "PostRecord", back_populates="project", cascade="all, delete-orphan"
    )
    blog_posts: Mapped[list["BlogPost"]] = relationship(  # noqa: F821
        "BlogPost", back_populates="project", cascade="all, delete-orphan"
    )
    ai_feedbacks: Mapped[list["AIFeedback"]] = relationship(  # noqa: F821
        "AIFeedback", back_populates="project", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list["ChatMessage"]] = relationship(  # noqa: F821
        "ChatMessage", back_populates="project", cascade="all, delete-orphan"
    )
    workspace_snapshots: Mapped[list["WorkspaceSnapshot"]] = relationship(  # noqa: F821
        "WorkspaceSnapshot", back_populates="project", cascade="all, delete-orphan"
    )
