"""add_researchforecast_table

Revision ID: f1a2b3c4d5e6
Revises: f0a1b2c3d4e5
Create Date: 2026-09-19 16:30:00.000000

Crea la tabla researchforecast para TimesFM market forecasting.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "researchforecast",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("price_series", sa.Text(), nullable=True),
        sa.Column("forecast_series", sa.Text(), nullable=True),
        sa.Column("confidence_low", sa.Text(), nullable=True),
        sa.Column("confidence_high", sa.Text(), nullable=True),
        sa.Column("trend_direction", sa.String(), nullable=False, server_default="estable"),
        sa.Column("launch_window", sa.String(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False, server_default="timesfm_simulated"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["researchproject.id"], name="fk_researchforecast_project_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "horizon_days", name="uq_researchforecast_project_horizon"),
    )
    op.create_index("ix_researchforecast_project_id", "researchforecast", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_researchforecast_project_id", table_name="researchforecast")
    op.drop_table("researchforecast")
