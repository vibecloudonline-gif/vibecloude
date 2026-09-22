"""Add ForecastProfile table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecastprofile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("researchproject.id"), nullable=False),
        sa.Column("business_type", sa.String(), nullable=False, server_default="physical_product"),
        sa.Column("business_stage", sa.String(), nullable=False, server_default="idea"),
        sa.Column("product_category", sa.String(), nullable=True),
        sa.Column("target_market", sa.String(), nullable=False, server_default="national"),
        sa.Column("target_audience", sa.String(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("desired_margin_pct", sa.Integer(), nullable=True),
        sa.Column("known_competitor_prices", sa.String(), nullable=True),
        sa.Column("pricing_strategy", sa.String(), nullable=False, server_default="competitive"),
        sa.Column("geography", sa.String(), nullable=True),
        sa.Column("seasonality_notes", sa.String(), nullable=True),
        sa.Column("competition_level", sa.String(), nullable=False, server_default="medium"),
        sa.Column("differentiator", sa.String(), nullable=True),
        sa.Column("launch_target_date", sa.String(), nullable=True),
        sa.Column("monthly_revenue_target", sa.Numeric(12, 2), nullable=True),
        sa.Column("growth_expectation", sa.String(), nullable=False, server_default="moderate"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_forecastprofile_tenant", "forecastprofile", ["tenant_id"])
    op.create_index("uq_forecastprofile_project", "forecastprofile", ["project_id"], unique=True)


def downgrade() -> None:
    op.drop_table("forecastprofile")
