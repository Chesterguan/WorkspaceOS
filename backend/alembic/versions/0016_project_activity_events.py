"""Add project_activity_events — per-project audit surface

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-13

Captures significant events (sync, worklog generated, file ingested, wiki
refreshed, draft created/published, project edited, workspace scanned) so
the project page can show a "what happened with this project" feed. The
same table is the future landing zone for MCP-driven actions (emails
ingested, calendar events linked, etc.) — the point is that every data
source ends up visible on one timeline per project instead of buried in
service logs.

Table shape:
  - event_type: dotted path like "sync.completed" / "worklog.generated".
    Kept flexible as VARCHAR so we don't need a migration every time a
    new event kind is emitted; frontend mapping is tolerant of unknowns.
  - summary: short human-readable line the UI shows directly.
  - details: JSONB payload for structured data (ids for click-through,
    counts, durations). No schema enforced — the emit site decides.
  - source: coarse category ("sync" | "user" | "ai" | "ingest" |
    "publish" | "system"). Lets the feed filter by who triggered what.
  - user_id SET NULL: auto-sync and system triggers have no user; when
    the user is later deleted we keep the event for the project.

Index on (project_id, created_at DESC) because every feed query is
"latest events for this project" — the table will grow fastest, and
that composite is the only hot path.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_activity_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="system"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_activity_project_created",
        "project_activity_events",
        ["project_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_project_created", table_name="project_activity_events")
    op.drop_table("project_activity_events")
