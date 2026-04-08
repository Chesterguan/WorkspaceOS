"""Create ai_usage_log table for tracking AI API costs

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage_log (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            provider VARCHAR(50) NOT NULL,
            model VARCHAR(100) NOT NULL,
            operation VARCHAR(100) NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_usage_log_created_at "
        "ON ai_usage_log (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ai_usage_log_created_at")
    op.execute("DROP TABLE IF EXISTS ai_usage_log")
