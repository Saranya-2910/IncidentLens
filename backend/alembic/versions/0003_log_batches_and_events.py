"""Create log_batches and log_events tables

Revision ID: 0003_log_batches_and_events
Revises: 0002_auth_projects_apikeys
Create Date: 2026-11-11 11:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_log_batches_and_events"
down_revision: str | None = "0002_auth_projects_apikeys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. log_batches table
    op.create_table(
        "log_batches",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_log_batches_project_id", "log_batches", ["project_id"])
    op.create_index("ix_log_batches_status", "log_batches", ["status"])

    # 2. log_events table
    bind = op.get_bind()
    json_type = JSONB if bind.dialect.name == "postgresql" else sa.JSON

    op.create_table(
        "log_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("log_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service", sa.String(length=128), nullable=False, server_default="unknown"),
        sa.Column("level", sa.String(length=32), nullable=False, server_default="INFO"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("pattern_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("attributes", json_type, nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=False),
    )
    op.create_index("ix_log_events_batch_id", "log_events", ["batch_id"])
    op.create_index("ix_log_events_project_ts", "log_events", ["project_id", "ts"])
    op.create_index("ix_log_events_project_pattern", "log_events", ["project_id", "pattern_id"])
    op.create_index(
        "ix_log_events_project_service_level",
        "log_events",
        ["project_id", "service", "level"],
    )


def downgrade() -> None:
    op.drop_index("ix_log_events_project_service_level", table_name="log_events")
    op.drop_index("ix_log_events_project_pattern", table_name="log_events")
    op.drop_index("ix_log_events_project_ts", table_name="log_events")
    op.drop_index("ix_log_events_batch_id", table_name="log_events")
    op.drop_table("log_events")

    op.drop_index("ix_log_batches_status", table_name="log_batches")
    op.drop_index("ix_log_batches_project_id", table_name="log_batches")
    op.drop_table("log_batches")
