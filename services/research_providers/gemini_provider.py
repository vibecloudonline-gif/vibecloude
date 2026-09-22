from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Optional

from services.gemini_service import GeminiService
from services.research_providers.base import (
    DemandEstimate,
    ProductDataProvider,
    ProductListing,
)

logger = logging.getLogger("research.gemini")


class GeminiMarketProvider(ProductDataProvider):
    """
    Proveedor de Inteligencia de Mercado potenciado por Google Gemini AI.
    Analiza el panorama real de mercado, productos comparables de la competencia,
    precios de referencia (Amazon, MercadoLibre, AliExpress) y estima la demanda real.
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search_products(
        self, query: str, reference_url: Optional[str] = None
    ) -> list[ProductListing]:
        prompt = f"""
        Actúa como un analista de mercado e-commerce experto en retail y marketplaces (Amazon, MercadoLibre, AliExpress, Walmart).
        Analiza el siguiente producto, servicio o nicho:
        Consulta: "{query}"
        {f'URL o referencia del producto: "{reference_url}"' if reference_url else ''}

        Genera entre 4 y 6 listados comparables reales o de referencia de mercado con precios competitivos actuales en USD, fuentes de mercado representativas, calificaciones realistas (de 3.8 a 4.9) y cantidad de reseñas estimadas.

        Debes responder EXCLUSIVAMENTE un JSON con este formato exacto:
        [
          {{
            "source": "Amazon",
            "title": "Nombre comercial y modelo representativo del competidor",
            "price": 29.99,
            "currency": "USD",
            "rating": 4.5,
            "review_count": 340,
            "url": "https://www.amazon.com/s?k=..."
          }}
        ]
        No agregues markdown ni texto adicional fuera del JSON.
        """

        system_instruction = (
            "Eres un especialista senior en inteligencia competitiva e investigación "
            "de mercado de comercio electrónico."
        )

        try:
            raw_text = await GeminiService._call_gemini_api(
                prompt, system_instruction, self.api_key
            )
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()

            items = json.loads(cleaned)
            if isinstance(items, dict):
                items = items.get("listings", items.get("products", []))

            listings: list[ProductListing] = []
            for item in items:
                price_val = None
                if item.get("price") is not None:
                    try:
                        price_val = Decimal(str(round(float(item["price"]), 2)))
                    except Exception:
                        price_val = None

                rating_val = None
                if item.get("rating") is not None:
                    try:
                        rating_val = Decimal(str(round(float(item["rating"]), 1)))
                    except Exception:
                        rating_val = None

                listings.append(
                    ProductListing(
                        source=str(item.get("source", "Mercado")),
                        title=str(item.get("title", query)),
                        price=price_val,
                        currency=str(item.get("currency", "USD")),
                        url=item.get("url"),
                        rating=rating_val,
                        review_count=int(item.get("review_count", 100)),
                        is_demo=False,
                    )
                )

            if listings:
                return listings
        except Exception as exc:
            logger.warning(
                f"Error generando listados de mercado con Gemini ({exc}). Usando fallback offline."
            )

        from services.research_providers.mock_provider import MockProvider

        return await MockProvider().search_products(query, reference_url)

    async def estimate_demand(self, query: str) -> DemandEstimate:
        prompt = f"""
        Actúa como un experto en análisis cuantitativo de demanda de e-commerce.
        Evalúa la demanda de mercado mensual para el producto o nicho: "{query}".

        Calcula el volumen mensual estimado de búsquedas/ventas, el nivel de confianza y un análisis conciso de la oportunidad de mercado.

        Debes responder EXCLUSIVAMENTE un JSON válido con esta estructura:
        {{
          "confidence_level": "alto", // opciones: "alto", "medio", "bajo"
          "estimated_monthly_volume": 3500, // número entero estimado
          "source_description": "Inteligencia de Mercado VibeCloud AI (Benchmarks Amazon / MercadoLibre)",
          "notes": "Análisis de oportunidad: descripción concisa de demanda, estacionalidad y competencia."
        }}
        No agregues markdown ni texto adicional fuera del JSON.
        """

        system_instruction = (
            "Eres un analista de datos de mercado y demanda para retail y comercio digital."
        )

        try:
            raw_text = await GeminiService._call_gemini_api(
                prompt, system_instruction, self.api_key
            )
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            conf = data.get("confidence_level", "medio")
            if conf not in ("alto", "medio", "bajo", "no_disponible"):
                conf = "medio"

            return DemandEstimate(
                confidence_level=conf,
                estimated_monthly_volume=int(
                    data.get("estimated_monthly_volume", 1200)
                ),
                source_description=data.get(
                    "source_description",
                    "Inteligencia de Mercado VibeCloud AI (Benchmarks Amazon / MercadoLibre)",
                ),
                notes=data.get(
                    "notes", "Análisis de mercado y demanda generado por IA."
                ),
            )
        except Exception as exc:
            logger.warning(
                f"Error estimando demanda con Gemini ({exc}). Usando fallback offline."
            )

        from services.research_providers.mock_provider import MockProvider

        return await MockProvider().estimate_demand(query)
