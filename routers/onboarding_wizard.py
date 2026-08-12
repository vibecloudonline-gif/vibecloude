"""routers/onboarding_wizard.py — Wizard guiado de onboarding (Fase 4 del
roadmap, sección 7).

Dos ramas independientes, cada una gateada por lo que el tenant tiene
realmente contratado (Tenant.has_landing / Tenant.has_ecommerce, nunca
confiado desde el cliente):

- Landing: preguntas guiadas + imagen de referencia de estilo opcional ->
  arma un prompt y reusa el pipeline ya sanitizado de
  services/landing_service.py (Regla 1.2, nunca HTML/CSS crudo). La imagen
  se manda a Gemini solo como referencia estética -- nunca se copia literal
  (ver SYSTEM_INSTRUCTION en landing_service.py).
- Ecommerce: elegir/confirmar Settings.storefront_template (4 opciones ya
  existentes), sin IA de por medio -- es una selección de un enum cerrado.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from database.models import Settings, Tenant, User
from database.session import get_session
from services.ai_gateway_service import ai_gateway_service
from services.landing_service import LandingGenerationError, get_landing, save_landing
from services.settings_service import MAX_LOGO_SIZE_BYTES, SettingsService, _has_valid_image_signature
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Onboarding Wizard"])

# Subconjunto de SettingsService.SUPPORTED_LOGO_CONTENT_TYPES -- Gemini no
# acepta SVG/GIF como input de imagen, solo raster estático.
REFERENCE_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
REFERENCE_IMAGE_DIR = os.path.join("static", "images", "style-refs")


def _templates():
    return CompatTemplates(directory="templates")


def _get_tenant_or_404(session: Session, tenant_id: int) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant no encontrado")
    return tenant


@router.get("/panel/onboarding", response_class=HTMLResponse)
def onboarding_wizard_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)
    tenant = _get_tenant_or_404(session, tenant_id)
    landing = get_landing(session, tenant_id)
    return _templates().TemplateResponse(
        "onboarding_wizard.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "onboarding_wizard",
            "tenant": tenant,
            "landing": landing,
        },
    )


@router.post("/panel/onboarding/landing")
async def onboarding_wizard_landing(
    request: Request,
    business_name: str = Form(...),
    rubro: str = Form(...),
    tono: str = Form(...),
    color_hint: Optional[str] = Form(None),
    reference_image: Optional[UploadFile] = File(None),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)
    tenant = _get_tenant_or_404(session, tenant_id)
    if not tenant.has_landing:
        raise HTTPException(403, "Tu cuenta no tiene contratado Landing con IA")

    business_name = business_name.strip()
    rubro = rubro.strip()
    tono = tono.strip()
    if not business_name or not rubro or not tono:
        raise HTTPException(400, "Contame el nombre del negocio, el rubro y el estilo que buscás")

    reference_image_path: Optional[str] = None
    reference_image_url: Optional[str] = None
    if reference_image is not None and reference_image.filename:
        if reference_image.content_type not in REFERENCE_IMAGE_CONTENT_TYPES:
            raise HTTPException(400, "La imagen de referencia debe ser PNG, JPEG o WEBP")

        file_content = reference_image.file.read()
        if len(file_content) > MAX_LOGO_SIZE_BYTES:
            raise HTTPException(400, f"La imagen no puede superar los {MAX_LOGO_SIZE_BYTES // (1024*1024)} MB")
        if not _has_valid_image_signature(file_content[:16]):
            raise HTTPException(400, "El archivo no es una imagen válida")

        os.makedirs(REFERENCE_IMAGE_DIR, exist_ok=True)
        _, ext = os.path.splitext(reference_image.filename)
        ext = ext.lower() or ".jpg"
        file_name = f"tenant{tenant_id}-{uuid.uuid4().hex}{ext}"
        reference_image_path = os.path.join(REFERENCE_IMAGE_DIR, file_name)
        with open(reference_image_path, "wb") as buffer:
            buffer.write(file_content)
        # URL publica con forward-slashes literal, independiente del path de
        # filesystem -- os.path.join usa backslash en Windows, que rompería
        # la URL servida por StaticFiles (siempre usa "/").
        reference_image_url = f"/static/images/style-refs/{file_name}"

    prompt_parts = [
        f"Negocio: {business_name}.",
        f"Rubro: {rubro}.",
        f"Estilo/tono deseado: {tono}.",
    ]
    if color_hint and color_hint.strip():
        prompt_parts.append(f"Preferencia de colores (orientativa, no obligatoria): {color_hint.strip()}.")
    prompt = " ".join(prompt_parts)

    try:
        content, provider_used = await ai_gateway_service.generate_landing_content_cascade(
            prompt, reference_image_path=reference_image_path
        )
    except LandingGenerationError as exc:
        raise HTTPException(422, str(exc))

    landing = save_landing(session, tenant_id, prompt, content, reference_image_url=reference_image_url)
    return {
        "status": "success",
        "landing_id": landing.id,
        "content": content.model_dump(),
        "reference_image_url": reference_image_url,
        "provider_used": provider_used,
        "public_url": "/landing",
        "editor_url": "/panel/landing",
    }


@router.post("/panel/onboarding/ecommerce")
def onboarding_wizard_ecommerce(
    request: Request,
    storefront_template: str = Form(...),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)
    tenant = _get_tenant_or_404(session, tenant_id)
    if not tenant.has_ecommerce:
        raise HTTPException(403, "Tu cuenta no tiene contratado Ecommerce")

    settings_obj = SettingsService.get_or_create_settings(session, tenant_id=tenant_id)
    SettingsService.apply_updates(session=session, settings=settings_obj, storefront_template=storefront_template)
    return {"status": "success", "storefront_template": storefront_template, "store_url": "/tienda"}
