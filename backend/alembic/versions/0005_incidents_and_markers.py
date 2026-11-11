"""Create incidents, incident_patterns, and deployment_markers tables

Revision ID: 0005_incidents_and_markers
Revises: 0004_error_patterns
Create Date: 2026-11-11 19:50:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_incidents_and_markers"
down_revision: str | None = "0004_error_patterns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = JSONB if bind.dialect.name == "postgresql" else sa.JSON

    # 1. incidents table
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "origin_pattern_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("error_patterns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("affected_services", json_type, nullable=False),
        sa.Column("origin_candidates", json_type, nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incidents_project_id", "incidents", ["project_id"])
    op.create_index("ix_incidents_project_started_at", "incidents", ["project_id", "started_at"])
    op.create_index("ix_incidents_project_status", "incidents", ["project_id", "status"])

    # 2. incident_patterns table
    op.create_table(
        "incident_patterns",
        sa.Column(
            "incident_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "pattern_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("error_patterns.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_in_incident", sa.DateTime(timezone=True), nullable=False),
    )

    # 3. deployment_markers table
    op.create_table(
        "deployment_markers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_deployment_markers_project_ts", "deployment_markers", ["project_id", "ts"])


def downgrade() -> None:
    op.drop_index("ix_deployment_markers_project_ts", table_name="deployment_markers")
    op.drop_table("deployment_markers")

    op.drop_table("incident_patterns")

    op.drop_index("ix_incidents_project_status", table_name="incidents")
    op.drop_index("ix_incidents_project_started_at", table_name="incidents")
    op.drop_index("ix_incidents_project_id", table_name="incidents")
    op.drop_table("incidents")
