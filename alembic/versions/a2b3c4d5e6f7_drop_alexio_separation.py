"""drop_alexio_separation

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-20 10:00:00.000000

Separación VibeCloud / Alex IO: elimina la tabla alexagentcontext
y la columna has_alexio de tenant. Alex IO es un SaaS independiente
que no debe existir dentro de VibeCloud.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("alexagentcontext")

    with op.batch_alter_table("tenant") as batch_op:
        batch_op.drop_column("has_alexio")


def downgrade() -> None:
    with op.batch_alter_table("tenant") as batch_op:
        batch_op.add_column(
            sa.Column("has_alexio", sa.Boolean(), nullable=True, server_default=sa.text("1"))
        )

    op.create_table(
        "alexagentcontext",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("personality_tone", sa.String(), server_default="profesional_cercano"),
        sa.Column("business_description", sa.String(), nullable=True),
        sa.Column("validated_offer_id", sa.Integer(), sa.ForeignKey("offer.id"), nullable=True),
        sa.Column("custom_instructions", sa.String(), nullable=True),
        sa.Column("faq_entries_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_alexagentcontext_tenant"),
    )
    op.create_index("ix_alexagentcontext_tenant_id", "alexagentcontext", ["tenant_id"])
