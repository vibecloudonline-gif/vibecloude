"""add tenant nivel

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant", sa.Column("nivel", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tenant", sa.Column("nivel_since", sa.DateTime(), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_column("tenant", "nivel_since")
    op.drop_column("tenant", "nivel")
