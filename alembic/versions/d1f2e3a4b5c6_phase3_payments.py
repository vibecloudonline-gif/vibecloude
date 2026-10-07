"""phase3 payments: TenantPaymentConfig, PlatformPayment cols, ProcessedWebhook transition

Revision ID: d1f2e3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = "d1f2e3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenantpaymentconfig",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("access_token_enc", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("refresh_token_enc", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("merchant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenantpaymentconfig_tenant_provider"),
    )
    op.create_index("ix_tenantpaymentconfig_tenant", "tenantpaymentconfig", ["tenant_id"])

    op.add_column(
        "platformpayment",
        sa.Column("external_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "platformpayment",
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )

    op.add_column(
        "processed_webhooks",
        sa.Column("status_transition", sqlmodel.sql.sqltypes.AutoString(), server_default="", nullable=False),
    )
    op.execute("DROP INDEX IF EXISTS ix_processed_webhooks_event_id")
    with op.batch_alter_table("processed_webhooks") as batch:
        batch.create_unique_constraint(
            "uq_webhook_event_transition",
            ["event_id", "source", "status_transition"],
        )


def downgrade() -> None:
    with op.batch_alter_table("processed_webhooks") as batch:
        batch.drop_constraint("uq_webhook_event_transition", type_="unique")
    op.drop_column("processed_webhooks", "status_transition")

    op.drop_column("platformpayment", "commission_amount")
    op.drop_column("platformpayment", "external_ref")

    op.drop_index("ix_tenantpaymentconfig_tenant", table_name="tenantpaymentconfig")
    op.drop_table("tenantpaymentconfig")
