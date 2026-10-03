"""Enable pgvector; domain tables and checkpoint setup belong to later tasks."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # An extension may predate this migration or be shared by other consumers.
    # Preserve it; B00 owns only the Alembic revision marker.
    pass
