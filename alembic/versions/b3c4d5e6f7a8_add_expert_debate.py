"""add_expert_debate

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-22 10:00:00.000000

Debate de Personas: expertos humanos calificados validan ofertas.
"""
from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expertdebate",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offer.id"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_expertdebate_offer_tenant", "expertdebate", ["offer_id", "tenant_id"])

    op.create_table(
        "expertopinion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("debate_id", sa.Integer(), sa.ForeignKey("expertdebate.id"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("expert_name", sa.String(), nullable=False),
        sa.Column("expert_role", sa.String(), nullable=False),
        sa.Column("expert_email", sa.String(), nullable=True),
        sa.Column("opinion_text", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False, server_default="neutral"),
        sa.Column("suggestions", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="ai_generated"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expertopinion_debate", "expertopinion", ["debate_id"])


def downgrade() -> None:
    op.drop_index("ix_expertopinion_debate", table_name="expertopinion")
    op.drop_table("expertopinion")
    op.drop_index("ix_expertdebate_offer_tenant", table_name="expertdebate")
    op.drop_table("expertdebate")
