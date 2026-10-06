"""Frozen B30 retrieval columns; upgrading existing rows never invokes a model."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects.postgresql import TSVECTOR

revision = "0003_retrieval"
down_revision = "0002_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks", sa.Column("embedding", VECTOR(1024), nullable=True)
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "search_vector",
            TSVECTOR,
            sa.Computed("to_tsvector('english'::regconfig, content)", persisted=True),
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_search_vector",
        "knowledge_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_search_vector", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "search_vector")
    op.drop_column("knowledge_chunks", "embedding")
