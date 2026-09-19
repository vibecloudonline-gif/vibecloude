"""services/ai_gateway_service.py — Gateway de IA multi-proveedor (Fase 5,
sección 7 del roadmap).

FASE 1 UPDATE: All AI calls now route through services.ai.gateway (AI Gateway).
AnthropicClient and QwenClient kept as thin wrappers for backward compat
(recommend_products, predict_product_success), but generate_landing_content_cascade
and chat_fallback_qwen now use the unified Gateway.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from database.models import Product, Sale, SaleItem

logger = logging.getLogger("ai_gateway")


class AIGatewayError(Exception):
    pass


class AnthropicClient:
    """Cliente de Claude vía Gateway (wrapper retrocompatible)."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-opus-5"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise AIGatewayError("ANTHROPIC_API_KEY no configurada")

    async def generate(
        self, system_prompt: str, user_prompt: str, reference_image_path: Optional[str] = None
    ) -> str:
        from services.ai.contracts import AIMessage, AIRequest
        from services.ai.gateway import ai_gateway

        request = AIRequest(
            task="landing_generation",
            messages=[AIMessage(role="user", content=user_prompt)],
            system_prompt=system_prompt,
            provider="claude",
            model=self.model,
            metadata={"reference_image_path": reference_image_path} if reference_image_path else {},
        )
        response = await ai_gateway.generate(request)
        return response.content


class QwenClient:
    """Cliente de Qwen vía Gateway (wrapper retrocompatible)."""

    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-plus"):
        self.api_key = api_key or os.getenv("QWEN_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise AIGatewayError("QWEN_API_KEY no configurada")

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        from services.ai.contracts import AIMessage, AIRequest
        from services.ai.gateway import ai_gateway

        request = AIRequest(
            task="qwen_chat",
            messages=[AIMessage(role="user", content=user_prompt)],
            system_prompt=system_prompt,
            provider="qwen",
            model=self.model,
        )
        response = await ai_gateway.generate(request)
        return response.content


class AIGatewayService:
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
        result = [candidates_by_id[pid] for pid in recommended_ids if pid in candidates_by_id]
        if not result:
            fallback_ids = cls._recommend_heuristic(seed_products, candidates)
            result = [candidates_by_id[pid] for pid in fallback_ids if pid in candidates_by_id]
        return result[:limit]

    @staticmethod
    async def _recommend_with_qwen(seed_products: list[Product], candidates: list[Product]) -> list[int]:
        from services.ai.contracts import AIMessage, AIRequest
        from services.ai.gateway import ai_gateway

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

        request = AIRequest(
            task="product_recommendation",
            messages=[AIMessage(role="user", content=user_prompt)],
            system_prompt=system_prompt,
            provider="qwen",
            model="qwen-plus",
            timeout=20.0,
        )

        try:
            response = await ai_gateway.generate(request)
        except Exception as exc:
            if os.getenv("GEMINI_API_KEY"):
                try:
                    request.provider = "gemini"
                    request.model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
                    response = await ai_gateway.generate(request)
                except Exception:
                    raise AIGatewayError(str(exc)) from exc
            else:
                raise AIGatewayError(str(exc)) from exc

        raw = response.content.strip()
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
        seed_categories = {p.category for p in seed_products if p.category}
        if seed_categories:
            same_category = [p.id for p in candidates if p.category in seed_categories]
            if same_category:
                return same_category
        return [p.id for p in candidates]

    # ------------------------------------------------------------------
    # Cascada de generación de contenido web: Claude -> Gemini -> Qwen
    # Now routes through AI Gateway adapters
    # ------------------------------------------------------------------

    @staticmethod
    async def generate_landing_content_cascade(
        prompt: str, reference_image_path: Optional[str] = None
    ):
        from services.ai.contracts import AIMessage, AIRequest
        from services.ai.gateway import ai_gateway
        from services.landing_service import (
            SYSTEM_INSTRUCTION,
            LandingGenerationError,
            _validate,
        )
        from services.landing_service import generate_landing_content as _generate_with_gemini

        errors: list[str] = []

        # --- Claude (primary) via Gateway ---
        claude_adapter = ai_gateway.get_adapter("claude")
        if claude_adapter.validate_config():
            try:
                request = AIRequest(
                    task="landing_generation",
                    messages=[AIMessage(role="user", content=prompt)],
                    system_prompt=SYSTEM_INSTRUCTION,
                    provider="claude",
                    max_tokens=2048,
                    metadata={"reference_image_path": reference_image_path} if reference_image_path else {},
                )
                response = await ai_gateway.generate(request)
                return _validate(response.content), "claude"
            except Exception as exc:
                errors.append(f"Claude: {exc}")
        else:
            errors.append("Claude: no configurado o sin crédito disponible")

        # --- Gemini (fallback) via Gateway ---
        try:
            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                raise AIGatewayError("GEMINI_API_KEY no configurada")
            content = await _generate_with_gemini(prompt, api_key, reference_image_path)
            return content, "gemini"
        except Exception as exc:
            errors.append(f"Gemini: {exc}")

        # --- Qwen (third fallback) via Gateway ---
        qwen_adapter = ai_gateway.get_adapter("qwen")
        if qwen_adapter.validate_config():
            try:
                request = AIRequest(
                    task="landing_generation",
                    messages=[AIMessage(role="user", content=prompt)],
                    system_prompt=SYSTEM_INSTRUCTION,
                    provider="qwen",
                    model="qwen-plus",
                    timeout=20.0,
                )
                response = await ai_gateway.generate(request)
                return _validate(response.content), "qwen"
            except Exception as exc:
                errors.append(f"Qwen: {exc}")
        else:
            errors.append("Qwen: no configurado o sin crédito disponible")

        raise LandingGenerationError(
            "Ningún proveedor de IA disponible para generar la landing. " + " | ".join(errors)
        )

    # ------------------------------------------------------------------
    # Fallback de chat de AlexIO: Gemini -> Qwen
    # Now routes through AI Gateway
    # ------------------------------------------------------------------

    @staticmethod
    async def chat_fallback_qwen(
        history: list, new_message: str, system_instruction: str
    ) -> Optional[str]:
        from services.ai.contracts import AIError, AIMessage, AIRequest
        from services.ai.gateway import ai_gateway

        qwen_adapter = ai_gateway.get_adapter("qwen")
        if not qwen_adapter.validate_config():
            return None

        history_text = "\n".join(
            f"{'Usuario' if h.get('role') == 'user' else 'Asistente'}: {h.get('parts', [{}])[0].get('text', '')}"
            for h in history
        )
        user_prompt = f"{history_text}\nUsuario: {new_message}" if history_text else new_message

        request = AIRequest(
            task="alex_chat_fallback",
            messages=[AIMessage(role="user", content=user_prompt)],
            system_prompt=system_instruction,
            provider="qwen",
            model="qwen-plus",
            timeout=20.0,
        )

        try:
            response = await ai_gateway.generate(request)
            return response.content
        except AIError:
            return None

    # ------------------------------------------------------------------
    # Predicción de viabilidad de producto — uses Qwen via Gateway
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

    _VIABILITY_PERSONAS = [
        {
            "id": "precio",
            "label": "Comprador sensible al precio",
            "role": (
                "Te importa sobre todo el precio: comparás con alternativas similares y "
                "dudás si algo te parece caro para lo que es."
            ),
        },
        {
            "id": "calidad",
            "label": "Comprador que prioriza calidad y marca",
            "role": (
                "Confiás en productos con buena reputación y descripciones que transmiten "
                "calidad; desconfiás de lo genérico o mal descripto."
            ),
        },
        {
            "id": "impulsivo",
            "label": "Comprador impulsivo / de tendencia",
            "role": (
                "Comprás por impulso cosas que se ven atractivas o de moda ahora mismo; "
                "te aburren los productos genéricos de siempre."
            ),
        },
        {
            "id": "esceptico",
            "label": "Comprador escéptico / que compara",
            "role": (
                "Investigás bastante antes de comprar, buscás razones para NO comprar, y "
                "sos el más difícil de convencer del grupo."
            ),
        },
    ]

    @staticmethod
    def _veredicto_from_score(score: float) -> str:
        if score >= 70:
            return "alto potencial"
        if score >= 40:
            return "potencial moderado"
        return "riesgo alto"

    @staticmethod
    async def _run_viability_agent(
        persona: dict,
        category_context: str,
        name: str,
        category: Optional[str],
        price: Decimal,
        description: Optional[str],
    ) -> Optional[dict]:
        from services.ai.contracts import AIError, AIMessage, AIRequest
        from services.ai.gateway import ai_gateway

        system_prompt = (
            f"Sos un comprador de retail con este perfil: {persona['role']} "
            "Te muestran un producto y el rendimiento histórico (si existe) de esa "
            "categoría en el negocio que lo vende. Devolvé SOLO un objeto JSON con las "
            'claves "score" (entero de 0 a 100, qué tan probable es que compres este '
            'producto, o que le vaya bien a alguien con tu perfil) y "razon" (un string '
            "breve, 1-2 oraciones, tu razón desde tu perspectiva de comprador). Si no hay "
            "historial de ventas de la categoría, no inventes cifras. No agregues texto "
            "fuera del JSON."
        )
        user_prompt = (
            f"Producto: {name}\n"
            f"Categoría: {category or 'sin categoría'}\n"
            f"Precio: ${price}\n"
            f"Descripción: {description or 'sin descripción'}\n\n"
            f"Contexto de ventas del negocio: {category_context}"
        )

        raw = None
        try:
            client = QwenClient()
            raw = (await client.chat(system_prompt, user_prompt)).strip()
        except Exception:
            if os.getenv("GEMINI_API_KEY"):
                try:
                    request = AIRequest(
                        task="product_viability",
                        messages=[AIMessage(role="user", content=user_prompt)],
                        system_prompt=system_prompt,
                        provider="gemini",
                        model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
                        timeout=20.0,
                    )
                    response = await ai_gateway.generate(request)
                    raw = response.content.strip()
                except Exception:
                    return None
            else:
                return None

        if not raw:
            return None

        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            parsed = json.loads(raw)
            score = max(0, min(100, int(parsed["score"])))
            razon = str(parsed.get("razon", "")).strip()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning(f"Qwen devolvió una respuesta inesperada para el perfil '{persona['id']}': {raw[:200]}")
            return None

        return {"id": persona["id"], "label": persona["label"], "score": score, "razon": razon}

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
        if not os.getenv("QWEN_API_KEY", ""):
            return {
                "available": False,
                "message": "La predicción con IA no está disponible en este momento (QWEN_API_KEY no configurada).",
            }

        category_context = cls._category_sales_context(session, tenant_id, category)

        results = await asyncio.gather(*[
            cls._run_viability_agent(persona, category_context, name, category, price, description)
            for persona in cls._VIABILITY_PERSONAS
        ])
        successful = [r for r in results if r is not None]

        if not successful:
            return {
                "available": False,
                "message": "No se pudo interpretar la respuesta de la IA. Probá de nuevo en un momento.",
            }

        for r in successful:
            r["veredicto"] = cls._veredicto_from_score(r["score"])

        avg_score = round(sum(r["score"] for r in successful) / len(successful))
        veredicto = cls._veredicto_from_score(avg_score)
        alto_count = sum(1 for r in successful if r["veredicto"] == "alto potencial")

        return {
            "available": True,
            "score": avg_score,
            "veredicto": veredicto,
            "agentes_consultados": len(successful),
            "agentes_alto_potencial": alto_count,
            "perfiles": successful,
            "category_context": category_context,
        }


ai_gateway_service = AIGatewayService()
