"""Tests for the courses module."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_API_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from database.models import Course, Lesson, Enrollment, LessonProgress, Tenant, User, Settings
from database.session import get_session
from main import app
from services.auth_service import AuthService


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from core.limiter import limiter, HAS_SLOWAPI
    if HAS_SLOWAPI:
        limiter.reset()
    yield


def _make_tenant(session, has_courses=True):
    tenant = Tenant(name="TestCo", subdomain="testco", has_landing=True, has_ecommerce=True, has_courses=has_courses, nivel=3)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(
        username="admin", role="admin", tenant_id=tenant.id,
        password_hash=AuthService.get_password_hash("TestPass123!"),
    )
    session.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="TestCo")
    session.add(settings)
    session.commit()
    session.refresh(user)
    return tenant, user


def _login(client):
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)


# --- Flag gating ---

def test_courses_blocked_without_flag(client, session):
    _make_tenant(session, has_courses=False)
    _login(client)
    resp = client.get("/panel/cursos")
    assert resp.status_code == 403


def test_courses_accessible_with_flag(client, session):
    _make_tenant(session, has_courses=True)
    _login(client)
    resp = client.get("/panel/cursos")
    assert resp.status_code == 200


# --- CRUD ---

def test_create_course(client, session):
    tenant, user = _make_tenant(session)
    _login(client)
    resp = client.post("/panel/cursos", data={
        "title": "Curso de Prueba",
        "description": "Descripción",
        "category": "Tech",
        "price": "100",
    }, follow_redirects=False)
    assert resp.status_code == 302
    course = session.exec(
        __import__("sqlmodel").select(Course).where(Course.tenant_id == tenant.id)
    ).first()
    assert course is not None
    assert course.title == "Curso de Prueba"
    assert course.slug == "curso-de-prueba"


def test_edit_course(client, session):
    tenant, user = _make_tenant(session)
    _login(client)
    course = Course(tenant_id=tenant.id, instructor_id=user.id, title="Original", slug="original")
    session.add(course)
    session.commit()
    session.refresh(course)
    resp = client.post(f"/panel/cursos/{course.id}/editar", data={
        "title": "Editado",
        "description": "Nueva desc",
        "category": "",
        "price": "50",
    }, follow_redirects=False)
    assert resp.status_code == 302
    session.refresh(course)
    assert course.title == "Editado"


def test_publish_course(client, session):
    tenant, user = _make_tenant(session)
    _login(client)
    course = Course(tenant_id=tenant.id, instructor_id=user.id, title="Draft", slug="draft", status="draft")
    session.add(course)
    session.commit()
    session.refresh(course)
    resp = client.post(f"/panel/cursos/{course.id}/publicar", follow_redirects=False)
    assert resp.status_code == 302
    session.refresh(course)
    assert course.status == "published"


# --- Lessons ---

def test_add_lesson(client, session):
    tenant, user = _make_tenant(session)
    _login(client)
    course = Course(tenant_id=tenant.id, instructor_id=user.id, title="C1", slug="c1")
    session.add(course)
    session.commit()
    session.refresh(course)
    resp = client.post(f"/panel/cursos/{course.id}/lecciones", data={
        "title": "Lección 1",
        "content_type": "text",
        "content_json": "Contenido de la lección",
        "duration_minutes": "30",
    }, follow_redirects=False)
    assert resp.status_code == 302
    lessons = session.exec(
        __import__("sqlmodel").select(Lesson).where(Lesson.course_id == course.id)
    ).all()
    assert len(lessons) == 1
    assert lessons[0].title == "Lección 1"


# --- Enrollment ---

def test_enrollment_and_progress(session):
    tenant = Tenant(name="T", subdomain="t", has_courses=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(username="student", role="client", tenant_id=tenant.id,
                password_hash=AuthService.get_password_hash("pass"))
    session.add(user)
    course = Course(tenant_id=tenant.id, instructor_id=1, title="C", slug="c", status="published")
    session.add(course)
    session.commit()
    session.refresh(user)
    session.refresh(course)
    lesson = Lesson(course_id=course.id, title="L1", order=1)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    enrollment = Enrollment(course_id=course.id, user_id=user.id, tenant_id=tenant.id)
    session.add(enrollment)
    session.commit()
    session.refresh(enrollment)
    assert enrollment.completed_at is None
    progress = LessonProgress(enrollment_id=enrollment.id, lesson_id=lesson.id, completed=True)
    session.add(progress)
    session.commit()
    assert progress.completed is True


# --- Storefront ---

def test_storefront_courses_list(client, session):
    tenant, user = _make_tenant(session)
    course = Course(tenant_id=tenant.id, instructor_id=user.id, title="Público", slug="publico", status="published")
    session.add(course)
    session.commit()
    resp = client.get("/tienda/cursos")
    assert resp.status_code == 200
    assert "Público" in resp.text
