"""add_tenantdomain

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tenantdomain',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('domain', sa.String(), nullable=False),
        sa.Column('verification_token', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain', name='uq_tenantdomain_domain'),
    )
    with op.batch_alter_table('tenantdomain', schema=None) as batch_op:
        batch_op.create_index('ix_tenantdomain_tenant_id', ['tenant_id'])
        batch_op.create_index('ix_tenantdomain_domain', ['domain'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tenantdomain')
