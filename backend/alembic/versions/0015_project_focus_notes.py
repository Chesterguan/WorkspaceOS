"""Add focus_notes column to projects — user-pinned context the AI must respect

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-13

Adds one nullable TEXT column `focus_notes` to the `projects` table. Holds
a short free-form note (commitments, deadlines, "this week's focus") that
the user edits by hand and that every AI prompt reading the project is
expected to treat as authoritative — the opposite of the auto-generated
wiki summary, which is AI-maintained.

No backfill: new projects and existing ones both start with NULL, which
the downstream prompts render as an empty section.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS focus_notes TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS focus_notes")
