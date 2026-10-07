"""Add explanation field to ResearchForecast + providers enhancement

Revision ID: g4a5b6c7d8e9
Revises: f3a4b5c6d7e8
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = "g4a5b6c7d8e9"
down_revision: str = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("researchforecast", sa.Column("explanation", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("researchforecast", "explanation")
