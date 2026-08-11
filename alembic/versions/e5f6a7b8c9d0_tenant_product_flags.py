"""tenant_product_flags

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-11 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tenant', schema=None) as batch_op:
        batch_op.add_column(sa.Column('has_erp', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('has_ecommerce', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('has_landing', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('has_alexio', sa.Boolean(), nullable=False, server_default=sa.true()))

    # Data-migration: mapear el viejo product_plan (si la columna todavia
    # existe) a los flags nuevos, para no perder lo que ya estaba elegido.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('tenant')]
    if 'product_plan' in columns:
        conn.execute(sa.text(
            "UPDATE tenant SET has_erp = false, has_ecommerce = true, has_landing = true "
            "WHERE product_plan = 'ecommerce'"
        ))
        conn.execute(sa.text(
            "UPDATE tenant SET has_erp = false, has_ecommerce = false, has_landing = true "
            "WHERE product_plan = 'landing'"
        ))
        with op.batch_alter_table('tenant', schema=None) as batch_op:
            batch_op.drop_column('product_plan')

    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ecommerce_connected_to_erp', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tenant', schema=None) as batch_op:
        batch_op.add_column(sa.Column('product_plan', sa.String(), nullable=False, server_default='full'))
        batch_op.drop_column('has_erp')
        batch_op.drop_column('has_ecommerce')
        batch_op.drop_column('has_landing')
        batch_op.drop_column('has_alexio')
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('ecommerce_connected_to_erp')
