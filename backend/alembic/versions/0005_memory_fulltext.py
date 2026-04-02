"""Add tsvector full-text search column to memory_entries

Changes:
- Add search_vector tsvector column to memory_entries
- Populate from existing content
- Create GIN index for fast full-text search
- Add trigger to auto-update tsvector on insert/update
- Add context_description column for contextual retrieval

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Add tsvector column for BM25-style full-text search
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE memory_entries "
        "ADD COLUMN IF NOT EXISTS search_vector tsvector"
    )

    # Populate tsvector from existing content
    op.execute(
        "UPDATE memory_entries "
        "SET search_vector = to_tsvector('english', coalesce(content, ''))"
    )

    # GIN index for fast full-text search
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_entries_search_vector "
        "ON memory_entries USING gin(search_vector)"
    )

    # Trigger to auto-update tsvector on insert/update of content
    op.execute("""
        CREATE OR REPLACE FUNCTION memory_search_vector_update() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := to_tsvector('english', coalesce(NEW.content, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute(
        "DROP TRIGGER IF EXISTS trg_memory_search_vector ON memory_entries"
    )

    op.execute(
        "CREATE TRIGGER trg_memory_search_vector "
        "BEFORE INSERT OR UPDATE OF content ON memory_entries "
        "FOR EACH ROW EXECUTE FUNCTION memory_search_vector_update()"
    )

    # ------------------------------------------------------------------
    # Add context_description column for contextual retrieval
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE memory_entries "
        "ADD COLUMN IF NOT EXISTS context_description TEXT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_memory_search_vector ON memory_entries")
    op.execute("DROP FUNCTION IF EXISTS memory_search_vector_update()")
    op.execute("DROP INDEX IF EXISTS idx_memory_entries_search_vector")
    op.execute("ALTER TABLE memory_entries DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE memory_entries DROP COLUMN IF EXISTS context_description")
