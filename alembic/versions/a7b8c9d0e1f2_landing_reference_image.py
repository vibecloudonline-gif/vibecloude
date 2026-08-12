"""landing_reference_image

Revision ID: a7b8c9d0e1f2
Revises: e5f6a7b8c9d0
Create Date: 2026-08-11 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('landingpage', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reference_image_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('landingpage', schema=None) as batch_op:
        batch_op.drop_column('reference_image_url')
