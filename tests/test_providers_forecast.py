"""Tests para Keepa, MeLi, cascada multi-provider y forecast traducido."""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("RATE_LIMIT_PUBLIC", "1000/minute")


# ---------------------------------------------------------------------------
# Keepa provider
# ---------------------------------------------------------------------------
class TestKeepaProvider(unittest.TestCase):
    def test_init_requires_key(self):
        from services.research_providers.keepa_provider import KeepaProvider
        from services.research_providers.base import ProviderNotConfigured

        with self.assertRaises(ProviderNotConfigured):
            KeepaProvider("")

    def test_init_sets_domain_id(self):
        from services.research_providers.keepa_provider import KeepaProvider

        p = KeepaProvider("test-key", domain="mx")
        self.assertEqual(p.domain_id, 11)

    def test_init_unknown_domain_defaults_to_us(self):
        from services.research_providers.keepa_provider import KeepaProvider

        p = KeepaProvider("test-key", domain="zz")
        self.assertEqual(p.domain_id, 1)

    def test_cents_to_dollars(self):
        from services.research_providers.keepa_provider import _cents_to_dollars

        self.assertEqual(_cents_to_dollars(2999), Decimal("29.99"))
        self.assertIsNone(_cents_to_dollars(None))
        self.assertIsNone(_cents_to_dollars(-1))
        self.assertEqual(_cents_to_dollars(0), Decimal("0.00"))

    def test_search_products_parses_keepa_response(self):
        from services.research_providers.keepa_provider import KeepaProvider

        provider = KeepaProvider("test-key")

        search_response = MagicMock()
        search_response.status_code = 200
        search_response.raise_for_status = MagicMock()
        search_response.json.return_value = {
            "asinList": ["B001TEST", "B002TEST"],
        }

        product_response = MagicMock()
        product_response.status_code = 200
        product_response.raise_for_status = MagicMock()
        product_response.json.return_value = {
            "products": [
                {
                    "title": "Wireless Headphones Pro",
                    "asin": "B001TEST",
                    "stats": {
                        "current": [2999, 3499],
                        "avg90": [2899, 3299],
                        "rating": 45,
                        "reviewCount": 1200,
                    },
                },
                {
                    "title": "Budget Earbuds",
                    "asin": "B002TEST",
                    "stats": {
                        "current": [1499],
                        "avg90": [1599],
                        "rating": 38,
                        "reviewCount": 320,
                    },
                },
            ]
        }

        call_count = 0
        async def fake_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "/search" in url:
                return search_response
            return product_response

        mock_client = AsyncMock()
        mock_client.get = fake_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("services.research_providers.keepa_provider.httpx.AsyncClient", return_value=mock_client):
            listings = asyncio.run(
                provider.search_products("wireless headphones")
            )

        self.assertEqual(len(listings), 2)
        self.assertEqual(listings[0].title, "Wireless Headphones Pro")
        self.assertEqual(listings[0].price, Decimal("29.99"))
        self.assertEqual(listings[0].source, "Amazon (Keepa)")
        self.assertFalse(listings[0].is_demo)
        self.assertEqual(listings[0].review_count, 1200)
        self.assertEqual(listings[0].rating, Decimal("4.5"))
        self.assertIn("amazon.com/dp/B001TEST", listings[0].url)

    def test_estimate_demand_uses_review_heuristic(self):
        from services.research_providers.keepa_provider import KeepaProvider

        provider = KeepaProvider("test-key")

        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.json.return_value = {"asinList": ["B001"]}

        product_resp = MagicMock()
        product_resp.raise_for_status = MagicMock()
        product_resp.json.return_value = {
            "products": [{
                "title": "Test Product",
                "asin": "B001",
                "stats": {
                    "current": [4999],
                    "avg90": [4999],
                    "rating": 42,
                    "reviewCount": 600,
                },
            }]
        }

        async def fake_get(url, **kwargs):
            if "/search" in url:
                return search_resp
            return product_resp

        mock_client = AsyncMock()
        mock_client.get = fake_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("services.research_providers.keepa_provider.httpx.AsyncClient", return_value=mock_client):
            demand = asyncio.run(
                provider.estimate_demand("test product")
            )

        self.assertEqual(demand.confidence_level, "medio")
        self.assertGreater(demand.estimated_monthly_volume, 0)
        self.assertIn("Keepa API", demand.source_description)


# ---------------------------------------------------------------------------
# MeLi provider
# ---------------------------------------------------------------------------
class TestMeliProvider(unittest.TestCase):
    def test_init_defaults_to_mla(self):
        from services.research_providers.meli_provider import MeliProvider

        p = MeliProvider()
        self.assertEqual(p.site_id, "MLA")

    def test_init_invalid_site_defaults_to_mla(self):
        from services.research_providers.meli_provider import MeliProvider

        p = MeliProvider("INVALID")
        self.assertEqual(p.site_id, "MLA")

    def test_init_valid_sites(self):
        from services.research_providers.meli_provider import MeliProvider

        for site in ("MLA", "MLM", "MLB", "MCO", "MLC"):
            p = MeliProvider(site)
            self.assertEqual(p.site_id, site)

    def test_search_products_parses_meli_response(self):
        from services.research_providers.meli_provider import MeliProvider

        provider = MeliProvider("MLA")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "MLA123",
                    "title": "Auriculares Bluetooth",
                    "price": 15999.99,
                    "currency_id": "ARS",
                    "permalink": "https://articulo.mercadolibre.com.ar/MLA-123",
                    "sold_quantity": 250,
                },
                {
                    "id": "MLA456",
                    "title": "Auriculares Inalambricos",
                    "price": 12500.0,
                    "currency_id": "ARS",
                    "permalink": "https://articulo.mercadolibre.com.ar/MLA-456",
                    "sold_quantity": 0,
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("services.research_providers.meli_provider.httpx.AsyncClient", return_value=mock_client):
            listings = asyncio.run(
                provider.search_products("auriculares bluetooth")
            )

        self.assertEqual(len(listings), 2)
        self.assertEqual(listings[0].title, "Auriculares Bluetooth")
        self.assertEqual(listings[0].price, Decimal("15999.99"))
        self.assertEqual(listings[0].currency, "ARS")
        self.assertFalse(listings[0].is_demo)
        self.assertIn("Mercado Libre", listings[0].source)
        self.assertEqual(listings[0].review_count, 250)

    def test_search_products_empty_response(self):
        from services.research_providers.meli_provider import MeliProvider

        provider = MeliProvider("MLM")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("services.research_providers.meli_provider.httpx.AsyncClient", return_value=mock_client):
            listings = asyncio.run(
                provider.search_products("producto inexistente")
            )

        self.assertEqual(listings, [])

    def test_estimate_demand_calculates_correctly(self):
        from services.research_providers.meli_provider import MeliProvider

        provider = MeliProvider("MLA")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"price": 1000, "sold_quantity": 500, "currency_id": "ARS"},
                {"price": 2000, "sold_quantity": 300, "currency_id": "ARS"},
                {"price": 1500, "sold_quantity": 200, "currency_id": "ARS"},
            ],
            "paging": {"total": 5000},
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("services.research_providers.meli_provider.httpx.AsyncClient", return_value=mock_client):
            demand = asyncio.run(
                provider.estimate_demand("auriculares")
            )

        self.assertEqual(demand.confidence_level, "alto")
        self.assertGreater(demand.estimated_monthly_volume, 0)
        self.assertIn("Mercado Libre", demand.source_description)
        self.assertIn("5000", demand.notes)

    def test_search_handles_http_error(self):
        from services.research_providers.meli_provider import MeliProvider
        import httpx

        provider = MeliProvider("MLA")

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_resp
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("services.research_providers.meli_provider.httpx.AsyncClient", return_value=mock_client):
            listings = asyncio.run(
                provider.search_products("test")
            )

        self.assertEqual(listings, [])


# ---------------------------------------------------------------------------
# Multi-provider cascade
# ---------------------------------------------------------------------------
class TestProviderCascade(unittest.TestCase):
    def test_get_providers_includes_meli_always(self):
        from services.research_service import _get_providers
        from services.research_providers.meli_provider import MeliProvider

        os.environ.pop("KEEPA_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)

        providers = _get_providers()
        meli_found = any(isinstance(p, MeliProvider) for p in providers)
        self.assertTrue(meli_found, "MeliProvider must always be in the cascade")

    def test_get_providers_adds_keepa_when_configured(self):
        from services.research_service import _get_providers
        from services.research_providers.keepa_provider import KeepaProvider

        os.environ["KEEPA_API_KEY"] = "test-key"
        try:
            providers = _get_providers()
            keepa_found = any(isinstance(p, KeepaProvider) for p in providers)
            self.assertTrue(keepa_found)
            keepa_idx = next(i for i, p in enumerate(providers) if isinstance(p, KeepaProvider))
            self.assertEqual(keepa_idx, 0, "Keepa should be first in priority")
        finally:
            del os.environ["KEEPA_API_KEY"]

    def test_get_providers_adds_gemini_when_configured(self):
        from services.research_service import _get_providers
        from services.research_providers.gemini_provider import GeminiMarketProvider

        os.environ["GEMINI_API_KEY"] = "test-gemini"
        os.environ.pop("KEEPA_API_KEY", None)
        try:
            providers = _get_providers()
            gemini_found = any(isinstance(p, GeminiMarketProvider) for p in providers)
            self.assertTrue(gemini_found)
        finally:
            del os.environ["GEMINI_API_KEY"]

    def test_get_provider_returns_first_provider(self):
        from services.research_service import _get_provider
        from services.research_providers.meli_provider import MeliProvider

        os.environ.pop("KEEPA_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)

        provider = _get_provider()
        self.assertIsInstance(provider, MeliProvider)

    def test_fallback_provider_is_mock(self):
        from services.research_service import _fallback_provider
        from services.research_providers.mock_provider import MockProvider

        fb = _fallback_provider()
        self.assertIsInstance(fb, MockProvider)


# ---------------------------------------------------------------------------
# Forecast explanation (_explain_forecast + _parse_forecast)
# ---------------------------------------------------------------------------
class TestForecastExplanation(unittest.TestCase):
    def test_parse_forecast_includes_explanation(self):
        from routers.research import _parse_forecast

        class FakeForecast:
            id = 1
            horizon_days = 30
            price_series = "[29.99, 31.50, 30.00]"
            forecast_series = "[30.50, 31.00, 31.80]"
            confidence_low = "[28.00, 29.00, 29.50]"
            confidence_high = "[33.00, 33.50, 34.00]"
            trend_direction = "alcista"
            launch_window = "Ahora"
            recommendation = "Buena oportunidad"
            provider = "timesfm_simulated"
            explanation = "Los precios muestran tendencia alcista."
            created_at = "2026-09-28"

        result = _parse_forecast(FakeForecast())
        self.assertIn("explanation", result)
        self.assertEqual(result["explanation"], "Los precios muestran tendencia alcista.")

    def test_parse_forecast_explanation_none_when_missing(self):
        from routers.research import _parse_forecast

        class FakeForecast:
            id = 2
            horizon_days = 90
            price_series = "[]"
            forecast_series = "[]"
            confidence_low = "[]"
            confidence_high = "[]"
            trend_direction = "estable"
            launch_window = "En 30 dias"
            recommendation = "Esperar"
            provider = "mock"
            explanation = None
            created_at = "2026-09-28"

        result = _parse_forecast(FakeForecast())
        self.assertIn("explanation", result)
        self.assertIsNone(result["explanation"])

    def test_parse_forecast_none_returns_none(self):
        from routers.research import _parse_forecast

        self.assertIsNone(_parse_forecast(None))

    def test_explain_forecast_calls_gateway(self):
        from routers.research import _explain_forecast

        class FakeResult:
            price_series = [29.99, 31.50]
            forecast_series = [32.00, 33.00]
            trend_direction = "alcista"
            launch_window = "Ahora"
            recommendation = "Buena oportunidad"
            provider = "timesfm_simulated"

        mock_explain = AsyncMock(return_value="Los precios van a subir.")

        with patch("services.ai_gateway_service.ai_gateway_service") as mock_gw:
            mock_gw.explain_results = mock_explain
            result = asyncio.run(
                _explain_forecast(FakeResult(), "wireless headphones", 30)
            )

        self.assertEqual(result, "Los precios van a subir.")
        mock_explain.assert_called_once()
        call_args = mock_explain.call_args
        self.assertEqual(call_args[1]["context_type"], "forecast")
        data = call_args[0][0]
        self.assertEqual(data["producto"], "wireless headphones")
        self.assertEqual(data["horizonte_dias"], 30)
        self.assertEqual(data["tendencia"], "alcista")

    def test_explain_forecast_returns_none_on_error(self):
        from routers.research import _explain_forecast

        class FakeResult:
            price_series = [29.99]
            forecast_series = [30.00]
            trend_direction = "estable"
            launch_window = "En 30 dias"
            recommendation = "Esperar"
            provider = "mock"

        with patch("services.ai_gateway_service.ai_gateway_service") as mock_gw:
            mock_gw.explain_results = AsyncMock(side_effect=RuntimeError("API down"))
            result = asyncio.run(
                _explain_forecast(FakeResult(), "test", 30)
            )

        self.assertIsNone(result)

    def test_explain_forecast_handles_empty_series(self):
        from routers.research import _explain_forecast

        class FakeResult:
            price_series = []
            forecast_series = []
            trend_direction = "estable"
            launch_window = "Indefinido"
            recommendation = "Sin datos"
            provider = "mock"

        mock_explain = AsyncMock(return_value="No hay datos suficientes.")

        with patch("services.ai_gateway_service.ai_gateway_service") as mock_gw:
            mock_gw.explain_results = mock_explain
            result = asyncio.run(
                _explain_forecast(FakeResult(), "producto", 90)
            )

        self.assertEqual(result, "No hay datos suficientes.")
        data = mock_explain.call_args[0][0]
        self.assertIsNone(data["precio_actual"])
        self.assertIsNone(data["precio_proyectado"])


# ---------------------------------------------------------------------------
# ResearchForecast model has explanation field
# ---------------------------------------------------------------------------
class TestResearchForecastModel(unittest.TestCase):
    def test_explanation_field_exists(self):
        from database.models import ResearchForecast

        fc = ResearchForecast(
            project_id=1,
            horizon_days=30,
            price_series="[]",
            forecast_series="[]",
            trend_direction="estable",
            provider="mock",
            explanation="Texto explicativo",
        )
        self.assertEqual(fc.explanation, "Texto explicativo")

    def test_explanation_defaults_to_none(self):
        from database.models import ResearchForecast

        fc = ResearchForecast(
            project_id=1,
            horizon_days=30,
            price_series="[]",
            forecast_series="[]",
            trend_direction="estable",
            provider="mock",
        )
        self.assertIsNone(fc.explanation)


if __name__ == "__main__":
    unittest.main()
