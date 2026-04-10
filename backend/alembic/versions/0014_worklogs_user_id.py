"""Add user_id column to work_logs (backfill for earlier CREATE TABLE IF NOT EXISTS gap)

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-10

The original migration 0013_work_logs.py wraps its CREATE TABLE in
``IF NOT EXISTS``. When the table was first created by SQLAlchemy auto-create
(or an earlier form of the migration) without the ``user_id`` column, the
subsequent migration run was a silent no-op — the column declared by the
``WorkLog`` model never made it into the physical schema. Any actual worklog
creation via ``POST /worklog/generate`` would 500 with
``column "user_id" does not exist``.

This migration patches the gap idempotently.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the column if the earlier migration skipped it. Nullable FK with
    # ON DELETE SET NULL matches the model in backend/app/models/worklog.py.
    op.execute("""
        ALTER TABLE work_logs
        ADD COLUMN IF NOT EXISTS user_id UUID
        REFERENCES users(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE work_logs DROP COLUMN IF EXISTS user_id")
