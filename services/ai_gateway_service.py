"""services/ai_gateway_service.py — Gateway de IA multi-proveedor.

Hoy solo implementa el cliente de Qwen (DashScope) para la feature de
recomendación predictiva de productos del ecommerce (actualización
2026-08-11, ver VIBECLOUD_ROADMAP_V2.md). La cascada completa
Claude→Gemini→Qwen para generación de contenido web sigue pendiente (Fase 5
de la sección 7 del roadmap) -- esta feature se activa independiente de esa
cascada, en el mismo servicio, para no bloquear el resto del trabajo por
falta de credenciales.

ADVERTENCIA: sin QWEN_API_KEY (DashScope) real disponible en este entorno.
Construido contra la API pública documentada de DashScope (modo compatible
OpenAI), no probado contra el proveedor real -- mismo patrón que se usó con
NameSilo/GoDaddy. Si no hay key configurada, la recomendación cae a una
heurística simple (misma categoría) en vez de romper el endpoint.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx
from sqlmodel import Session, select

from database.models import Product

logger = logging.getLogger("ai_gateway")

QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


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


ai_gateway_service = AIGatewayService()
