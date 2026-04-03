"""Clean up duplicate readme_content memory entries

Keeps only the most recent readme_content entry per project,
deletes all older duplicates.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete all but the most recent readme_content entry per project
    op.execute("""
        DELETE FROM memory_entries
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY project_id
                           ORDER BY created_at DESC
                       ) AS rn
                FROM memory_entries
                WHERE entry_type = 'readme_content'
            ) sub
            WHERE rn > 1
        )
    """)


def downgrade() -> None:
    # Cannot restore deleted duplicates
    pass
