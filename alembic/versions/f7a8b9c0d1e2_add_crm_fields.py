"""add crm fields

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-24 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("client", schema=None) as batch_op:
        batch_op.add_column(sa.Column("crm_external_id", sa.String(), nullable=True))
        batch_op.create_index("ix_client_crm_external_id", ["crm_external_id"])

    with op.batch_alter_table("sale", schema=None) as batch_op:
        batch_op.add_column(sa.Column("crm_external_id", sa.String(), nullable=True))
        batch_op.create_index("ix_sale_crm_external_id", ["crm_external_id"])

    op.create_table(
        "crmsynclog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("sync_type", sa.String(), nullable=False, server_default="full"),
        sa.Column("direction", sa.String(), nullable=False, server_default="pull"),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("contacts_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_crmsynclog_tenant", "crmsynclog", ["tenant_id", "created_at"])
    op.create_index("ix_crmsynclog_tenant_id", "crmsynclog", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("crmsynclog")
    with op.batch_alter_table("sale", schema=None) as batch_op:
        batch_op.drop_index("ix_sale_crm_external_id")
        batch_op.drop_column("crm_external_id")
    with op.batch_alter_table("client", schema=None) as batch_op:
        batch_op.drop_index("ix_client_crm_external_id")
        batch_op.drop_column("crm_external_id")
