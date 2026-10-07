"""Add Course, Lesson, Enrollment, LessonProgress tables and has_courses flag

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenant", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("has_courses", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_table(
        "course",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("instructor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("cover_image_url", sa.String(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default="0.00"),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_course_tenant_slug"),
    )
    op.create_index("ix_course_tenant_id", "course", ["tenant_id"])
    op.create_index("ix_course_slug", "course", ["slug"])
    op.create_index("ix_course_tenant_status", "course", ["tenant_id", "status"])

    op.create_table(
        "lesson",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False, server_default="text"),
        sa.Column("content_json", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("is_free_preview", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_lesson_course_id", "lesson", ["course_id"])
    op.create_index("ix_lesson_course_order", "lesson", ["course_id", "order"])

    op.create_table(
        "enrollment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("course.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("course_id", "user_id", name="uq_enrollment_course_user"),
    )
    op.create_index("ix_enrollment_course_id", "enrollment", ["course_id"])
    op.create_index("ix_enrollment_user_id", "enrollment", ["user_id"])
    op.create_index("ix_enrollment_tenant", "enrollment", ["tenant_id"])

    op.create_table(
        "lessonprogress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enrollment_id", sa.Integer(), sa.ForeignKey("enrollment.id"), nullable=False),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("lesson.id"), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("last_position", sa.String(), nullable=True),
        sa.UniqueConstraint("enrollment_id", "lesson_id", name="uq_progress_enrollment_lesson"),
    )
    op.create_index("ix_lessonprogress_enrollment_id", "lessonprogress", ["enrollment_id"])
    op.create_index("ix_lessonprogress_lesson_id", "lessonprogress", ["lesson_id"])


def downgrade() -> None:
    op.drop_table("lessonprogress")
    op.drop_table("enrollment")
    op.drop_table("lesson")
    op.drop_table("course")
    with op.batch_alter_table("tenant", schema=None) as batch_op:
        batch_op.drop_column("has_courses")
