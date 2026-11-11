"""Create incident_reports table

Revision ID: 0006_incident_reports
Revises: 0005_incidents_and_markers
Create Date: 2026-11-11 21:25:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_incident_reports"
down_revision: str | None = "0005_incidents_and_markers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = JSONB if bind.dialect.name == "postgresql" else sa.JSON

    op.create_table(
        "incident_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "incident_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("affected_services", json_type, nullable=False),
        sa.Column("suggested_fix", json_type, nullable=False),
        sa.Column("evidence", json_type, nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("unsupported_claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_name", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_incident_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_evidence_lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("ix_incident_reports_incident_id", "incident_reports", ["incident_id"])
    op.create_index(
        "ix_incident_reports_incident_version",
        "incident_reports",
        ["incident_id", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_reports_incident_version", table_name="incident_reports")
    op.drop_index("ix_incident_reports_incident_id", table_name="incident_reports")
    op.drop_table("incident_reports")
