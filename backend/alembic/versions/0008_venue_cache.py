"""Add venue_cache table for caching resolved venue submission guidelines

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS venue_cache (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            venue_name  VARCHAR(500) NOT NULL,
            venue_url   VARCHAR(1000) NULL,
            page_limit  INTEGER     NULL,
            word_limit  INTEGER     NULL,
            template    VARCHAR(100) NULL,
            anonymization BOOLEAN   NOT NULL DEFAULT FALSE,
            deadline    VARCHAR(100) NULL,
            topics      TEXT[]      NULL,
            source      VARCHAR(50)  NOT NULL DEFAULT 'manual',
            fetched_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_venue_cache_venue_name ON venue_cache (venue_name)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_venue_cache_venue_name")
    op.execute("DROP TABLE IF EXISTS venue_cache")
