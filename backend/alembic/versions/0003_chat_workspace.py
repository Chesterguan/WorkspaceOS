"""Chat messages, workspace snapshots, and project local_path

Adds:
- chat_messages table
- workspace_snapshots table
- projects.local_path column

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # chat_messages
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_chat_messages_project
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_project_id ON chat_messages (project_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_created_at ON chat_messages (project_id, created_at DESC)"
    )

    # ------------------------------------------------------------------
    # workspace_snapshots
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_snapshots (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            local_path VARCHAR(500) NOT NULL,
            summary TEXT NOT NULL,
            raw_data JSONB NULL,
            git_branch VARCHAR(255) NULL,
            git_status TEXT NULL,
            git_recent_log TEXT NULL,
            scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_workspace_snapshots_project
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workspace_snapshots_project_id ON workspace_snapshots (project_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workspace_snapshots_scanned_at ON workspace_snapshots (project_id, scanned_at DESC)"
    )

    # ------------------------------------------------------------------
    # projects: add local_path column
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS local_path VARCHAR(500) NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_messages")
    op.execute("DROP TABLE IF EXISTS workspace_snapshots")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS local_path")
