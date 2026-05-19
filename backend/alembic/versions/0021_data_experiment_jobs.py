"""data_experiment_jobs

Revision ID: 0021
Revises: 0020
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_experiment_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sidecar_job_id", sa.String(length=80), nullable=True),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("dataset_ref", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="queued"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("result_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_data_experiment_jobs_user_id",
                    "data_experiment_jobs", ["user_id"])
    op.create_index("ix_data_experiment_jobs_project_id",
                    "data_experiment_jobs", ["project_id"])
    op.create_index("ix_data_experiment_jobs_status",
                    "data_experiment_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_data_experiment_jobs_status",
                  table_name="data_experiment_jobs")
    op.drop_index("ix_data_experiment_jobs_project_id",
                  table_name="data_experiment_jobs")
    op.drop_index("ix_data_experiment_jobs_user_id",
                  table_name="data_experiment_jobs")
    op.drop_table("data_experiment_jobs")
