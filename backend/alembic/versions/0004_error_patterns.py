"""Create error_patterns table and link pattern_id foreign key

Revision ID: 0004_error_patterns
Revises: 0003_log_batches_and_events
Create Date: 2026-11-11 19:40:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_error_patterns"
down_revision: str | None = "0003_log_batches_and_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. error_patterns table
    op.create_table(
        "error_patterns",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False, server_default="ERROR"),
        sa.Column("sample_service", sa.String(length=128), nullable=False, server_default="unknown"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_unique_constraint(
        "uq_error_patterns_project_fingerprint",
        "error_patterns",
        ["project_id", "fingerprint"],
    )
    op.create_index("ix_error_patterns_fingerprint", "error_patterns", ["fingerprint"])
    op.create_index(
        "ix_error_patterns_project_total_count",
        "error_patterns",
        ["project_id", "total_count"],
    )
    op.create_index(
        "ix_error_patterns_project_last_seen",
        "error_patterns",
        ["project_id", "last_seen"],
    )


def downgrade() -> None:
    op.drop_index("ix_error_patterns_project_last_seen", table_name="error_patterns")
    op.drop_index("ix_error_patterns_project_total_count", table_name="error_patterns")
    op.drop_index("ix_error_patterns_fingerprint", table_name="error_patterns")
    op.drop_constraint("uq_error_patterns_project_fingerprint", "error_patterns", type_="unique")
    op.drop_table("error_patterns")
