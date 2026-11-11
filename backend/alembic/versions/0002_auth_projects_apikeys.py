"""Create users, projects, and api_keys tables

Revision ID: 0002_auth_projects_apikeys
Revises: 0001_enable_pgvector
Create Date: 2026-11-11 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_auth_projects_apikeys"
down_revision: str | None = "0001_enable_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. projects table
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # 3. api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index(
        "ix_api_keys_prefix_revoked", "api_keys", ["key_prefix", "revoked_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_prefix_revoked", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_project_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
