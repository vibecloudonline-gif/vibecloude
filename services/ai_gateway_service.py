"""services/ai_gateway_service.py — Gateway de IA multi-proveedor (Fase 5,
sección 7 del roadmap).

Cascada de generación de contenido web (Landing/Ecommerce): Claude
(primario) → Gemini (fallback) → Qwen (tercer fallback). Cascada de chat de
AlexIO (Gemini → Qwen) vive en services/ai_brain_service.py, que importa
`ai_gateway_service` para el segundo salto. También implementa el cliente de
Qwen (DashScope) para la recomendación predictiva de productos del ecommerce
(actualización 2026-08-11).

Claude usa el SDK oficial de Anthropic (`anthropic`), como corresponde a
código Python que llama a la API de Claude. Gemini y Qwen no tienen SDK
propio en este proyecto -- siguen llamándose por HTTP directo (httpx), igual
que ya hacía el resto del código antes de esta fase.

ADVERTENCIA: sin ANTHROPIC_API_KEY ni QWEN_API_KEY (DashScope) reales
disponibles en este entorno. Construido contra las APIs públicas
documentadas, no probado contra los proveedores reales -- mismo patrón que
se usó con NameSilo/GoDaddy. Si Claude no está configurado, la cascada cae a
Gemini; si ninguno de los tres está disponible, se rechaza con un mensaje
claro (nunca se rompe el endpoint). La recomendación de productos, en
particular, cae a una heurística simple (misma categoría) si Qwen no está
disponible.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import anthropic
import httpx
from sqlalchemy import func
from sqlmodel import Session, select

from database.models import Product, Sale, SaleItem

logger = logging.getLogger("ai_gateway")

QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# Modelo por defecto para generación de contenido -- ver la skill de
# referencia de la API de Claude: usar claude-opus-5 salvo pedido explícito
# de otro modelo.
ANTHROPIC_MODEL = "claude-opus-5"


class AIGatewayError(Exception):
    pass


class QwenClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-plus"):
        self.api_key = api_key or os.getenv("QWEN_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise AIGatewayError("QWEN_API_KEY no configurada")

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.post(QWEN_API_URL, json=payload, headers=headers, timeout=20.0)
            if response.status_code != 200:
                raise AIGatewayError(f"Qwen API error {response.status_code}: {response.text}")
            data = response.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as exc:
                raise AIGatewayError(f"Respuesta inesperada de Qwen: {data}") from exc


def _build_anthropic_image_block(reference_image_path: str) -> dict:
    mime_type, _ = mimetypes.guess_type(reference_image_path)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"
    with open(reference_image_path, "rb") as f:
        encoded = base64.standard_b64encode(f.read()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": encoded}}


class AnthropicClient:
    """Cliente de Claude vía el SDK oficial de Anthropic (no HTTP directo)."""

    def __init__(self, api_key: Optional[str] = None, model: str = ANTHROPIC_MODEL):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise AIGatewayError("ANTHROPIC_API_KEY no configurada")
        self._client = anthropic.AsyncAnthropic(api_key=self.api_key)

    async def generate(
        self, system_prompt: str, user_prompt: str, reference_image_path: Optional[str] = None
    ) -> str:
        content_blocks: list = []
        if reference_image_path:
            content_blocks.append(_build_anthropic_image_block(reference_image_path))
        content_blocks.append({"type": "text", "text": user_prompt})

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": content_blocks}],
            )
        except anthropic.APIError as exc:
            raise AIGatewayError(f"Claude API error: {exc}") from exc

        if response.stop_reason == "refusal":
            raise AIGatewayError("Claude rechazó la solicitud (stop_reason=refusal)")

        text_parts = [block.text for block in response.content if block.type == "text"]
        if not text_parts:
            raise AIGatewayError("Claude no devolvió contenido de texto")
        return "".join(text_parts)


class AIGatewayService:
    """
    Recomendación predictiva de productos.

    Regla 1.1 aplicada a esta feature: el set de candidatos SIEMPRE se arma
    filtrado por tenant_id antes de mandarle nada al modelo, y la respuesta
    del modelo se vuelve a filtrar contra ese mismo set de IDs antes de
    devolverla -- aunque Qwen "alucine" o intente devolver un ID que no
    estaba en la lista, nunca puede escaparse del catálogo del tenant,
    porque el filtro de salida es estructural (whitelist), no depende de
    que el modelo se porte bien.
    """

    MAX_CANDIDATES = 40
    MAX_RECOMMENDATIONS = 8

    @staticmethod
    def _candidate_products(session: Session, tenant_id: int, exclude_ids: list[int]) -> list[Product]:
        query = select(Product).where(Product.tenant_id == tenant_id, Product.is_deleted == False)
        if exclude_ids:
            query = query.where(Product.id.not_in(exclude_ids))
        return session.exec(query.limit(AIGatewayService.MAX_CANDIDATES)).all()

    @classmethod
    async def recommend_products(
        cls,
        session: Session,
        tenant_id: int,
        seed_product_ids: list[int],
        limit: int = 4,
    ) -> list[Product]:
        """
        seed_product_ids: el producto que se está viendo, o los IDs del
        carrito -- se usan solo para elegir productos del MISMO tenant (ya
        validado por el caller vía get_public_tenant), nunca se le manda
        tenant_id al modelo.
        """
        candidates = cls._candidate_products(session, tenant_id, exclude_ids=seed_product_ids)
        if not candidates:
            return []

        seed_products = (
            session.exec(
                select(Product).where(Product.id.in_(seed_product_ids), Product.tenant_id == tenant_id)
            ).all()
            if seed_product_ids
            else []
        )

        try:
            recommended_ids = await cls._recommend_with_qwen(seed_products, candidates)
        except AIGatewayError as exc:
            logger.info(f"Recomendación con Qwen no disponible, usando heurística: {exc}")
            recommended_ids = cls._recommend_heuristic(seed_products, candidates)

        candidates_by_id = {p.id: p for p in candidates}
        # Filtro de salida (whitelist): solo IDs que YA estaban en el set de
        # candidatos de este tenant sobreviven -- nunca se confía en el
        # output del modelo por si solo.
        result = [candidates_by_id[pid] for pid in recommended_ids if pid in candidates_by_id]
        if not result:
            fallback_ids = cls._recommend_heuristic(seed_products, candidates)
            result = [candidates_by_id[pid] for pid in fallback_ids if pid in candidates_by_id]
        return result[:limit]

    @staticmethod
    async def _recommend_with_qwen(seed_products: list[Product], candidates: list[Product]) -> list[int]:
        client = QwenClient()  # levanta AIGatewayError si no hay QWEN_API_KEY

        seed_desc = "\n".join(
            f"- {p.name} (categoría: {p.category or 'sin categoría'})" for p in seed_products
        ) or "Ninguno especificado"
        candidates_desc = "\n".join(
            f"{p.id}: {p.name} (categoría: {p.category or 'sin categoría'})" for p in candidates
        )

        system_prompt = (
            "Sos un motor de recomendación de productos para un ecommerce. "
            "Dado un producto o carrito de referencia y una lista de productos candidatos "
            "(con su ID numérico), devolvé SOLO un array JSON de hasta 8 IDs numéricos de los "
            "candidatos más relevantes para recomendar, ordenados de más a menos relevante. "
            "No inventes IDs que no estén en la lista de candidatos. No agregues texto fuera del JSON."
        )
        user_prompt = f"Producto(s)/carrito de referencia:\n{seed_desc}\n\nCandidatos:\n{candidates_desc}"

        raw = (await client.chat(system_prompt, user_prompt)).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIGatewayError(f"Qwen no devolvió JSON válido: {raw[:200]}") from exc

        if not isinstance(parsed, list):
            raise AIGatewayError(f"Qwen no devolvió una lista: {raw[:200]}")

        ids: list[int] = []
        for item in parsed:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return ids

    @staticmethod
    def _recommend_heuristic(seed_products: list[Product], candidates: list[Product]) -> list[int]:
        """Sin Qwen (no configurado o error): misma categoría que el seed; si no hay match, los primeros candidatos."""
        seed_categories = {p.category for p in seed_products if p.category}
        if seed_categories:
            same_category = [p.id for p in candidates if p.category in seed_categories]
            if same_category:
                return same_category
        return [p.id for p in candidates]

    # ------------------------------------------------------------------
    # Cascada de generación de contenido web: Claude -> Gemini -> Qwen
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_landing_content_cascade(
        prompt: str, reference_image_path: Optional[str] = None
    ):
        """
        Cascada de Fase 5: Claude (primario) -> Gemini (fallback) -> Qwen
        (tercer fallback) para generación de contenido de landing/ecommerce.
        Cada intento se valida contra el MISMO schema estricto
        (LandingPageContent, Regla 1.2) sin importar qué proveedor respondió
        -- la sanitización nunca depende del proveedor. Devuelve
        (content, provider_used).
        """
        from services.landing_service import (
            SYSTEM_INSTRUCTION,
            LandingGenerationError,
            _validate,
        )
        from services.landing_service import generate_landing_content as _generate_with_gemini

        errors: list[str] = []

        try:
            client = AnthropicClient()
            raw = await client.generate(SYSTEM_INSTRUCTION, prompt, reference_image_path)
            return _validate(raw), "claude"
        except Exception as exc:  # noqa: BLE001 - se agrega al log de errores del intento, no se propaga
            errors.append(f"Claude: {exc}")

        try:
            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                raise AIGatewayError("GEMINI_API_KEY no configurada")
            content = await _generate_with_gemini(prompt, api_key, reference_image_path)
            return content, "gemini"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Gemini: {exc}")

        try:
            client = QwenClient()  # sin soporte de imagen todavía -- fallback de texto
            raw = await client.chat(SYSTEM_INSTRUCTION, prompt)
            return _validate(raw), "qwen"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Qwen: {exc}")

        raise LandingGenerationError(
            "Ningún proveedor de IA disponible para generar la landing. " + " | ".join(errors)
        )

    # ------------------------------------------------------------------
    # Fallback de chat de AlexIO: Gemini -> Qwen (llamado desde
    # services/ai_brain_service.py cuando Gemini no está disponible)
    # ------------------------------------------------------------------

    @staticmethod
    async def chat_fallback_qwen(
        history: list, new_message: str, system_instruction: str
    ) -> Optional[str]:
        """
        Fallback degradado: sin function-calling (Qwen no tiene las tools
        de AIBrainService wireadas todavía) y sin descuento de créditos de
        IA (el modelo de costos actual solo cubre Gemini) -- mejor una
        respuesta de texto que un error, pero es intencionalmente un
        camino de emergencia, no un reemplazo de Gemini. Devuelve None si
        Qwen tampoco está disponible, para que el caller decida si
        re-lanzar el error original de Gemini.
        """
        try:
            client = QwenClient()
        except AIGatewayError:
            return None

        history_text = "\n".join(
            f"{'Usuario' if h.get('role') == 'user' else 'Asistente'}: {h.get('parts', [{}])[0].get('text', '')}"
            for h in history
        )
        user_prompt = f"{history_text}\nUsuario: {new_message}" if history_text else new_message

        try:
            return await client.chat(system_instruction, user_prompt)
        except AIGatewayError:
            return None

    # ------------------------------------------------------------------
    # Predicción de viabilidad de producto -- módulo disponible para
    # cualquier tenant (con o sin historial de ventas propio). Usa Qwen
    # con el mismo patrón que recommend_products: prompt + JSON, filtrado
    # siempre por tenant_id (Regla 1.1).
    # ------------------------------------------------------------------

    @staticmethod
    def _category_sales_context(session: Session, tenant_id: int, category: Optional[str]) -> str:
        if not category:
            return "El producto no tiene categoría asignada."

        cutoff = datetime.utcnow() - timedelta(days=90)
        row = session.exec(
            select(
                func.count(func.distinct(SaleItem.product_id)),
                func.coalesce(func.sum(SaleItem.quantity), 0),
                func.coalesce(func.avg(SaleItem.unit_price), 0),
            )
            .join(Sale, SaleItem.sale_id == Sale.id)
            .join(Product, SaleItem.product_id == Product.id)
            .where(
                Product.tenant_id == tenant_id,
                Product.category == category,
                Sale.tenant_id == tenant_id,
                Sale.timestamp >= cutoff,
            )
        ).first()

        distinct_products, total_units, avg_price = row or (0, 0, 0)
        if not distinct_products:
            return (
                f"Sin ventas registradas en la categoría '{category}' en los últimos 90 días "
                "-- este tenant todavía no tiene historial propio en esta categoría."
            )
        return (
            f"En los últimos 90 días, este negocio vendió {int(total_units)} unidades de "
            f"{distinct_products} producto(s) distinto(s) de la categoría '{category}', "
            f"a un precio promedio de ${float(avg_price):.2f}."
        )

    @classmethod
    async def predict_product_success(
        cls,
        session: Session,
        tenant_id: int,
        name: str,
        category: Optional[str],
        price: Decimal,
        description: Optional[str] = None,
    ) -> dict:
        """
        Devuelve {available: bool, ...}. Cuando Qwen no está configurado o
        la respuesta no se puede interpretar, available=False con un
        mensaje claro -- a propósito no hay heurística de respaldo acá
        (a diferencia de recommend_products): "predecir éxito" sin un
        modelo detrás no tiene una regla objetiva razonable, así que es
        más honesto decir "no disponible" que devolver un score inventado.
        """
        category_context = cls._category_sales_context(session, tenant_id, category)

        system_prompt = (
            "Sos un analista de retail que evalúa la viabilidad comercial de productos "
            "para pequeños y medianos negocios. Te dan un producto nuevo o en evaluación "
            "y el rendimiento histórico (si existe) de esa categoría en ESTE negocio puntual. "
            "Devolvé SOLO un objeto JSON con las claves: "
            '"score" (entero de 0 a 100, qué tan probable es que el producto funcione bien), '
            '"veredicto" (uno de: "alto potencial", "potencial moderado", "riesgo alto"), '
            '"razones" (array de 2 a 4 strings breves), '
            '"recomendacion" (un string corto y accionable). '
            "Si no hay historial de ventas de la categoría, decilo explícitamente en las "
            "razones -- nunca inventes cifras de ventas que no te dieron. "
            "No agregues texto fuera del JSON."
        )
        user_prompt = (
            f"Producto: {name}\n"
            f"Categoría: {category or 'sin categoría'}\n"
            f"Precio: ${price}\n"
            f"Descripción: {description or 'sin descripción'}\n\n"
            f"Contexto de ventas del negocio: {category_context}"
        )

        try:
            client = QwenClient()
            raw = (await client.chat(system_prompt, user_prompt)).strip()
        except AIGatewayError as exc:
            logger.info(f"Predicción de viabilidad no disponible: {exc}")
            return {
                "available": False,
                "message": "La predicción con IA no está disponible en este momento (QWEN_API_KEY no configurada).",
            }

        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            parsed = json.loads(raw)
            score = max(0, min(100, int(parsed["score"])))
            veredicto = str(parsed["veredicto"])
            razones = [str(r) for r in parsed.get("razones", [])][:4]
            recomendacion = str(parsed.get("recomendacion", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning(f"Qwen devolvió una respuesta inesperada para predicción de producto: {raw[:200]}")
            return {
                "available": False,
                "message": "No se pudo interpretar la respuesta de la IA. Probá de nuevo en un momento.",
            }

        return {
            "available": True,
            "score": score,
            "veredicto": veredicto,
            "razones": razones,
            "recomendacion": recomendacion,
            "category_context": category_context,
        }


ai_gateway_service = AIGatewayService()
