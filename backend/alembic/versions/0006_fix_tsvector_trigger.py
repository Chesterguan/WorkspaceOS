"""Fix tsvector trigger to include context_description

The 0005 trigger only indexed content. This update includes
context_description in the tsvector so BM25 search can match
on AI-generated context keywords too.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update trigger function to include context_description
    op.execute("""
        CREATE OR REPLACE FUNCTION memory_search_vector_update() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := to_tsvector('english',
              coalesce(NEW.content, '') || ' ' || coalesce(NEW.context_description, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Recreate trigger to also fire on context_description updates
    op.execute(
        "DROP TRIGGER IF EXISTS trg_memory_search_vector ON memory_entries"
    )
    op.execute(
        "CREATE TRIGGER trg_memory_search_vector "
        "BEFORE INSERT OR UPDATE OF content, context_description ON memory_entries "
        "FOR EACH ROW EXECUTE FUNCTION memory_search_vector_update()"
    )

    # Backfill existing rows
    op.execute(
        "UPDATE memory_entries SET search_vector = to_tsvector('english', "
        "coalesce(content, '') || ' ' || coalesce(context_description, ''))"
    )


def downgrade() -> None:
    # Revert to content-only trigger
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
    op.execute(
        "UPDATE memory_entries SET search_vector = to_tsvector('english', "
        "coalesce(content, ''))"
    )
