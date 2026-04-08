"""Add app_settings table for UI-editable API keys

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            id          UUID         NOT NULL DEFAULT gen_random_uuid(),
            key         VARCHAR(100) NOT NULL,
            value       TEXT         NOT NULL,
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_app_settings_key UNIQUE (key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_settings_key ON app_settings (key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_app_settings_key")
    op.execute("DROP TABLE IF EXISTS app_settings")
