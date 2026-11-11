"""Add incident resolution fields and vector embedding column with HNSW index

Revision ID: 0007_similarity_embeddings
Revises: 0006_incident_reports
Create Date: 2026-11-11 21:35:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_similarity_embeddings"
down_revision: str | None = "0006_incident_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Resolution fields on incidents
    op.add_column("incidents", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))

    # 2. Vector embedding column on incident_reports
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column("incident_reports", sa.Column("embedding", Vector(768), nullable=True))
        op.execute(
            "CREATE INDEX ix_incident_reports_embedding "
            "ON incident_reports USING hnsw (embedding vector_cosine_ops)"
        )
    else:
        op.add_column("incident_reports", sa.Column("embedding", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_incident_reports_embedding")

    op.drop_column("incident_reports", "embedding")
    op.drop_column("incidents", "resolved_at")
    op.drop_column("incidents", "resolution_note")
