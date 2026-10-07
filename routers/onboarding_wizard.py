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
from typing import List, Optional

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from database.models import Product, Settings, Tenant, TenantProfile, User
from database.session import get_session
from services.ai_gateway_service import ai_gateway_service
from services.landing_service import LandingGenerationError, get_landing, save_landing
from services.settings_service import MAX_LOGO_SIZE_BYTES, SettingsService, _has_valid_image_signature
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

MAX_ONBOARDING_PRODUCTS = 5


class _OnboardingProductItem(BaseModel):
    name: str = ""
    price: float = 0.0
    description: str = ""
    category: str = ""


class _OnboardingProductsBody(BaseModel):
    products: List[_OnboardingProductItem] = []

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
    tenant_profile = session.exec(
        select(TenantProfile).where(TenantProfile.tenant_id == tenant_id)
    ).first()
    return _templates().TemplateResponse(
        "onboarding_wizard.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "onboarding_wizard",
            "tenant": tenant,
            "landing": landing,
            "tenant_profile": tenant_profile,
        },
    )


@router.post("/panel/onboarding/negocio")
def onboarding_wizard_negocio(
    request: Request,
    elevator_pitch: str = Form(...),
    business_type: str = Form(...),
    business_stage: str = Form(...),
    target_audience: str = Form(...),
    target_market: str = Form(...),
    monthly_revenue_target: Optional[str] = Form(None),
    main_challenge: str = Form(...),
    competitors: Optional[str] = Form(None),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)

    elevator_pitch = elevator_pitch.strip()
    business_type = business_type.strip()
    business_stage = business_stage.strip()
    target_audience = target_audience.strip()
    main_challenge = main_challenge.strip()

    if not elevator_pitch or not target_audience or not main_challenge:
        raise HTTPException(400, "Completa al menos el pitch, la audiencia y el desafio principal")

    valid_types = ("physical_product", "digital_service", "saas", "marketplace", "gastro", "retail", "other")
    if business_type not in valid_types:
        business_type = "other"

    valid_stages = ("idea", "prototype", "launched", "scaling")
    if business_stage not in valid_stages:
        business_stage = "idea"

    valid_markets = ("local", "national", "regional", "international")
    if target_market not in valid_markets:
        target_market = "local"

    revenue: Optional[Decimal] = None
    if monthly_revenue_target and monthly_revenue_target.strip():
        try:
            revenue = Decimal(monthly_revenue_target.strip())
        except InvalidOperation:
            pass

    from datetime import datetime, timezone
    profile = session.exec(
        select(TenantProfile).where(TenantProfile.tenant_id == tenant_id)
    ).first()

    if profile:
        profile.elevator_pitch = elevator_pitch
        profile.business_type = business_type
        profile.business_stage = business_stage
        profile.target_audience = target_audience
        profile.target_market = target_market
        profile.monthly_revenue_target = revenue
        profile.main_challenge = main_challenge
        profile.competitors = competitors.strip() if competitors else None
        profile.updated_at = datetime.now(timezone.utc)
    else:
        profile = TenantProfile(
            tenant_id=tenant_id,
            elevator_pitch=elevator_pitch,
            business_type=business_type,
            business_stage=business_stage,
            target_audience=target_audience,
            target_market=target_market,
            monthly_revenue_target=revenue,
            main_challenge=main_challenge,
            competitors=competitors.strip() if competitors else None,
        )

    session.add(profile)
    session.commit()
    return {"status": "success", "profile_id": profile.id}


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

        from services.storage_service import upload_image_sync
        from database.models import TenantFile
        ct = reference_image.content_type or "image/jpeg"
        try:
            key, url, size = upload_image_sync(tenant_id, file_content, ct, "style-ref", reference_image.filename)
            reference_image_url = url
            session.add(TenantFile(
                tenant_id=tenant_id, storage_key=key, file_type="style-ref",
                original_name=reference_image.filename or "", content_type=ct,
                size_bytes=size, public_url=url,
            ))
        except ValueError as e:
            raise HTTPException(400, str(e))

    prompt_parts = [
        f"Negocio: {business_name}.",
        f"Rubro: {rubro}.",
        f"Estilo/tono deseado: {tono}.",
    ]
    if color_hint and color_hint.strip():
        prompt_parts.append(f"Preferencia de colores (orientativa, no obligatoria): {color_hint.strip()}.")
    prompt = " ".join(prompt_parts)

    settings_obj = SettingsService.get_or_create_settings(session, tenant_id)
    sf_template = getattr(settings_obj, "storefront_template", None)

    try:
        content, provider_used = await ai_gateway_service.generate_landing_content_cascade(
            prompt,
            reference_image_path=reference_image_path,
            storefront_template=sf_template,
        )
    except LandingGenerationError as exc:
        raise HTTPException(422, str(exc))

    landing = save_landing(session, tenant_id, prompt, content, reference_image_url=reference_image_url)
    from database.models import Tenant
    tenant = session.get(Tenant, tenant_id)
    if tenant:
        tenant.landing_regen_count += 1
        session.add(tenant)
        session.commit()

    from services.funnel_service import track_event
    track_event(session, tenant_id, "sitio_generado", user_id=user.id)
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

    from services.funnel_service import track_event
    track_event(session, tenant_id, "tienda_publicada", user_id=user.id)

    return {"status": "success", "storefront_template": storefront_template, "store_url": "/tienda"}


@router.post("/panel/onboarding/productos")
def onboarding_wizard_productos(
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
    body: _OnboardingProductsBody = Body(...),
):
    SettingsService.ensure_admin(user)
    tenant = _get_tenant_or_404(session, tenant_id)

    products_data = body.products
    if not products_data:
        raise HTTPException(400, "Enviá al menos un producto")
    if len(products_data) > MAX_ONBOARDING_PRODUCTS:
        raise HTTPException(400, f"Máximo {MAX_ONBOARDING_PRODUCTS} productos en onboarding")

    from services.plan_service import check_product_limit

    created = []
    for p in products_data:
        name = (p.name or "").strip()
        if not name:
            continue

        price = p.price if p.price >= 0 else 0.0

        ai_tier = tenant.ai_tier if tenant else "inicial"
        if not check_product_limit(session, tenant_id, ai_tier):
            break

        import uuid as _uuid
        product = Product(
            tenant_id=tenant_id,
            name=name,
            price=price,
            description=(p.description or "").strip() or None,
            category=(p.category or "").strip() or None,
            barcode=f"OB-{_uuid.uuid4().hex[:8].upper()}",
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        created.append({"id": product.id, "name": product.name})

    if created:
        from services.funnel_service import track_event
        track_event(session, tenant_id, "primer_producto", user_id=user.id)

    return {
        "status": "success",
        "products_created": len(created),
        "products": created,
        "catalog_url": "/panel/productos",
        "import_url": "/catalog-import",
    }
