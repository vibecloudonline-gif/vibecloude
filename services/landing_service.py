"""Landing Pages con IA (Fase 3 del roadmap, "AI Template Studio").

Regla 1.2 de CLAUDE.md, aplicada acá de la forma más estricta posible: Gemini
NUNCA genera HTML ni CSS crudo. Genera únicamente contenido de texto plano y
la elección de un color/fuente de una lista cerrada -- el HTML lo arma
siempre nuestro propio template (templates/storefront_landing.html). Así no
existe ningún canal por el que el modelo pueda inyectar <script>, url(),
expression() ni nada que "resuelva a ejecución", porque nunca se le da la
posibilidad de escribir markup en absoluto.

Si la respuesta de Gemini no valida contra LandingPageContent, se descarta y
se reintenta una vez; si sigue sin validar, se rechaza (nunca se persiste
"lo que vino").
"""
from __future__ import annotations

import json
import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from database.models import LandingPage, Tenant

logger = logging.getLogger("landing_service")

# Modelo vigente según CLAUDE.md sección 3 (gemini-2.0-flash fue discontinuado
# el 2026-06-01) -- usar el de nivel 2 (equilibrado), no el 1.
GEMINI_MODEL = "gemini-3.5-flash"

# Únicas fuentes permitidas -- Gemini elige un nombre de esta lista, nunca
# escribe la declaración @font-face ni un <link> él mismo.
ALLOWED_FONTS = (
    "Inter", "Outfit", "Poppins", "Montserrat", "Roboto", "Nunito", "Lato", "Playfair Display",
)

_HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"
_NO_MARKUP = re.compile(r"[<>]")


def _no_markup(value: str, field_name: str) -> str:
    if _NO_MARKUP.search(value):
        raise ValueError(f"{field_name} no puede contener '<' ni '>' (sin HTML/markup permitido)")
    return value.strip()


class LandingSection(BaseModel):
    title: str = Field(max_length=60)
    body: str = Field(max_length=500)

    @field_validator("title")
    @classmethod
    def _title_no_markup(cls, v):
        return _no_markup(v, "title")

    @field_validator("body")
    @classmethod
    def _body_no_markup(cls, v):
        return _no_markup(v, "body")


class LandingTheme(BaseModel):
    primary_color: str = Field(pattern=_HEX_COLOR)
    secondary_color: str = Field(pattern=_HEX_COLOR)
    font_family: Literal[ALLOWED_FONTS]  # type: ignore[valid-type]


class LandingPageContent(BaseModel):
    hero_title: str = Field(max_length=80)
    hero_subtitle: str = Field(max_length=220)
    cta_text: str = Field(max_length=40)
    sections: list[LandingSection] = Field(max_length=6)
    theme: LandingTheme

    @field_validator("hero_title")
    @classmethod
    def _hero_title_no_markup(cls, v):
        return _no_markup(v, "hero_title")

    @field_validator("hero_subtitle")
    @classmethod
    def _hero_subtitle_no_markup(cls, v):
        return _no_markup(v, "hero_subtitle")

    @field_validator("cta_text")
    @classmethod
    def _cta_text_no_markup(cls, v):
        return _no_markup(v, "cta_text")


SYSTEM_INSTRUCTION = f"""
Eres un redactor y diseñador de landing pages para pequeños comercios.
El usuario te va a pegar una idea o descripción de su negocio. Tu trabajo es
generar CONTENIDO (texto) y ELEGIR estilo de una lista cerrada -- nunca HTML,
nunca CSS, nunca código de ningún tipo.

Generá algo INSPIRADO en lo que describe el usuario, con tus propias
palabras -- si menciona que quiere "una página como tal marca/sitio", no
copies textos ni diseños de esa marca/sitio, interpretalo y creá algo
original en ese espíritu.

Responde EXCLUSIVAMENTE con un JSON con esta forma exacta, sin texto
adicional antes ni después:
{{
  "hero_title": "string, máximo 80 caracteres",
  "hero_subtitle": "string, máximo 220 caracteres",
  "cta_text": "string corto para un botón, máximo 40 caracteres",
  "sections": [
    {{"title": "string, máximo 60 caracteres", "body": "string, máximo 500 caracteres"}}
  ],
  "theme": {{
    "primary_color": "#RRGGBB",
    "secondary_color": "#RRGGBB",
    "font_family": "una de: {', '.join(ALLOWED_FONTS)}"
  }}
}}
Entre 2 y 4 elementos en "sections". Ningún campo de texto puede contener los
caracteres '<' o '>' bajo ninguna circunstancia.
"""


class LandingGenerationError(ValueError):
    pass


async def _call_gemini(prompt: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "generationConfig": {"responseMimeType": "application/json"},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        if response.status_code != 200:
            logger.error(f"Gemini API error: {response.status_code} {response.text}")
            raise LandingGenerationError(f"Error de Gemini API: {response.status_code}")
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LandingGenerationError("Gemini no devolvió candidatos")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise LandingGenerationError("Gemini no devolvió contenido")
        return parts[0].get("text", "")


def _validate(raw_text: str) -> LandingPageContent:
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LandingGenerationError(f"Respuesta de Gemini no es JSON válido: {exc}")
    return LandingPageContent.model_validate(data)


async def generate_landing_content(prompt: str, api_key: str) -> LandingPageContent:
    """Llama a Gemini y valida contra el schema estricto. Un reintento si
    la primera respuesta no valida; si el segundo intento tampoco valida,
    se descarta (nunca se persiste contenido sin validar)."""
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw_text = await _call_gemini(prompt, api_key)
            return _validate(raw_text)
        except Exception as exc:  # noqa: BLE001 - queremos capturar json/pydantic/http por igual
            last_error = exc
            logger.warning(f"Intento {attempt + 1} de generar landing falló: {exc}")
    raise LandingGenerationError(f"No se pudo generar una landing válida: {last_error}")


def save_landing(session: Session, tenant_id: int, prompt: str, content: LandingPageContent) -> LandingPage:
    from datetime import datetime, timezone

    existing = session.exec(select(LandingPage).where(LandingPage.tenant_id == tenant_id)).first()
    content_json = content.model_dump_json()
    if existing:
        existing.prompt_used = prompt
        existing.content_json = content_json
        existing.updated_at = datetime.now(timezone.utc)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    landing = LandingPage(tenant_id=tenant_id, prompt_used=prompt, content_json=content_json)
    session.add(landing)
    session.commit()
    session.refresh(landing)
    return landing


def get_landing(session: Session, tenant_id: int) -> LandingPage | None:
    return session.exec(select(LandingPage).where(LandingPage.tenant_id == tenant_id)).first()
