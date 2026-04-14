"""Add user_oauth_tokens — per-user, multi-provider OAuth token storage

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-14

Rationale:
  LinkedIn's token currently lives on users.linkedin_access_token. That
  pattern doesn't scale to Google (needs refresh_token + expires_at) or
  beyond (Slack, Notion, …). Instead of piling columns onto users, give
  each provider its own row.

  Tokens are Fernet-encrypted at rest using the app's existing key
  (backend/app/services/encryption.py) — same discipline as app_settings.

  UNIQUE(user_id, provider) so each user has at most one token per
  provider; re-connecting overwrites in place. ON DELETE CASCADE so
  deleting a user cleans up their creds.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_oauth_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=30), nullable=False),
        # Fernet ciphertext is base64 (~120 chars for a Google access token);
        # TEXT is safest for any provider.
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=True),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("scopes", sa.Text, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_oauth_user_provider"),
    )


def downgrade() -> None:
    op.drop_table("user_oauth_tokens")
