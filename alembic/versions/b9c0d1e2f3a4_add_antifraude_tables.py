"""add antifraude tables

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tenant: comisión + regen count
    op.add_column("tenant", sa.Column("platform_commission_pct", sa.Numeric(5, 2), nullable=False, server_default="5.00"))
    op.add_column("tenant", sa.Column("landing_regen_count", sa.Integer(), nullable=False, server_default="0"))

    # Sale: comisión + fraud flag
    op.add_column("sale", sa.Column("platform_commission", sa.Numeric(12, 2), nullable=False, server_default="0.00"))
    op.add_column("sale", sa.Column("fraud_flag", sa.String(), nullable=True))

    # BusinessReview: verified purchase
    op.add_column("businessreview", sa.Column("is_verified_purchase", sa.Boolean(), nullable=False, server_default="0"))

    # OrderFingerprint
    op.create_table(
        "orderfingerprint",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("buyer_ip", sa.String(), nullable=True),
        sa.Column("buyer_user_agent", sa.String(), nullable=True),
        sa.Column("buyer_session_id", sa.String(), nullable=True),
        sa.Column("buyer_device_hash", sa.String(), nullable=True),
        sa.Column("buyer_email", sa.String(), nullable=True),
        sa.Column("buyer_cuit", sa.String(), nullable=True),
        sa.Column("is_self_purchase", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("fraud_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fraud_reasons", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_orderfingerprint_sale", "orderfingerprint", ["sale_id"])
    op.create_index("ix_orderfingerprint_tenant", "orderfingerprint", ["tenant_id"])

    # ReturnRequest
    op.create_table(
        "returnrequest",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("resolution_note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_returnrequest_tenant", "returnrequest", ["tenant_id"])
    op.create_index("ix_returnrequest_sale", "returnrequest", ["sale_id"])

    # TrustMetrics
    op.create_table(
        "trustmetrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("total_sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_buyers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_revenue", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("total_commission", sa.Numeric(14, 2), nullable=False, server_default="0.00"),
        sa.Column("return_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("complaint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("self_purchase_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fraud_flags_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("return_rate_pct", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id"),
    )


def downgrade() -> None:
    op.drop_table("trustmetrics")
    op.drop_table("returnrequest")
    op.drop_table("orderfingerprint")
    op.drop_column("sale", "fraud_flag")
    op.drop_column("sale", "platform_commission")
    op.drop_column("businessreview", "is_verified_purchase")
    op.drop_column("tenant", "landing_regen_count")
    op.drop_column("tenant", "platform_commission_pct")
