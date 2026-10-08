"""Tests para AliExpress research provider."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from services.research_providers.aliexpress_provider import AliExpressProvider, _parse_price


def test_parse_price_simple():
    assert _parse_price("12.99") == Decimal("12.99")


def test_parse_price_with_currency():
    assert _parse_price("US $24.50") == Decimal("24.50")


def test_parse_price_range():
    assert _parse_price("5.99-12.99") == Decimal("5.99")


def test_parse_price_none():
    assert _parse_price(None) is None


def test_parse_price_invalid():
    assert _parse_price("abc") is None


@pytest.mark.asyncio
async def test_search_products_success():
    mock_data = {
        "data": {
            "items": [
                {
                    "title": "Wireless Bluetooth Earbuds",
                    "prices": {"salePrice": {"minPrice": "8.99"}},
                    "productId": "123456",
                    "orders": "1500",
                    "averageStar": "4.7",
                },
                {
                    "title": "Phone Case Silicone",
                    "prices": {"salePrice": {"minPrice": "2.50"}},
                    "productId": "789012",
                    "orders": "3200",
                    "averageStar": "4.5",
                },
            ]
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_data

    provider = AliExpressProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("earbuds")

    assert len(results) == 2
    assert results[0].source == "AliExpress"
    assert results[0].price == Decimal("8.99")
    assert results[0].is_demo is False


@pytest.mark.asyncio
async def test_search_products_empty():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"items": []}}

    provider = AliExpressProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("xyznotfound")

    assert results == []


@pytest.mark.asyncio
async def test_search_products_http_error():
    provider = AliExpressProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp_1 = MagicMock()
        mock_resp_1.status_code = 403
        mock_resp_2 = MagicMock()
        mock_resp_2.status_code = 403
        mock_client.get.side_effect = [mock_resp_1, mock_resp_2]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("test")

    assert results == []


@pytest.mark.asyncio
async def test_estimate_demand():
    provider = AliExpressProvider()

    with patch.object(provider, "search_products", new_callable=AsyncMock) as mock_search:
        from services.research_providers.base import ProductListing
        mock_search.return_value = [
            ProductListing(
                source="AliExpress", title="Test", price=Decimal("5.00"),
                currency="USD", review_count=5000, is_demo=False,
            ),
            ProductListing(
                source="AliExpress", title="Test 2", price=Decimal("8.00"),
                currency="USD", review_count=3000, is_demo=False,
            ),
        ]

        demand = await provider.estimate_demand("earbuds")

    assert demand.confidence_level == "medio"
    assert demand.estimated_monthly_volume is not None
    assert "AliExpress" in demand.source_description
