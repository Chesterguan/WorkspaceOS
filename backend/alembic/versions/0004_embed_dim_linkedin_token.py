"""Resize embedding column to 768 dims and add LinkedIn token storage

Changes:
- Drop HNSW index on memory_entries.embedding
- ALTER memory_entries.embedding to vector(768) (correct native dimension)
- Nullify existing embeddings (they were 1536-dim and are now invalid)
- Recreate HNSW index for cosine similarity
- ALTER users ADD COLUMN linkedin_access_token TEXT (persistent OAuth token)
- Add backend_data volume path /app/data directory hint (handled in compose)

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-27
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Fix embedding dimension: 1536 → 768
    # nomic-embed-text and Gemini text-embedding-004 both emit 768-dim
    # vectors. The old column padded them to 1536 with zeros, which
    # corrupted cosine similarity. Drop, resize, and wipe stale data.
    # ------------------------------------------------------------------
    op.execute(
        "DROP INDEX IF EXISTS ix_memory_entries_embedding_hnsw"
    )

    # pgvector requires casting through text to change vector dimensions
    op.execute(
        "ALTER TABLE memory_entries "
        "ALTER COLUMN embedding TYPE vector(768) "
        "USING NULL"
    )

    # All previously stored embeddings were 1536-dim (half zeros) — invalid.
    # Nullify them so they are regenerated on next search/embed call.
    op.execute("UPDATE memory_entries SET embedding = NULL")

    # Recreate HNSW index for fast approximate nearest-neighbour search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memory_entries_embedding_hnsw "
        "ON memory_entries USING hnsw (embedding vector_cosine_ops)"
    )

    # ------------------------------------------------------------------
    # Add linkedin_access_token to users table
    # Stores the OAuth access token so it survives container restarts.
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS linkedin_access_token TEXT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_entries_embedding_hnsw")
    op.execute(
        "ALTER TABLE memory_entries "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memory_entries_embedding_hnsw "
        "ON memory_entries USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS linkedin_access_token"
    )
