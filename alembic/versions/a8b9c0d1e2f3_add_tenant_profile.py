"""add tenant profile

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-25 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenantprofile",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("elevator_pitch", sa.String, nullable=False, server_default=""),
        sa.Column("business_type", sa.String, nullable=False, server_default="other"),
        sa.Column("business_stage", sa.String, nullable=False, server_default="idea"),
        sa.Column("target_audience", sa.String, nullable=False, server_default=""),
        sa.Column("target_market", sa.String, nullable=False, server_default="local"),
        sa.Column("monthly_revenue_target", sa.Numeric(12, 2), nullable=True),
        sa.Column("main_challenge", sa.String, nullable=False, server_default=""),
        sa.Column("competitors", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", name="uq_tenantprofile_tenant"),
    )
    op.create_index("ix_tenantprofile_tenant_id", "tenantprofile", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tenantprofile_tenant_id")
    op.drop_table("tenantprofile")
