"""Create work_logs table for progress reports

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS work_logs (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            title VARCHAR(500) NOT NULL,
            period_type VARCHAR(20) NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            project_ids UUID[] NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            goals JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_logs_period_start "
        "ON work_logs (period_start)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_work_logs_period_start")
    op.execute("DROP TABLE IF EXISTS work_logs")
