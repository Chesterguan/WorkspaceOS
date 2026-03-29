"""Features v2: posting, blog, AI feedback, GitHub full_name, sync themes extraction

Adds:
- projects.github_full_name column
- sync_runs.themes_extracted (JSONB) and extraction_run_at (DateTime) columns
- post_schedules table
- post_records table
- blog_posts table
- blog_post_versions table
- ai_feedback table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # projects: add github_full_name column
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_full_name VARCHAR(255) NULL"
    )

    # ------------------------------------------------------------------
    # sync_runs: add themes_extracted (JSONB) and extraction_run_at (timestamp)
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS themes_extracted JSONB NULL"
    )
    op.execute(
        "ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS extraction_run_at TIMESTAMPTZ NULL"
    )

    # ------------------------------------------------------------------
    # post_schedules
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS post_schedules (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            draft_id UUID NOT NULL,
            project_id UUID NOT NULL,
            platform VARCHAR(100) NOT NULL,
            scheduled_for TIMESTAMPTZ NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'planned',
            notes TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_post_schedules_draft
                FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE,
            CONSTRAINT fk_post_schedules_project
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_post_schedules_draft_id ON post_schedules (draft_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_post_schedules_project_id ON post_schedules (project_id)"
    )

    # ------------------------------------------------------------------
    # post_records
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS post_records (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            draft_id UUID NOT NULL,
            project_id UUID NOT NULL,
            platform VARCHAR(100) NOT NULL,
            posted_at TIMESTAMPTZ NOT NULL,
            post_url TEXT NULL,
            notes TEXT NULL,
            post_type VARCHAR(50) NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_post_records_draft
                FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE,
            CONSTRAINT fk_post_records_project
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_post_records_draft_id ON post_records (draft_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_post_records_project_id ON post_records (project_id)"
    )

    # ------------------------------------------------------------------
    # blog_posts
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_posts (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            title VARCHAR(500) NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            status VARCHAR(50) NOT NULL DEFAULT 'draft',
            tags TEXT[] NULL,
            sync_run_id UUID NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_blog_posts_project
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CONSTRAINT fk_blog_posts_sync_run
                FOREIGN KEY (sync_run_id) REFERENCES sync_runs(id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_blog_posts_project_id ON blog_posts (project_id)"
    )

    # ------------------------------------------------------------------
    # blog_post_versions
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_post_versions (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            blog_post_id UUID NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            title VARCHAR(500) NOT NULL,
            saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            change_note TEXT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_blog_post_versions_post
                FOREIGN KEY (blog_post_id) REFERENCES blog_posts(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_blog_post_versions_post_id ON blog_post_versions (blog_post_id)"
    )

    # ------------------------------------------------------------------
    # ai_feedback
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_feedback (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            draft_id UUID NOT NULL,
            project_id UUID NOT NULL,
            outcome VARCHAR(50) NOT NULL,
            edit_distance INTEGER NULL,
            user_notes TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT fk_ai_feedback_draft
                FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE,
            CONSTRAINT fk_ai_feedback_project
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_feedback_draft_id ON ai_feedback (draft_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_feedback_project_id ON ai_feedback (project_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ai_feedback")
    op.execute("DROP TABLE IF EXISTS blog_post_versions")
    op.execute("DROP TABLE IF EXISTS blog_posts")
    op.execute("DROP TABLE IF EXISTS post_records")
    op.execute("DROP TABLE IF EXISTS post_schedules")
    op.execute("ALTER TABLE sync_runs DROP COLUMN IF EXISTS extraction_run_at")
    op.execute("ALTER TABLE sync_runs DROP COLUMN IF EXISTS themes_extracted")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS github_full_name")
