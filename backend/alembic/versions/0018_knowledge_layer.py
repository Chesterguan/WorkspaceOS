"""Add knowledge_nodes + knowledge_edges — user-scoped cross-project graph.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-04

Rationale:
  Roundtable conversations produce decisions, claims, hypotheses, etc.
  Today they die in chat_messages. This adds a user-scoped graph layer
  populated by per-turn extraction. Memory tables stay untouched.

  See docs/superpowers/specs/2026-05-04-knowledge-layer-design.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector exists (safe no-op if already created)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_refs", JSONB, server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("search_vector", sa.Text, nullable=True),  # placeholder; rewritten below
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.Column("archived", sa.Boolean, server_default=sa.text("false"),
                  nullable=False),
        sa.Column("created_by", sa.String(40), nullable=False,
                  server_default="auto_extractor"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )

    # Replace the placeholder embedding/search_vector columns with proper types.
    op.execute("ALTER TABLE knowledge_nodes DROP COLUMN embedding")
    op.execute("ALTER TABLE knowledge_nodes ADD COLUMN embedding vector(768)")
    op.execute("ALTER TABLE knowledge_nodes DROP COLUMN search_vector")
    op.execute("ALTER TABLE knowledge_nodes ADD COLUMN search_vector tsvector")

    # tsvector trigger (mirrors memory_entries pattern)
    op.execute("""
        CREATE FUNCTION knowledge_nodes_tsv_trigger() RETURNS trigger AS $$
        BEGIN
          NEW.search_vector :=
            setweight(to_tsvector('english', coalesce(NEW.title,'')), 'A') ||
            setweight(to_tsvector('english', coalesce(NEW.content,'')), 'B');
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER knowledge_nodes_tsv_update
        BEFORE INSERT OR UPDATE OF title, content
        ON knowledge_nodes
        FOR EACH ROW EXECUTE FUNCTION knowledge_nodes_tsv_trigger();
    """)

    op.create_index("ix_knowledge_nodes_user_id", "knowledge_nodes", ["user_id"])
    op.create_index("ix_knowledge_nodes_project_id", "knowledge_nodes", ["project_id"])
    op.create_index("ix_knowledge_nodes_node_type", "knowledge_nodes", ["node_type"])
    op.create_index(
        "ix_knowledge_nodes_user_archived_created",
        "knowledge_nodes",
        ["user_id", "archived", sa.text("created_at DESC")],
    )
    op.execute(
        "CREATE INDEX ix_knowledge_nodes_search_vector "
        "ON knowledge_nodes USING gin (search_vector)"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_nodes_embedding "
        "ON knowledge_nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "knowledge_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("target_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("edge_type", sa.String(40), nullable=False),
        sa.Column("weight", sa.Float, server_default=sa.text("1.0"), nullable=False),
        sa.Column("source_refs", JSONB, server_default=sa.text("'[]'::jsonb"),
                  nullable=False),
        sa.Column("created_by", sa.String(40), nullable=False,
                  server_default="auto_extractor"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_node_id", "target_node_id", "edge_type",
                            name="uq_knowledge_edges_triple"),
    )
    op.create_index("ix_knowledge_edges_user_id", "knowledge_edges", ["user_id"])


def downgrade() -> None:
    op.drop_table("knowledge_edges")
    op.execute("DROP TRIGGER IF EXISTS knowledge_nodes_tsv_update ON knowledge_nodes")
    op.execute("DROP FUNCTION IF EXISTS knowledge_nodes_tsv_trigger()")
    op.drop_table("knowledge_nodes")
