"""Add user onboarding state (tutorial_completed + onboarding_answers).

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-13

Adds two columns on users:
  - tutorial_completed: gates the post-apply tour / wait-state tutorial
  - onboarding_answers: stores wizard answers so "Personalize" in settings
    can prefill the form on re-run

Both are nullable / defaulted — existing users (the demo seed account)
stay valid without backfill.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "tutorial_completed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "onboarding_answers",
            JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_answers")
    op.drop_column("users", "tutorial_completed")
