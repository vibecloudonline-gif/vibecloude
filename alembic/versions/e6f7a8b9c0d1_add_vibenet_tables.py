"""add vibenet tables

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-24 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "businesscategory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("businesscategory.id"), nullable=True),
        sa.UniqueConstraint("slug", name="uq_businesscategory_slug"),
    )
    op.create_index("ix_businesscategory_slug", "businesscategory", ["slug"])

    op.create_table(
        "businessprofile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("tagline", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("banner_url", sa.String(), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("businesscategory.id"), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=False, server_default="AR"),
        sa.Column("website_url", sa.String(), nullable=True),
        sa.Column("social_links_json", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("avg_rating", sa.Numeric(3, 2), nullable=False, server_default="0.00"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_businessprofile_tenant"),
    )
    op.create_index("ix_businessprofile_tenant_id", "businessprofile", ["tenant_id"])

    op.create_table(
        "connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("to_tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("connection_type", sa.String(), nullable=False, server_default="partner"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("from_tenant_id", "to_tenant_id", name="uq_connection_pair"),
        sa.CheckConstraint("from_tenant_id != to_tenant_id", name="ck_connection_no_self"),
    )
    op.create_index("ix_connection_from", "connection", ["from_tenant_id"])
    op.create_index("ix_connection_to", "connection", ["to_tenant_id"])

    op.create_table(
        "conversation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_a_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("tenant_b_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("unread_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unread_b", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_a_id", "tenant_b_id", name="uq_conversation_pair"),
    )
    op.create_index("ix_conversation_tenant_a_id", "conversation", ["tenant_a_id"])
    op.create_index("ix_conversation_tenant_b_id", "conversation", ["tenant_b_id"])

    op.create_table(
        "netmessage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("sender_tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_netmessage_conversation", "netmessage", ["conversation_id", "created_at"])
    op.create_index("ix_netmessage_conversation_id", "netmessage", ["conversation_id"])

    op.create_table(
        "businessreview",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("businessprofile.id"), nullable=False),
        sa.Column("reviewer_tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_verified_connection", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("owner_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_businessreview_profile", "businessreview", ["profile_id"])
    op.create_index("ix_businessreview_profile_id", "businessreview", ["profile_id"])

    op.create_table(
        "feedpost",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("post_type", sa.String(), nullable=False, server_default="article"),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedpost_tenant", "feedpost", ["tenant_id"])
    op.create_index("ix_feedpost_created", "feedpost", ["created_at"])
    op.create_index("ix_feedpost_tenant_id", "feedpost", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("feedpost")
    op.drop_table("businessreview")
    op.drop_table("netmessage")
    op.drop_table("conversation")
    op.drop_table("connection")
    op.drop_table("businessprofile")
    op.drop_table("businesscategory")
