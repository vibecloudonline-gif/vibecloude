from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import json
import re
import logging
from datetime import datetime

from database.session import get_session
from database.models import User, Tenant
from web.dependencies import get_current_user, get_current_tenant, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI Services"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

class CopyRequest(BaseModel):
    product_name: str
    category: Optional[str] = None
    context: Optional[str] = None

class ThemeRequest(BaseModel):
    description: str

class ImageRequest(BaseModel):
    prompt: str

class PredictProductRequest(BaseModel):
    name: str
    category: Optional[str] = None
    price: float = 0.0
    description: Optional[str] = None

@router.post("/copy")
async def generate_copy(req: CopyRequest, db: Session = Depends(get_session), current_user: User = Depends(require_auth)):
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    from services.ai.contracts import AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    prompt = f"Genera 3 opciones de copy de ventas persuasivo para el producto '{req.product_name}'. Categoría: {req.category}. Contexto extra: {req.context}. Devuelve solo los textos numerados."

    request = AIRequest(
        task="copy_generation",
        tenant_id=current_user.tenant_id,
        messages=[AIMessage(role="user", content=prompt)],
        provider="gemini",
        model=DEFAULT_GEMINI_MODEL,
    )

    try:
        response = await ai_gateway.generate(request)
        return {"success": True, "copies": response.content.split("\n")}
    except Exception as e:
        logger.error(f"Error generando copy: {e}")
        raise HTTPException(status_code=500, detail="Error interno al generar copy de ventas.")

@router.post("/theme")
async def generate_theme(req: ThemeRequest, db: Session = Depends(get_session), current_user: User = Depends(require_auth)):
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    from services.ai.contracts import AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    prompt = f"""Crea una paleta de colores para una tienda online descrita como: '{req.description}'.
    Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta (reemplazando los hex por los sugeridos):
    {{
      "bg": "#ffffff",
      "primary": "#000000",
      "secondary": "#cccccc",
      "cardBg": "#f0f0f0",
      "border": "#dddddd",
      "text": "#333333",
      "shadow": "0 4px 6px rgba(0,0,0,0.1)"
    }}
    No agregues markdown, ni backticks, ni comentarios."""

    request = AIRequest(
        task="theme_generation",
        tenant_id=current_user.tenant_id,
        messages=[AIMessage(role="user", content=prompt)],
        provider="gemini",
        model=DEFAULT_GEMINI_MODEL,
        structured_output=True,
    )

    try:
        response = await ai_gateway.generate(request)
        text = response.content.replace('```json', '').replace('```', '').strip()
        theme_json = json.loads(text)
        return {"success": True, "theme": theme_json}
    except Exception as e:
        logger.error(f"Error generando tema: {e}")
        raise HTTPException(status_code=500, detail="Error interno al generar paleta de colores.")


@router.post("/predict-product")
async def predict_product(
    req: PredictProductRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(require_auth),
):
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    from decimal import Decimal
    from services.ai_gateway_service import AIGatewayService

    return await AIGatewayService.predict_product_success(
        session=db,
        tenant_id=current_user.tenant_id,
        name=req.name,
        category=req.category,
        price=Decimal(str(req.price)),
        description=req.description,
    )


# Basic in-memory rate limiting for AI calls per tenant
_AI_CALL_LOGS: Dict[int, list] = {}

def _check_ai_rate_limit(tenant_id: int):
    import time
    limit = int(os.getenv("AI_RATE_LIMIT_PER_HOUR", "20"))
    now = time.time()
    cutoff = now - 3600

    tenant_calls = _AI_CALL_LOGS.get(tenant_id, [])
    recent_calls = [t for t in tenant_calls if t > cutoff]

    if len(recent_calls) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Límite de cuota de IA alcanzado ({limit} peticiones/hora)."
        )

    recent_calls.append(now)
    _AI_CALL_LOGS[tenant_id] = recent_calls

@router.get("/onboarding/texts")
async def get_onboarding_texts(
    step: str,
    niche: str = "general",
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    from services.gemini_service import GeminiService
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Servicio de IA no configurado.")
    try:
        texts = await GeminiService.generate_onboarding_text(step, niche, GEMINI_API_KEY)
        return texts
    except Exception as e:
        logger.error(f"Error en AI onboarding/texts: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")

@router.post("/image")
async def generate_image(req: ImageRequest, db: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)
    return {"success": True, "image_url": "https://placehold.co/600x400/png?text=Generated+Image"}

class ProductDescRequest(BaseModel):
    product_name: str
    features: str

@router.post("/product-description")
async def generate_product_description(
    req: ProductDescRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    from services.ai.contracts import AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    system_instruction = "Eres un experto en copywriting para e-commerce."
    prompt = f"""Genera una descripción persuasiva, atractiva y optimizada para SEO para el siguiente producto:
    Producto: {req.product_name}
    Características clave: {req.features}

    Devuelve la descripción en formato HTML limpio (solo etiquetas <p>, <ul>, <li>, <strong>) para insertarlo directo en la web.
    NO devuelvas bloques de código (```html), devuelve directamente el string HTML."""

    request = AIRequest(
        task="product_description",
        tenant_id=current_user.tenant_id,
        messages=[AIMessage(role="user", content=prompt)],
        system_prompt=system_instruction,
        provider="gemini",
        model=DEFAULT_GEMINI_MODEL,
    )

    try:
        response = await ai_gateway.generate(request)
        desc = response.content.replace('```html', '').replace('```', '').strip()
        return {"success": True, "description": desc}
    except Exception as e:
        logger.error(f"Error en AI product-description: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")

class LandingCopyRequest(BaseModel):
    niche: str
    audience: str
    tone: str

@router.post("/landing-copy")
async def generate_landing_copy(
    req: LandingCopyRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    from services.ai.contracts import AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    system_instruction = "Eres un experto creador de Landing Pages y copywriter para marketing digital."
    prompt = f"""Crea el texto para una Landing Page de un negocio de: {req.niche}.
    El público objetivo es: {req.audience}.
    El tono de la marca debe ser: {req.tone}.

    Debes retornar EXCLUSIVAMENTE un objeto JSON válido con esta estructura exacta:
    {{
        "h1": "Título principal que llame la atención",
        "h2": "Subtítulo que explique el beneficio principal",
        "bullets": ["Dolor que soluciona 1", "Dolor que soluciona 2", "Dolor que soluciona 3"],
        "cta": "Llamado a la acción potente"
    }}
    No agregues markdown ni texto fuera del JSON."""

    request = AIRequest(
        task="landing_copy",
        tenant_id=current_user.tenant_id,
        messages=[AIMessage(role="user", content=prompt)],
        system_prompt=system_instruction,
        provider="gemini",
        model=DEFAULT_GEMINI_MODEL,
        structured_output=True,
    )

    try:
        response = await ai_gateway.generate(request)
        text = response.content.replace('```json', '').replace('```', '').strip()
        copy = json.loads(text)
        return {"success": True, "copy": copy}
    except Exception as e:
        logger.error(f"Error en AI landing-copy: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")

class ChatRequest(BaseModel):
    history: list
    new_message: str
    system_instruction: str = "Eres un asistente virtual de ventas amable."

@router.post("/chat")
async def chat_bot_response(
    req: ChatRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Autenticación requerida.")
    if current_user.tenant_id:
        _check_ai_rate_limit(current_user.tenant_id)

    from services.ai.contracts import AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    messages = []
    for turn in req.history:
        role = turn.get("role", "user")
        text = turn.get("parts", [{}])[0].get("text", "")
        messages.append(AIMessage(role=role, content=text))
    messages.append(AIMessage(role="user", content=req.new_message))

    request = AIRequest(
        task="chat",
        tenant_id=current_user.tenant_id,
        messages=messages,
        system_prompt=req.system_instruction,
        provider="gemini",
        model=DEFAULT_GEMINI_MODEL,
    )

    try:
        response = await ai_gateway.generate(request)
        return {"success": True, "response": response.content}
    except Exception as e:
        logger.error(f"Error en AI chat: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servicio de IA")


@router.post("/alex-io")
async def alex_io_chat(
    req: ChatRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant)
):
    from services.ai_brain_service import ai_brain_service
    try:
        response_text = await ai_brain_service.chat_response(
            session=db,
            tenant_id=tenant_id,
            history=req.history,
            new_message=req.new_message,
            system_instruction=req.system_instruction
        )
        return {"success": True, "response": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UIConfigTheme(BaseModel):
    primary_color: str
    secondary_color: str
    mode: str
    background_gradient: Optional[str] = None
    border_radius: Optional[str] = "8px"
    font_family: Optional[str] = "Outfit"

class TemplateStudioRequest(BaseModel):
    prompt: str
    page_name: str = "storefront_home"

def sanitize_css_property(value: str) -> str:
    if not value:
        return ""
    lower_val = value.lower()
    unsafe_patterns = [
        r"url\s*\(",
        r"expression\s*\(",
        r"javascript\s*:",
        r"<script",
        r"onload",
        r"onerror",
        r"import\s+",
    ]
    for pattern in unsafe_patterns:
        if re.search(pattern, lower_val):
            raise ValueError(f"Estilo CSS no seguro detectado: {value}")
    sanitized = re.sub(r"[^\w\s\d#\(\)%\-,\.\x27\x22:/]", "", value)
    return sanitized

@router.post("/template-studio")
async def ai_template_studio(
    req: TemplateStudioRequest,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant)
):
    from services.ai_brain_service import ai_brain_service
    from database.models import UIConfig

    current_config = db.exec(
        select(UIConfig).where(UIConfig.tenant_id == tenant_id, UIConfig.page_name == req.page_name)
    ).first()

    current_context = ""
    if current_config:
        current_context = f"Configuración actual: {current_config.theme_json}"

    system_instruction = (
        "Eres un diseñador web experto. Tu tarea es generar una paleta de colores y estilos en formato JSON. "
        "Debes responder ÚNICAMENTE con un objeto JSON válido que cumpla este esquema:\n"
        "{\n"
        "  \"primary_color\": \"#HexColor\",\n"
        "  \"secondary_color\": \"#HexColor\",\n"
        "  \"mode\": \"light\" o \"dark\",\n"
        "  \"background_gradient\": \"linear-gradient(to right, #Hex1, #Hex2)\",\n"
        "  \"border_radius\": \"8px\" o similar,\n"
        "  \"font_family\": \"Outfit\" o \"Inter\" o \"Roboto\" o \"Space Grotesk\" o \"DM Sans\"\n"
        "}\n"
        "No agregues markdown ni explicaciones adicionales, solo el JSON estructurado."
    )

    prompt = f"Instrucción del usuario: {req.prompt}\n{current_context}"

    try:
        response_text = await ai_brain_service.chat_response(
            session=db,
            tenant_id=tenant_id,
            history=[],
            new_message=prompt,
            system_instruction=system_instruction,
            model_name="gemini-3.1-pro"
        )

        clean_json_str = response_text.replace("```json", "").replace("```", "").strip()
        theme_dict = json.loads(clean_json_str)
        validated_theme = UIConfigTheme(**theme_dict)

        sanitized_theme = {
            "primary_color": sanitize_css_property(validated_theme.primary_color),
            "secondary_color": sanitize_css_property(validated_theme.secondary_color),
            "mode": validated_theme.mode if validated_theme.mode in ["light", "dark"] else "dark",
            "background_gradient": sanitize_css_property(validated_theme.background_gradient or ""),
            "border_radius": sanitize_css_property(validated_theme.border_radius or "8px"),
            "font_family": validated_theme.font_family if validated_theme.font_family in ["Outfit", "Inter", "Roboto", "Space Grotesk", "DM Sans"] else "Outfit"
        }

        if not current_config:
            current_config = UIConfig(
                tenant_id=tenant_id,
                page_name=req.page_name,
                layout_json=json.dumps({"modules": ["Header", "StorefrontHero", "StorefrontCatalog", "Footer"]}),
                theme_json=json.dumps(sanitized_theme)
            )
        else:
            current_config.theme_json = json.dumps(sanitized_theme)
            current_config.updated_at = datetime.utcnow()

        db.add(current_config)
        db.commit()

        return {
            "success": True,
            "theme": sanitized_theme
        }

    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=f"Validación o límites fallidos: {val_err}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Template Studio: {str(e)}")

@router.get("/credits")
async def get_tenant_credits(
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant)
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")
    return {
        "success": True,
        "ai_tier": tenant.ai_tier,
        "ai_credits": tenant.ai_credits
    }

class CreditPurchaseRequest(BaseModel):
    amount: int = 100
    payment_reference: str  # external_id de un PlatformPayment completado


@router.post("/credits/buy")
async def buy_tenant_credits(
    req: CreditPurchaseRequest,
    db: Session = Depends(get_session),
    current_user: User = Depends(require_auth),
    tenant_id: int = Depends(get_current_tenant),
):
    # 1. Solo admin puede comprar créditos
    from services.settings_service import SettingsService
    SettingsService.ensure_admin(current_user)

    # 2. Verificar pago real completado y no reutilizado
    from database.models import PlatformPayment
    payment = db.exec(
        select(PlatformPayment).where(
            PlatformPayment.tenant_id == tenant_id,
            PlatformPayment.external_id == req.payment_reference,
            PlatformPayment.status == "completed",
            PlatformPayment.payment_type == "credit_purchase",
        )
    ).first()

    if not payment:
        raise HTTPException(
            status_code=402,
            detail="Referencia de pago inválida, no completada o no encontrada.",
        )

    # 3. Idempotencia: verificar que no se acreditaron créditos ya con este pago
    meta = json.loads(payment.metadata_json or "{}")
    if meta.get("credits_applied"):
        raise HTTPException(
            status_code=409,
            detail="Los créditos de este pago ya fueron acreditados.",
        )

    # 4. Acreditar créditos
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")

    tenant.ai_credits += req.amount
    meta["credits_applied"] = True
    meta["credits_amount"] = req.amount
    payment.metadata_json = json.dumps(meta)
    db.add(tenant)
    db.add(payment)
    db.commit()

    logger.info(
        "Credits purchased: tenant_id=%s amount=%s payment=%s",
        tenant_id, req.amount, req.payment_reference,
    )

    return {
        "success": True,
        "message": f"Se agregaron {req.amount} créditos con éxito.",
        "ai_credits": tenant.ai_credits,
    }

