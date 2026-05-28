"""privacy foundation: egress_logs + projects.privacy_default

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. egress_logs — one row per cloud egress call
    op.create_table(
        "egress_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("surface", sa.String(64), nullable=False, index=True),
        sa.Column("service", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("fields", JSONB, nullable=False),
        sa.Column("redaction", JSONB, nullable=True),
        sa.Column("tokens_estimated", sa.Integer, nullable=True),
        sa.Column("total_bytes", sa.Integer, nullable=False),
    )
    op.create_index("ix_egress_logs_user_ts", "egress_logs", ["user_id", "ts"])

    # 2. projects.privacy_default — 'open' | 'strict'
    op.add_column(
        "projects",
        sa.Column("privacy_default", sa.String(16), nullable=False, server_default="open"),
    )


def downgrade() -> None:
    op.drop_column("projects", "privacy_default")
    op.drop_index("ix_egress_logs_user_ts", table_name="egress_logs")
    op.drop_table("egress_logs")
