"""alexio_validation_pipeline

Revision ID: f0a1b2c3d4e5
Revises: e1f2a3b4c5d6
Create Date: 2026-09-16 12:00:00.000000

Crea las 8 tablas del pipeline de validacion de Alex IO:
researchproject, researchlisting, researchdemand, competitoranalysis,
offer, validationdebate, debateobjection, alexagentcontext.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. researchproject
    op.create_table(
        "researchproject",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("project_type", sqlmodel.sql.sqltypes.AutoString(), server_default="physical_product", nullable=False),
        sa.Column("query_description", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("reference_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("factory_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_researchproject_tenant_id", "researchproject", ["tenant_id"])
    op.create_index("ix_researchproject_tenant_status", "researchproject", ["tenant_id", "status"])

    # 2. researchlisting
    op.create_table(
        "researchlisting",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sqlmodel.sql.sqltypes.AutoString(), server_default="USD", nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["researchproject.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_researchlisting_project_id", "researchlisting", ["project_id"])

    # 3. researchdemand
    op.create_table(
        "researchdemand",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("confidence_level", sqlmodel.sql.sqltypes.AutoString(), server_default="no_disponible", nullable=False),
        sa.Column("estimated_monthly_volume", sa.Integer(), nullable=True),
        sa.Column("source_description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["researchproject.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_researchdemand_project"),
    )
    op.create_index("ix_researchdemand_project_id", "researchdemand", ["project_id"])

    # 4. competitoranalysis
    op.create_table(
        "competitoranalysis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value_proposition", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("price_info", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("guarantees", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("objections_addressed", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("analysis_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("user_confirmed", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["researchproject.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_competitoranalysis_project_id", "competitoranalysis", ["project_id"])

    # 5. offer
    op.create_table(
        "offer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value_proposition", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("price_structure", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("cta_text", sqlmodel.sql.sqltypes.AutoString(), server_default="Comprar ahora", nullable=False),
        sa.Column("differentiators_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["researchproject.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offer_tenant_id", "offer", ["tenant_id"])
    op.create_index("ix_offer_project_id", "offer", ["project_id"])
    op.create_index("ix_offer_tenant_project", "offer", ["tenant_id", "project_id"])

    # 6. validationdebate
    op.create_table(
        "validationdebate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), server_default="in_progress", nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("final_verdict", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("arbiter_summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["offer_id"], ["offer.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id", name="uq_validationdebate_offer"),
    )
    op.create_index("ix_validationdebate_offer_id", "validationdebate", ["offer_id"])

    # 7. debateobjection
    op.create_table(
        "debateobjection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debate_id", sa.Integer(), nullable=False),
        sa.Column("objection_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("objection_source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("severity", sqlmodel.sql.sqltypes.AutoString(), server_default="medium", nullable=False),
        sa.Column("proposed_solution", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("resolution_status", sqlmodel.sql.sqltypes.AutoString(), server_default="pending", nullable=False),
        sa.Column("resolved_text", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["debate_id"], ["validationdebate.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_debateobjection_debate_id", "debateobjection", ["debate_id"])

    # 8. alexagentcontext
    op.create_table(
        "alexagentcontext",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("personality_tone", sqlmodel.sql.sqltypes.AutoString(), server_default="profesional_cercano", nullable=False),
        sa.Column("business_description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("validated_offer_id", sa.Integer(), nullable=True),
        sa.Column("custom_instructions", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("faq_entries_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["validated_offer_id"], ["offer.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_alexagentcontext_tenant"),
    )
    op.create_index("ix_alexagentcontext_tenant_id", "alexagentcontext", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("alexagentcontext")
    op.drop_table("debateobjection")
    op.drop_table("validationdebate")
    op.drop_table("offer")
    op.drop_table("competitoranalysis")
    op.drop_table("researchdemand")
    op.drop_table("researchlisting")
    op.drop_table("researchproject")
