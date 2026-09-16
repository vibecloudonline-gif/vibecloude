"""platform_payment

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-08-23 12:00:00.000000

Tabla para registrar pagos de la plataforma (suscripciones, créditos,
storefront checkout). Separada de Sale/PaymentAllocation que son ventas
del tenant a sus clientes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platformpayment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(), server_default="", nullable=False),
        sa.Column("payment_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), server_default="USD", nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), server_default="pending", nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), server_default="", nullable=False),
        sa.Column("metadata_json", sqlmodel.sql.sqltypes.AutoString(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("sale_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["sale_id"], ["sale.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platformpayment_tenant", "platformpayment", ["tenant_id"])
    op.create_index("ix_platformpayment_external", "platformpayment", ["provider", "external_id"])


def downgrade() -> None:
    op.drop_index("ix_platformpayment_external", table_name="platformpayment")
    op.drop_index("ix_platformpayment_tenant", table_name="platformpayment")
    op.drop_table("platformpayment")
