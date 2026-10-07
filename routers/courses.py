"""routers/courses.py — Panel + Storefront de Cursos"""
import json
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select, func
from typing import Optional
from core.limiter import limiter
from database.session import get_session
from database.models import (
    Course, Lesson, Enrollment, LessonProgress,
    Settings, User, Tenant,
)
from services.entitlements import can_use_module, get_blocked_message
from web.dependencies import require_auth, get_tenant, get_settings, get_public_tenant
from web.compat_templates import CompatTemplates

router = APIRouter(tags=["Courses"])

def _templates():
    return CompatTemplates(directory="templates")


def _require_courses(request: Request):
    flags = request.session.get("tenant_flags", {})
    if not flags.get("courses"):
        raise HTTPException(status_code=403, detail="Módulo de cursos no habilitado")


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[áàäâ]", "a", s)
    s = re.sub(r"[éèëê]", "e", s)
    s = re.sub(r"[íìïî]", "i", s)
    s = re.sub(r"[óòöô]", "o", s)
    s = re.sub(r"[úùüû]", "u", s)
    s = re.sub(r"[ñ]", "n", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ========== PANEL (admin) ==========

@router.get("/panel/cursos", response_class=HTMLResponse)
def courses_list(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    courses = session.exec(
        select(Course).where(Course.tenant_id == tenant_id).order_by(Course.created_at.desc())
    ).all()
    stats = {}
    for c in courses:
        count = session.exec(
            select(func.count(Enrollment.id)).where(Enrollment.course_id == c.id)
        ).one()
        stats[c.id] = {"enrollments": count, "lessons": len(c.lessons)}
    return _templates().TemplateResponse("panel_cursos.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "courses", "courses": courses, "stats": stats,
    })


@router.get("/panel/cursos/nuevo", response_class=HTMLResponse)
def course_new_form(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
):
    _require_courses(request)
    return _templates().TemplateResponse("panel_curso_form.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "course_form", "course": None,
    })


@router.post("/panel/cursos", response_class=HTMLResponse)
def course_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    price: str = Form("0"),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    slug = _slugify(title)
    existing = session.exec(
        select(Course).where(Course.tenant_id == tenant_id, Course.slug == slug)
    ).first()
    if existing:
        slug = f"{slug}-{session.exec(select(func.count(Course.id)).where(Course.tenant_id == tenant_id)).one()}"
    course = Course(
        tenant_id=tenant_id,
        instructor_id=user.id,
        title=title,
        slug=slug,
        description=description or None,
        category=category or None,
        price=price,
    )
    session.add(course)
    session.commit()
    session.refresh(course)
    return RedirectResponse(f"/panel/cursos/{course.id}/editar", status_code=302)


@router.get("/panel/cursos/{course_id}/editar", response_class=HTMLResponse)
def course_edit_form(
    request: Request,
    course_id: int,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    return _templates().TemplateResponse("panel_curso_form.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "course_form", "course": course,
    })


@router.post("/panel/cursos/{course_id}/editar", response_class=HTMLResponse)
def course_update(
    request: Request,
    course_id: int,
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    price: str = Form("0"),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    course.title = title
    course.description = description or None
    course.category = category or None
    course.price = price
    course.updated_at = datetime.now(timezone.utc)
    session.add(course)
    session.commit()
    return RedirectResponse(f"/panel/cursos/{course.id}/editar", status_code=302)


@router.post("/panel/cursos/{course_id}/publicar")
def course_publish(
    request: Request,
    course_id: int,
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    course.status = "published" if course.status == "draft" else "draft"
    course.updated_at = datetime.now(timezone.utc)
    session.add(course)
    session.commit()
    return RedirectResponse("/panel/cursos", status_code=302)


@router.get("/panel/cursos/{course_id}/lecciones", response_class=HTMLResponse)
def course_lessons_page(
    request: Request,
    course_id: int,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    lessons = session.exec(
        select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.order)
    ).all()
    return _templates().TemplateResponse("panel_curso_lecciones.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "course_lessons", "course": course, "lessons": lessons,
    })


@router.post("/panel/cursos/{course_id}/lecciones")
def lesson_create(
    request: Request,
    course_id: int,
    title: str = Form(...),
    content_type: str = Form("text"),
    content_json: str = Form(""),
    duration_minutes: Optional[int] = Form(None),
    is_free_preview: bool = Form(False),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    max_order = session.exec(
        select(func.max(Lesson.order)).where(Lesson.course_id == course_id)
    ).one() or 0
    lesson = Lesson(
        course_id=course_id,
        title=title,
        content_type=content_type,
        content_json=content_json or None,
        order=max_order + 1,
        duration_minutes=duration_minutes,
        is_free_preview=is_free_preview,
    )
    session.add(lesson)
    session.commit()
    return RedirectResponse(f"/panel/cursos/{course_id}/lecciones", status_code=302)


@router.post("/panel/cursos/{course_id}/lecciones/{lesson_id}/eliminar")
def lesson_delete(
    request: Request,
    course_id: int,
    lesson_id: int,
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    lesson = session.exec(
        select(Lesson).where(Lesson.id == lesson_id, Lesson.course_id == course_id)
    ).first()
    if lesson:
        session.delete(lesson)
        session.commit()
    return RedirectResponse(f"/panel/cursos/{course_id}/lecciones", status_code=302)


@router.post("/panel/cursos/{course_id}/lecciones/reorder")
def lesson_reorder(
    request: Request,
    course_id: int,
    order: list[int] = Body(...),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    lessons = session.exec(
        select(Lesson).where(Lesson.course_id == course_id)
    ).all()
    by_id = {l.id: l for l in lessons}
    for i, lid in enumerate(order):
        if lid in by_id:
            by_id[lid].order = i + 1
            session.add(by_id[lid])
    session.commit()
    return {"status": "ok"}


@router.get("/panel/cursos/{course_id}/alumnos", response_class=HTMLResponse)
def course_students(
    request: Request,
    course_id: int,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    _require_courses(request)
    course = session.exec(
        select(Course).where(Course.id == course_id, Course.tenant_id == tenant_id)
    ).first()
    if not course:
        raise HTTPException(404)
    enrollments = session.exec(
        select(Enrollment).where(Enrollment.course_id == course_id)
    ).all()
    students = []
    for e in enrollments:
        u = session.get(User, e.user_id)
        total_lessons = session.exec(
            select(func.count(Lesson.id)).where(Lesson.course_id == course_id)
        ).one()
        completed = session.exec(
            select(func.count(LessonProgress.id)).where(
                LessonProgress.enrollment_id == e.id,
                LessonProgress.completed == True,
            )
        ).one()
        students.append({
            "user": u,
            "enrollment": e,
            "completed": completed,
            "total": total_lessons,
            "pct": int(completed / total_lessons * 100) if total_lessons else 0,
        })
    return _templates().TemplateResponse("panel_curso_alumnos.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "course_lessons", "course": course, "students": students,
    })


# ========== STOREFRONT (público) ==========

@router.get("/tienda/cursos", response_class=HTMLResponse)
@limiter.limit("30/minute")
def storefront_courses(
    request: Request,
    session: Session = Depends(get_session),
):
    tenant_id = get_public_tenant(request, session)
    if not tenant_id:
        raise HTTPException(404)
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "courses"):
        raise HTTPException(403, get_blocked_message("courses"))
    settings_obj = session.exec(
        select(Settings).where(Settings.tenant_id == tenant.id)
    ).first()
    courses = session.exec(
        select(Course).where(
            Course.tenant_id == tenant.id, Course.status == "published"
        ).order_by(Course.is_featured.desc(), Course.created_at.desc())
    ).all()
    stats = {}
    for c in courses:
        stats[c.id] = {
            "lessons": session.exec(select(func.count(Lesson.id)).where(Lesson.course_id == c.id)).one(),
            "students": session.exec(select(func.count(Enrollment.id)).where(Enrollment.course_id == c.id)).one(),
        }
    return _templates().TemplateResponse("storefront_cursos.html", {
        "request": request, "settings": settings_obj, "tenant": tenant,
        "courses": courses, "stats": stats,
    })


@router.get("/tienda/cursos/{course_id}", response_class=HTMLResponse)
@limiter.limit("30/minute")
def storefront_course_detail(
    request: Request,
    course_id: int,
    session: Session = Depends(get_session),
):
    tenant_id = get_public_tenant(request, session)
    if not tenant_id:
        raise HTTPException(404)
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "courses"):
        raise HTTPException(403, get_blocked_message("courses"))
    settings_obj = session.exec(
        select(Settings).where(Settings.tenant_id == tenant.id)
    ).first()
    course = session.exec(
        select(Course).where(
            Course.id == course_id, Course.tenant_id == tenant.id,
            Course.status == "published",
        )
    ).first()
    if not course:
        raise HTTPException(404)
    lessons = session.exec(
        select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.order)
    ).all()
    total_students = session.exec(
        select(func.count(Enrollment.id)).where(Enrollment.course_id == course_id)
    ).one()
    enrolled = False
    enrollment = None
    completed_lessons = set()
    course_completed = False
    user_id = request.session.get("user_id")
    if user_id:
        enrollment = session.exec(
            select(Enrollment).where(
                Enrollment.course_id == course_id, Enrollment.user_id == user_id,
            )
        ).first()
        enrolled = enrollment is not None
        if enrollment:
            course_completed = enrollment.completed_at is not None
            progress_rows = session.exec(
                select(LessonProgress).where(
                    LessonProgress.enrollment_id == enrollment.id,
                    LessonProgress.completed == True,
                )
            ).all()
            completed_lessons = {p.lesson_id for p in progress_rows}
    progress_pct = int(len(completed_lessons) / len(lessons) * 100) if lessons and enrolled else 0
    return _templates().TemplateResponse("storefront_curso_detalle.html", {
        "request": request, "settings": settings_obj, "tenant": tenant,
        "course": course, "lessons": lessons,
        "total_students": total_students, "enrolled": enrolled,
        "completed_lessons": completed_lessons, "progress_pct": progress_pct,
        "course_completed": course_completed,
    })


@router.post("/tienda/cursos/{course_id}/inscribir")
def storefront_enroll(
    request: Request,
    course_id: int,
    session: Session = Depends(get_session),
):
    tenant_id = get_public_tenant(request, session)
    if not tenant_id:
        raise HTTPException(404)
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "courses"):
        raise HTTPException(403, get_blocked_message("courses"))
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "Iniciá sesión para inscribirte")
    course = session.exec(
        select(Course).where(
            Course.id == course_id, Course.tenant_id == tenant.id,
            Course.status == "published",
        )
    ).first()
    if not course:
        raise HTTPException(404)
    existing = session.exec(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user_id,
        )
    ).first()
    if not existing:
        enrollment = Enrollment(
            course_id=course_id, user_id=user_id, tenant_id=tenant.id,
        )
        session.add(enrollment)
        session.commit()
    return RedirectResponse(f"/tienda/cursos/{course_id}", status_code=302)


@router.get("/tienda/cursos/{course_id}/leccion/{lesson_order}", response_class=HTMLResponse)
def storefront_lesson(
    request: Request,
    course_id: int,
    lesson_order: int,
    session: Session = Depends(get_session),
):
    tenant_id = get_public_tenant(request, session)
    if not tenant_id:
        raise HTTPException(404)
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "courses"):
        raise HTTPException(403, get_blocked_message("courses"))
    settings_obj = session.exec(
        select(Settings).where(Settings.tenant_id == tenant.id)
    ).first()
    course = session.exec(
        select(Course).where(
            Course.id == course_id, Course.tenant_id == tenant.id,
        )
    ).first()
    if not course:
        raise HTTPException(404)
    lesson = session.exec(
        select(Lesson).where(Lesson.course_id == course_id, Lesson.order == lesson_order)
    ).first()
    if not lesson:
        raise HTTPException(404)
    all_lessons = session.exec(
        select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.order)
    ).all()
    user_id = request.session.get("user_id")
    if not lesson.is_free_preview:
        if not user_id:
            raise HTTPException(401, "Iniciá sesión para ver esta lección")
        enrolled = session.exec(
            select(Enrollment).where(
                Enrollment.course_id == course_id, Enrollment.user_id == user_id,
            )
        ).first()
        if not enrolled:
            return RedirectResponse(f"/tienda/cursos/{course_id}", status_code=302)
    completed = False
    if user_id:
        enrollment = session.exec(
            select(Enrollment).where(
                Enrollment.course_id == course_id, Enrollment.user_id == user_id,
            )
        ).first()
        if enrollment:
            prog = session.exec(
                select(LessonProgress).where(
                    LessonProgress.enrollment_id == enrollment.id,
                    LessonProgress.lesson_id == lesson.id,
                )
            ).first()
            completed = prog.completed if prog else False
    return _templates().TemplateResponse("storefront_leccion.html", {
        "request": request, "settings": settings_obj, "tenant": tenant,
        "course": course, "lesson": lesson, "all_lessons": all_lessons,
        "completed": completed,
    })


@router.post("/tienda/cursos/{course_id}/leccion/{lesson_order}/completar")
def storefront_lesson_complete(
    request: Request,
    course_id: int,
    lesson_order: int,
    session: Session = Depends(get_session),
):
    tenant_id = get_public_tenant(request, session)
    if not tenant_id:
        raise HTTPException(404)
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401)
    enrollment = session.exec(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user_id,
        )
    ).first()
    if not enrollment:
        raise HTTPException(403)
    lesson = session.exec(
        select(Lesson).where(Lesson.course_id == course_id, Lesson.order == lesson_order)
    ).first()
    if not lesson:
        raise HTTPException(404)
    prog = session.exec(
        select(LessonProgress).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.lesson_id == lesson.id,
        )
    ).first()
    if not prog:
        prog = LessonProgress(enrollment_id=enrollment.id, lesson_id=lesson.id)
    prog.completed = True
    session.add(prog)
    total = session.exec(select(func.count(Lesson.id)).where(Lesson.course_id == course_id)).one()
    done = session.exec(
        select(func.count(LessonProgress.id)).where(
            LessonProgress.enrollment_id == enrollment.id,
            LessonProgress.completed == True,
        )
    ).one() + (0 if prog.id else 1)
    if done >= total:
        enrollment.completed_at = datetime.now(timezone.utc)
        session.add(enrollment)
    session.commit()
    next_lesson = session.exec(
        select(Lesson).where(Lesson.course_id == course_id, Lesson.order > lesson_order).order_by(Lesson.order).limit(1)
    ).first()
    if next_lesson:
        return RedirectResponse(f"/tienda/cursos/{course_id}/leccion/{next_lesson.order}", status_code=302)
    return RedirectResponse(f"/tienda/cursos/{course_id}", status_code=302)


@router.get("/tienda/cursos/{course_id}/certificado", response_class=HTMLResponse)
def storefront_certificate(
    request: Request,
    course_id: int,
    session: Session = Depends(get_session),
):
    tenant_id = get_public_tenant(request, session)
    if not tenant_id:
        raise HTTPException(404)
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "courses"):
        raise HTTPException(403, get_blocked_message("courses"))
    settings_obj = session.exec(
        select(Settings).where(Settings.tenant_id == tenant.id)
    ).first()
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "Iniciá sesión para ver tu certificado")
    user = session.get(User, user_id)
    enrollment = session.exec(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.user_id == user_id,
        )
    ).first()
    if not enrollment or not enrollment.completed_at:
        raise HTTPException(403, "Completá el curso para obtener tu certificado")
    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404)
    return _templates().TemplateResponse("storefront_certificado.html", {
        "request": request, "settings": settings_obj, "tenant": tenant,
        "course": course, "user": user, "enrollment": enrollment,
    })
