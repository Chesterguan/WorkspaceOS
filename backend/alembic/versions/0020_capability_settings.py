"""Add capability_settings — runtime overlay for capability config.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-14

Manifest YAML files have the structural config (which capabilities
exist, default values, schema). This table holds per-deployment
overrides: API keys, library IDs, etc., that the user fills in via
the Settings UI rather than editing YAML.

Values are Fernet-encrypted (same key as app_settings.encrypted_value)
so secrets aren't readable from a raw DB dump.

Single-tenant for now — no user_id column. v0.3+ may add it for
multi-tenant deployments; the schema is additive.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capability_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("extension_id", sa.String(80), nullable=False),
        sa.Column("capability_name", sa.String(80), nullable=False),
        # Fernet-encrypted JSON blob. Stored as text so we can use the
        # same encryption pattern as app_settings without a binary column.
        sa.Column("encrypted_config", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(),
                  nullable=False),
        sa.UniqueConstraint("extension_id", "capability_name",
                            name="uq_capability_settings_ext_cap"),
    )
    op.create_index(
        "ix_capability_settings_ext_cap",
        "capability_settings",
        ["extension_id", "capability_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_capability_settings_ext_cap", "capability_settings")
    op.drop_table("capability_settings")
