import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from database.models import Course, Lesson, Enrollment, LessonProgress


def test_course_model_fields():
    c = Course(
        tenant_id=1,
        title="Test Course",
        slug="test-course",
        price=Decimal("29.99"),
        category="tech",
        status="draft",
    )
    assert c.title == "Test Course"
    assert c.slug == "test-course"
    assert c.price == Decimal("29.99")
    assert c.status == "draft"
    assert c.is_featured is False


def test_lesson_model_fields():
    l = Lesson(
        course_id=1,
        title="Intro",
        content_type="video",
        content_json="https://www.youtube.com/watch?v=abc123def45",
        order=1,
        duration_minutes=15,
        is_free_preview=True,
    )
    assert l.content_type == "video"
    assert l.order == 1
    assert l.is_free_preview is True
    assert "youtube" in l.content_json


def test_enrollment_model_defaults():
    e = Enrollment(course_id=1, user_id=1, tenant_id=1)
    assert e.completed_at is None


def test_lesson_progress_defaults():
    p = LessonProgress(enrollment_id=1, lesson_id=1)
    assert p.completed is False
    assert p.score is None
    assert p.last_position is None


def test_reorder_endpoint_exists():
    from routers.courses import router
    routes = [r.path for r in router.routes]
    assert "/panel/cursos/{course_id}/lecciones/reorder" in routes


def test_certificate_endpoint_exists():
    from routers.courses import router
    routes = [r.path for r in router.routes]
    assert "/tienda/cursos/{course_id}/certificado" in routes


def test_slugify():
    from routers.courses import _slugify
    assert _slugify("Curso de Programación") == "curso-de-programacion"
    assert _slugify("Café & Más") == "cafe-mas"
    assert _slugify("  Hello World  ") == "hello-world"


def test_lesson_content_types():
    for ct in ("text", "video", "quiz"):
        l = Lesson(course_id=1, title="Test", content_type=ct, order=1)
        assert l.content_type == ct
