"""Add metadata JSONB column to memory_entries

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE memory_entries ADD COLUMN IF NOT EXISTS metadata JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE memory_entries DROP COLUMN IF EXISTS metadata")
