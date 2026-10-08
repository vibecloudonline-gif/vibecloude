"""Tests para YouTube research provider."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.research_providers.youtube_provider import YouTubeProvider
from services.research_providers.base import ProviderNotConfigured


def test_init_no_key():
    with pytest.raises(ProviderNotConfigured):
        YouTubeProvider("")


def test_init_with_key():
    provider = YouTubeProvider("test-key-123")
    assert provider.api_key == "test-key-123"


@pytest.mark.asyncio
async def test_search_products_success():
    search_data = {
        "items": [
            {
                "id": {"videoId": "abc123"},
                "snippet": {
                    "title": "Best Earbuds 2024 Review",
                    "channelTitle": "TechReviewer",
                },
            },
            {
                "id": {"videoId": "def456"},
                "snippet": {
                    "title": "AirPods Pro Unboxing",
                    "channelTitle": "GadgetGuy",
                },
            },
        ]
    }

    stats_data = {
        "items": [
            {"id": "abc123", "statistics": {"viewCount": "150000", "likeCount": "5000"}},
            {"id": "def456", "statistics": {"viewCount": "80000", "likeCount": "3000"}},
        ]
    }

    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = search_data
    mock_search_resp.raise_for_status = MagicMock()

    mock_stats_resp = MagicMock()
    mock_stats_resp.status_code = 200
    mock_stats_resp.json.return_value = stats_data
    mock_stats_resp.raise_for_status = MagicMock()

    provider = YouTubeProvider("test-key")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = [mock_search_resp, mock_stats_resp]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("earbuds")

    assert len(results) == 2
    assert "YouTube" in results[0].source
    assert results[0].review_count == 150000
    assert "youtube.com" in results[0].url
    assert results[0].is_demo is False


@pytest.mark.asyncio
async def test_search_products_empty():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_resp.raise_for_status = MagicMock()

    provider = YouTubeProvider("test-key")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("xyznotfound")

    assert results == []


@pytest.mark.asyncio
async def test_search_products_http_error():
    provider = YouTubeProvider("test-key")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        import httpx
        mock_request = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "forbidden", request=mock_request, response=mock_resp,
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("test")

    assert results == []


@pytest.mark.asyncio
async def test_estimate_demand_high_views():
    provider = YouTubeProvider("test-key")

    with patch.object(provider, "search_products", new_callable=AsyncMock) as mock_search:
        from services.research_providers.base import ProductListing
        mock_search.return_value = [
            ProductListing(
                source="YouTube (TechChannel)", title="Review Video",
                price=None, currency="USD", review_count=800_000, is_demo=False,
            ),
            ProductListing(
                source="YouTube (GadgetChannel)", title="Unboxing",
                price=None, currency="USD", review_count=500_000, is_demo=False,
            ),
        ]

        demand = await provider.estimate_demand("earbuds")

    assert demand.confidence_level == "alto"
    assert "YouTube" in demand.source_description
    assert "1,300,000" in demand.notes


@pytest.mark.asyncio
async def test_estimate_demand_no_results():
    provider = YouTubeProvider("test-key")

    with patch.object(provider, "search_products", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        demand = await provider.estimate_demand("xyznotfound")

    assert demand.confidence_level == "bajo"
    assert "sin resultados" in demand.source_description
