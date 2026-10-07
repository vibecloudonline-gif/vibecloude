"""add tenant_file table

Revision ID: e2f3a4b5c6d7
Revises: d1f2e3a4b5c6
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = "e2f3a4b5c6d7"
down_revision = "d1f2e3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenantfile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("file_type", sqlmodel.sql.sqltypes.AutoString(), server_default="image", nullable=False),
        sa.Column("original_name", sqlmodel.sql.sqltypes.AutoString(), server_default="", nullable=False),
        sa.Column("content_type", sqlmodel.sql.sqltypes.AutoString(), server_default="image/jpeg", nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("public_url", sqlmodel.sql.sqltypes.AutoString(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_tenantfile_tenant", "tenantfile", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tenantfile_tenant", table_name="tenantfile")
    op.drop_table("tenantfile")
