"""Phase 6: FunnelEvent table + ResearchListing verified fields

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funnelevent",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "event_type", name="uq_funnelevent_tenant_type"),
    )
    op.create_index("ix_funnelevent_tenant", "funnelevent", ["tenant_id"])

    op.add_column("researchlisting", sa.Column("source_date", sa.DateTime(), nullable=True))
    op.add_column("researchlisting", sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("researchlisting", sa.Column("verification_details", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("researchlisting", "verification_details")
    op.drop_column("researchlisting", "verified")
    op.drop_column("researchlisting", "source_date")
    op.drop_index("ix_funnelevent_tenant", table_name="funnelevent")
    op.drop_table("funnelevent")
